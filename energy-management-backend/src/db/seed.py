from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.models import Terminal, TariffBracket, Reservation


async def seed_database(session: AsyncSession) -> None:
    # Check if terminals already exist
    result = await session.execute(select(Terminal))
    if result.scalars().first() is not None:
        return

    # 1. Terminals
    terminals = [
        Terminal(id="ST-01", status="ACTIVE"),
        Terminal(id="ST-02", status="ACTIVE"),
        Terminal(id="ST-03", status="ACTIVE"),
    ]
    session.add_all(terminals)

    # 2. Tariff brackets (Tunisian utility pricing inspired)
    tariffs = [
        # Electricity (kWh)
        TariffBracket(
            meter_type="electricity",
            tier_order=1,
            lower_bound=0.000,
            upper_bound=5.000,
            rate_per_unit=0.150,
            unit="kWh",
            currency="TND",
            fixed_fee=0.500,
            is_active=True,
        ),
        TariffBracket(
            meter_type="electricity",
            tier_order=2,
            lower_bound=5.000,
            upper_bound=20.000,
            rate_per_unit=0.230,
            unit="kWh",
            currency="TND",
            fixed_fee=None,
            is_active=True,
        ),
        TariffBracket(
            meter_type="electricity",
            tier_order=3,
            lower_bound=20.000,
            upper_bound=None,
            rate_per_unit=0.350,
            unit="kWh",
            currency="TND",
            fixed_fee=None,
            is_active=True,
        ),
        # Water (m3)
        TariffBracket(
            meter_type="water",
            tier_order=1,
            lower_bound=0.000,
            upper_bound=1.000,
            rate_per_unit=0.230,
            unit="m3",
            currency="TND",
            fixed_fee=0.300,
            is_active=True,
        ),
        TariffBracket(
            meter_type="water",
            tier_order=2,
            lower_bound=1.000,
            upper_bound=5.000,
            rate_per_unit=0.560,
            unit="m3",
            currency="TND",
            fixed_fee=None,
            is_active=True,
        ),
        TariffBracket(
            meter_type="water",
            tier_order=3,
            lower_bound=5.000,
            upper_bound=None,
            rate_per_unit=1.130,
            unit="m3",
            currency="TND",
            fixed_fee=None,
            is_active=True,
        ),
        # Gas (thermie)
        TariffBracket(
            meter_type="gas",
            tier_order=1,
            lower_bound=0.000,
            upper_bound=10.000,
            rate_per_unit=0.032,
            unit="thermie",
            currency="TND",
            fixed_fee=0.400,
            is_active=True,
        ),
        TariffBracket(
            meter_type="gas",
            tier_order=2,
            lower_bound=10.000,
            upper_bound=50.000,
            rate_per_unit=0.058,
            unit="thermie",
            currency="TND",
            fixed_fee=None,
            is_active=True,
        ),
        TariffBracket(
            meter_type="gas",
            tier_order=3,
            lower_bound=50.000,
            upper_bound=None,
            rate_per_unit=0.098,
            unit="thermie",
            currency="TND",
            fixed_fee=None,
            is_active=True,
        ),
    ]
    session.add_all(tariffs)

    # 3. Sample reservations
    now = datetime.now(timezone.utc)
    sample_reservations = [
        Reservation(
            customer_name="Ahmed Ben Ali",
            card_uid="RFID-A1B2C3D4",
            requested_services=["electricity", "water", "gas"],
            status="PENDING",
            expires_at=now + timedelta(minutes=2),
        ),
        Reservation(
            customer_name="Fatma Trabelsi",
            card_uid="RFID-E5F6A7B8",
            requested_services=["electricity", "water"],
            status="PENDING",
            expires_at=now + timedelta(minutes=2),
        ),
        Reservation(
            customer_name="Youssef Hammami",
            card_uid="RFID-C9D0E1F2",
            requested_services=["electricity", "gas"],
            status="PENDING",
            expires_at=now + timedelta(minutes=2),
        ),
    ]
    session.add_all(sample_reservations)

    await session.flush()
