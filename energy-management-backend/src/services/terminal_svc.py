from typing import List, Optional
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.models import Terminal


async def get_all_terminals(db: AsyncSession) -> List[Terminal]:
    stmt = select(Terminal).order_by(Terminal.id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_terminal(db: AsyncSession, terminal_id: str) -> Optional[Terminal]:
    stmt = select(Terminal).where(Terminal.id == terminal_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def update_terminal_status(
    db: AsyncSession,
    terminal_id: str,
    status: str,
    session_id: Optional[str] = None
) -> Optional[Terminal]:
    terminal = await get_terminal(db, terminal_id)
    if not terminal:
        return None
    terminal.status = status
    terminal.current_session_id = session_id
    terminal.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return terminal
