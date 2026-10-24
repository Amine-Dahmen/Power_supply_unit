from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.session import get_db
from src.api.schemas import TerminalResponse
from src.services.terminal_svc import get_all_terminals, get_terminal

router = APIRouter()


@router.get("", response_model=List[TerminalResponse], summary="List all terminals")
async def list_terminals(db: AsyncSession = Depends(get_db)):
    return await get_all_terminals(db)


@router.get("/{terminal_id}", response_model=TerminalResponse, summary="Get terminal details")
async def get_terminal_by_id(terminal_id: str, db: AsyncSession = Depends(get_db)):
    term = await get_terminal(db, terminal_id)
    if not term:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Terminal {terminal_id} not found",
        )
    return term
