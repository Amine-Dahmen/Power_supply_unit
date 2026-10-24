import uuid
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Dict, Any, Optional
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.models import Invoice, InvoiceLine, MeterReading, TariffBracket

PRECISION = Decimal("0.001")


def to_dec(val: Any) -> Decimal:
    return Decimal(str(val))


def round_millime(val: Decimal) -> Decimal:
    return val.quantize(PRECISION, rounding=ROUND_HALF_UP)


def calculate_single_meter_cost(
    consumption: float,
    brackets: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Progressive tier calculation for a single meter.
    Uses Decimal with ROUND_HALF_UP for accurate millime rounding.
    """
    remaining = to_dec(consumption)
    fixed_fee = Decimal("0.000")
    tier_breakdown = []

    for bracket in brackets:
        # Tier 1 fixed fee
        if bracket.get("tier_order") == 1 and bracket.get("fixed_fee") is not None:
            fixed_fee = to_dec(bracket["fixed_fee"])

        lower = to_dec(bracket["lower_bound"])
        upper = to_dec(bracket["upper_bound"]) if bracket.get("upper_bound") is not None else None

        if upper is not None:
            tier_capacity = upper - lower
            applicable = max(Decimal("0.000"), min(remaining, tier_capacity))
        else:
            applicable = max(Decimal("0.000"), remaining)

        if applicable > Decimal("0.000"):
            rate = to_dec(bracket["rate_per_unit"])
            cost = round_millime(applicable * rate)
            tier_breakdown.append({
                "tier": bracket["tier_order"],
                "range": f"{float(lower)}-{float(upper) if upper is not None else '∞'}",
                "applicable": float(round_millime(applicable)),
                "rate": float(rate),
                "cost": float(cost),
            })
            remaining -= applicable

    usage_amount = sum((Decimal(str(t["cost"])) for t in tier_breakdown), Decimal("0.000"))
    line_total = round_millime(fixed_fee + usage_amount)

    return {
        "consumption": float(round_millime(to_dec(consumption))),
        "fixed_fee": float(round_millime(fixed_fee)),
        "usage_amount": float(round_millime(usage_amount)),
        "line_total": float(line_total),
        "tier_breakdown": tier_breakdown,
    }


async def calculate_and_store_invoice(
    db: AsyncSession,
    session_id: uuid.UUID,
    requested_services: List[str]
) -> Invoice:
    """
    Calculates the final invoice for a session using stored final meter readings
    and active tariff brackets. Ensures idempotent storage via UNIQUE constraint.
    """
    # Check if invoice already exists
    existing_stmt = (
        select(Invoice)
        .where(Invoice.session_id == session_id)
        .options(selectinload(Invoice.lines))
    )
    existing_res = await db.execute(existing_stmt)
    existing_invoice = existing_res.scalar_one_or_none()
    if existing_invoice:
        return existing_invoice

    # 1. Fetch final readings for this session
    readings_stmt = select(MeterReading).where(
        MeterReading.session_id == session_id,
        MeterReading.is_final == True,
    )
    readings_res = await db.execute(readings_stmt)
    final_readings = readings_res.scalars().all()

    # 2. Fetch active tariff brackets
    brackets_stmt = (
        select(TariffBracket)
        .where(TariffBracket.is_active == True)
        .order_by(TariffBracket.meter_type, TariffBracket.tier_order)
    )
    brackets_res = await db.execute(brackets_stmt)
    all_brackets = brackets_res.scalars().all()

    brackets_by_type: Dict[str, List[Dict[str, Any]]] = {}
    for b in all_brackets:
        brackets_by_type.setdefault(b.meter_type, []).append({
            "tier_order": b.tier_order,
            "lower_bound": float(b.lower_bound),
            "upper_bound": float(b.upper_bound) if b.upper_bound is not None else None,
            "rate_per_unit": float(b.rate_per_unit),
            "fixed_fee": float(b.fixed_fee) if b.fixed_fee is not None else None,
        })

    # 3. Calculate per requested meter
    invoice_lines = []
    total_amount = Decimal("0.000")

    for reading in final_readings:
        if reading.meter_type not in requested_services:
            continue

        b_list = brackets_by_type.get(reading.meter_type, [])
        calc_res = calculate_single_meter_cost(float(reading.cumulative_value), b_list)

        line = InvoiceLine(
            meter_type=reading.meter_type,
            consumption=calc_res["consumption"],
            unit=reading.unit,
            fixed_fee=calc_res["fixed_fee"],
            usage_amount=calc_res["usage_amount"],
            line_total=calc_res["line_total"],
            tier_breakdown=calc_res["tier_breakdown"],
        )
        invoice_lines.append(line)
        total_amount += Decimal(str(calc_res["line_total"]))

    total_amount = float(round_millime(total_amount))
    invoice = Invoice(
        session_id=session_id,
        total_amount=total_amount,
        currency="TND",
        lines=invoice_lines,
    )

    db.add(invoice)
    try:
        await db.commit()
        # Reload with lines
        res = await db.execute(existing_stmt)
        return res.scalar_one()
    except IntegrityError:
        await db.rollback()
        res = await db.execute(existing_stmt)
        return res.scalar_one()


async def get_invoice_by_session(db: AsyncSession, session_id: uuid.UUID) -> Optional[Invoice]:
    stmt = (
        select(Invoice)
        .where(Invoice.session_id == session_id)
        .options(selectinload(Invoice.lines))
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_all_invoices(db: AsyncSession) -> List[Invoice]:
    stmt = select(Invoice).options(selectinload(Invoice.lines)).order_by(Invoice.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())
