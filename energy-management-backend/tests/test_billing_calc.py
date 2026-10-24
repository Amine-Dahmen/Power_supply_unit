import uuid
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.models import Session, MeterReading, Invoice
from src.services.billing_svc import (
    calculate_single_meter_cost,
    calculate_and_store_invoice,
)

ELECTRICITY_BRACKETS = [
    {"tier_order": 1, "lower_bound": 0.0, "upper_bound": 5.0, "rate_per_unit": 0.150, "fixed_fee": 0.500},
    {"tier_order": 2, "lower_bound": 5.0, "upper_bound": 20.0, "rate_per_unit": 0.230, "fixed_fee": None},
    {"tier_order": 3, "lower_bound": 20.0, "upper_bound": None, "rate_per_unit": 0.350, "fixed_fee": None},
]

WATER_BRACKETS = [
    {"tier_order": 1, "lower_bound": 0.0, "upper_bound": 1.0, "rate_per_unit": 0.230, "fixed_fee": 0.300},
    {"tier_order": 2, "lower_bound": 1.0, "upper_bound": 5.0, "rate_per_unit": 0.560, "fixed_fee": None},
    {"tier_order": 3, "lower_bound": 5.0, "upper_bound": None, "rate_per_unit": 1.130, "fixed_fee": None},
]

GAS_BRACKETS = [
    {"tier_order": 1, "lower_bound": 0.0, "upper_bound": 10.0, "rate_per_unit": 0.032, "fixed_fee": 0.400},
    {"tier_order": 2, "lower_bound": 10.0, "upper_bound": 50.0, "rate_per_unit": 0.058, "fixed_fee": None},
    {"tier_order": 3, "lower_bound": 50.0, "upper_bound": None, "rate_per_unit": 0.098, "fixed_fee": None},
]


def test_electricity_billing_single_tier():
    # 3 kWh in tier 1 (0-5 kWh): 0.500 fixed + 3 * 0.150 = 0.950 TND
    res = calculate_single_meter_cost(3.0, ELECTRICITY_BRACKETS)
    assert res["fixed_fee"] == 0.500
    assert res["usage_amount"] == 0.450
    assert res["line_total"] == 0.950
    assert len(res["tier_breakdown"]) == 1


def test_electricity_billing_multi_tier():
    # 12.450 kWh:
    # fixed: 0.500
    # tier 1 (5 kWh * 0.150): 0.750
    # tier 2 (7.450 kWh * 0.230): 1.714
    # line_total: 0.500 + 0.750 + 1.714 = 2.964
    res = calculate_single_meter_cost(12.450, ELECTRICITY_BRACKETS)
    assert res["fixed_fee"] == 0.500
    assert res["usage_amount"] == 2.464
    assert res["line_total"] == 2.964
    assert len(res["tier_breakdown"]) == 2


def test_water_billing():
    # 2.380 m3:
    # fixed: 0.300
    # tier 1 (1.000 m3 * 0.230): 0.230
    # tier 2 (1.380 m3 * 0.560): 0.773
    # line_total: 0.300 + 0.230 + 0.773 = 1.303
    res = calculate_single_meter_cost(2.380, WATER_BRACKETS)
    assert res["fixed_fee"] == 0.300
    assert res["usage_amount"] == 1.003
    assert res["line_total"] == 1.303


def test_gas_billing():
    # 18.700 thermies:
    # fixed: 0.400
    # tier 1 (10.000 * 0.032): 0.320
    # tier 2 (8.700 * 0.058): 0.505
    # line_total: 0.400 + 0.320 + 0.505 = 1.225
    res = calculate_single_meter_cost(18.700, GAS_BRACKETS)
    assert res["fixed_fee"] == 0.400
    assert res["usage_amount"] == 0.825
    assert res["line_total"] == 1.225


def test_zero_consumption():
    res = calculate_single_meter_cost(0.0, ELECTRICITY_BRACKETS)
    assert res["fixed_fee"] == 0.500
    assert res["usage_amount"] == 0.0
    assert res["line_total"] == 0.500
    assert len(res["tier_breakdown"]) == 0


def test_tier_boundary_exact():
    # Exactly 5.0 kWh
    res = calculate_single_meter_cost(5.0, ELECTRICITY_BRACKETS)
    assert res["fixed_fee"] == 0.500
    assert res["usage_amount"] == 0.750
    assert res["line_total"] == 1.250
    assert len(res["tier_breakdown"]) == 1


@pytest.mark.asyncio
async def test_full_invoice_calculation_and_storage(seeded_db: AsyncSession):
    session_id = uuid.uuid4()
    sess = Session(
        id=session_id,
        terminal_id="ST-01",
        reservation_id=uuid.uuid4(),
        status="RUNNING",
    )
    seeded_db.add(sess)

    # Add final readings for all 3 meters matching proposal
    seeded_db.add_all([
        MeterReading(session_id=session_id, meter_type="electricity", cumulative_value=12.450, unit="kWh", is_final=True),
        MeterReading(session_id=session_id, meter_type="water", cumulative_value=2.380, unit="m3", is_final=True),
        MeterReading(session_id=session_id, meter_type="gas", cumulative_value=18.700, unit="thermie", is_final=True),
    ])
    await seeded_db.commit()

    # Calculate and store invoice
    invoice = await calculate_and_store_invoice(
        seeded_db,
        session_id=session_id,
        requested_services=["electricity", "water", "gas"],
    )

    # 2.964 + 1.303 + 1.225 = 5.492 TND
    assert float(invoice.total_amount) == 5.492
    assert invoice.currency == "TND"
    assert len(invoice.lines) == 3


@pytest.mark.asyncio
async def test_duplicate_invoice_prevented(seeded_db: AsyncSession):
    session_id = uuid.uuid4()
    sess = Session(
        id=session_id,
        terminal_id="ST-02",
        reservation_id=uuid.uuid4(),
        status="RUNNING",
    )
    seeded_db.add(sess)
    seeded_db.add(
        MeterReading(session_id=session_id, meter_type="electricity", cumulative_value=10.0, unit="kWh", is_final=True)
    )
    await seeded_db.commit()

    # First call
    inv1 = await calculate_and_store_invoice(seeded_db, session_id, ["electricity"])
    # Second call
    inv2 = await calculate_and_store_invoice(seeded_db, session_id, ["electricity"])

    assert inv1.id == inv2.id
    assert inv1.total_amount == inv2.total_amount

    # Ensure DB only has one invoice for this session
    stmt = select(Invoice).where(Invoice.session_id == session_id)
    res = await seeded_db.execute(stmt)
    assert len(res.scalars().all()) == 1


@pytest.mark.asyncio
async def test_requested_services_filter(seeded_db: AsyncSession):
    session_id = uuid.uuid4()
    sess = Session(
        id=session_id,
        terminal_id="ST-03",
        reservation_id=uuid.uuid4(),
        status="RUNNING",
    )
    seeded_db.add(sess)
    seeded_db.add_all([
        MeterReading(session_id=session_id, meter_type="electricity", cumulative_value=12.450, unit="kWh", is_final=True),
        MeterReading(session_id=session_id, meter_type="gas", cumulative_value=18.700, unit="thermie", is_final=True),
    ])
    await seeded_db.commit()

    # Customer only requested electricity (gas should NOT be billed)
    invoice = await calculate_and_store_invoice(seeded_db, session_id, ["electricity"])

    assert float(invoice.total_amount) == 2.964
    assert len(invoice.lines) == 1
    assert invoice.lines[0].meter_type == "electricity"
