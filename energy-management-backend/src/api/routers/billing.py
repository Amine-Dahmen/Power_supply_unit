import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.session import get_db
from src.api.schemas import InvoiceResponse
from src.services.billing_svc import get_invoice_by_session, get_all_invoices
from src.services.session_svc import get_session_detail

router = APIRouter()


@router.get("/sessions/{session_id}/invoice", response_model=InvoiceResponse, summary="Get session invoice")
async def get_session_invoice(session_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    sess = await get_session_detail(db, session_id)
    if not sess:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )

    inv = await get_invoice_by_session(db, session_id)
    if not inv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No invoice generated yet for session {session_id}",
        )
    return inv


@router.get("/invoices", response_model=List[InvoiceResponse], summary="List all invoices")
async def list_invoices(db: AsyncSession = Depends(get_db)):
    return await get_all_invoices(db)
