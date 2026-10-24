import uuid
from typing import List, Optional
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.models import Session, MeterReading


async def get_sessions(
    db: AsyncSession,
    terminal_id: Optional[str] = None,
    status: Optional[str] = None
) -> List[Session]:
    stmt = select(Session).order_by(Session.started_at.desc())
    if terminal_id:
        stmt = stmt.where(Session.terminal_id == terminal_id)
    if status:
        stmt = stmt.where(Session.status == status)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_session_detail(db: AsyncSession, session_id: uuid.UUID) -> Optional[Session]:
    stmt = (
        select(Session)
        .where(Session.id == session_id)
        .options(selectinload(Session.readings))
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_latest_consumption(db: AsyncSession, session_id: uuid.UUID) -> List[MeterReading]:
    stmt = (
        select(MeterReading)
        .where(MeterReading.session_id == session_id)
        .order_by(MeterReading.recorded_at.desc())
    )
    result = await db.execute(stmt)
    all_readings = result.scalars().all()

    # Get the latest reading per meter_type
    latest: dict[str, MeterReading] = {}
    for r in all_readings:
        if r.meter_type not in latest:
            latest[r.meter_type] = r
    return list(latest.values())


async def update_session_status(
    db: AsyncSession,
    session_id: uuid.UUID,
    status: str,
    ended_at: Optional[datetime] = None
) -> Optional[Session]:
    stmt = select(Session).where(Session.id == session_id)
    result = await db.execute(stmt)
    sess = result.scalar_one_or_none()
    if not sess:
        return None
    sess.status = status
    if ended_at:
        sess.ended_at = ended_at
    sess.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return sess
