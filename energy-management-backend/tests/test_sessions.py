import uuid
import pytest
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.models import Session, MeterReading
from src.services.session_svc import (
    get_sessions,
    get_session_detail,
    get_latest_consumption,
    update_session_status,
)


@pytest.mark.asyncio
async def test_session_lifecycle_and_queries(seeded_db: AsyncSession):
    session_id = uuid.uuid4()
    sess = Session(
        id=session_id,
        terminal_id="ST-01",
        reservation_id=uuid.uuid4(),
        status="STARTED",
    )
    seeded_db.add(sess)
    await seeded_db.commit()

    # Query list
    sessions = await get_sessions(seeded_db, terminal_id="ST-01")
    assert len(sessions) >= 1
    assert any(s.id == session_id for s in sessions)

    # Update status to RUNNING
    updated = await update_session_status(seeded_db, session_id, "RUNNING")
    assert updated.status == "RUNNING"

    # Add telemetry readings
    seeded_db.add_all([
        MeterReading(
            session_id=session_id,
            meter_type="electricity",
            cumulative_value=1.5,
            unit="kWh",
            is_final=False,
            recorded_at=datetime.now(timezone.utc),
        ),
        MeterReading(
            session_id=session_id,
            meter_type="water",
            cumulative_value=0.2,
            unit="m3",
            is_final=False,
            recorded_at=datetime.now(timezone.utc),
        ),
    ])
    await seeded_db.commit()

    # Get live consumption
    latest = await get_latest_consumption(seeded_db, session_id)
    assert len(latest) == 2
    meter_types = {r.meter_type for r in latest}
    assert "electricity" in meter_types
    assert "water" in meter_types

    # Detail query
    detail = await get_session_detail(seeded_db, session_id)
    assert detail is not None
    assert len(detail.readings) == 2
