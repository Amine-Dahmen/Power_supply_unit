import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.session import get_db
from src.api.schemas import SessionResponse, SessionDetailResponse, MeterReadingResponse
from src.services.session_svc import (
    get_sessions,
    get_session_detail,
    get_latest_consumption,
)

router = APIRouter()


@router.get("", response_model=List[SessionResponse], summary="List sessions")
async def list_sessions(
    terminal_id: Optional[str] = None,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    return await get_sessions(db, terminal_id=terminal_id, status=status)


@router.get("/{session_id}", response_model=SessionDetailResponse, summary="Get session detail")
async def get_session(session_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    sess = await get_session_detail(db, session_id)
    if not sess:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )
    return sess


@router.get(
    "/{session_id}/consumption",
    response_model=List[MeterReadingResponse],
    summary="Get live consumption snapshot",
)
async def get_session_consumption(session_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    sess = await get_session_detail(db, session_id)
    if not sess:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )
    return await get_latest_consumption(db, session_id)
