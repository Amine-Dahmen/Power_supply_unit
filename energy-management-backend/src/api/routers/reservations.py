import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.session import get_db
from src.api.schemas import CreateReservationRequest, ReservationResponse
from src.services.reservation_svc import (
    create_reservation,
    get_reservations,
    get_reservation,
    cancel_reservation,
    NoTerminalAvailableError,
    InvalidServicesError,
)

router = APIRouter()


@router.post(
    "",
    response_model=ReservationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new reservation",
)
async def make_reservation(
    body: CreateReservationRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    mqtt_client = getattr(request.app.state, "mqtt_client", None)
    config = getattr(request.app.state, "config", None)
    timeout = config.RESERVATION_TIMEOUT_SECONDS if config else 120

    try:
        reservation = await create_reservation(
            db=db,
            request=body,
            mqtt_client=mqtt_client,
            timeout_seconds=timeout,
        )
        return reservation
    except NoTerminalAvailableError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except InvalidServicesError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("", response_model=List[ReservationResponse], summary="List reservations")
async def list_reservations(
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    return await get_reservations(db, status=status)


@router.get("/{reservation_id}", response_model=ReservationResponse, summary="Get reservation")
async def get_reservation_by_id(
    reservation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    res = await get_reservation(db, reservation_id)
    if not res:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reservation {reservation_id} not found",
        )
    return res


@router.delete("/{reservation_id}", response_model=ReservationResponse, summary="Cancel reservation")
async def cancel_reservation_by_id(
    reservation_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    mqtt_client = getattr(request.app.state, "mqtt_client", None)
    res = await cancel_reservation(db, reservation_id, mqtt_client)
    if not res:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Reservation {reservation_id} could not be cancelled or is not in PENDING/ASSIGNED status",
        )
    return res
