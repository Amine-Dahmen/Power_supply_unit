import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.models import Terminal, Reservation, Session
from src.api.schemas import CreateReservationRequest
from src.mqtt.publisher import send_assign_reservation


VALID_SERVICES = {"electricity", "water", "gas"}


class NoTerminalAvailableError(Exception):
    pass


class InvalidServicesError(Exception):
    pass


async def create_reservation(
    db: AsyncSession,
    request: CreateReservationRequest,
    mqtt_client: Optional[Any] = None,
    timeout_seconds: int = 120,
) -> Reservation:
    # 1. Validate requested services
    services = request.requested_services or ["electricity", "water", "gas"]
    if not set(services).issubset(VALID_SERVICES) or len(services) == 0:
        raise InvalidServicesError(f"Requested services must be a non-empty subset of {list(VALID_SERVICES)}")

    # 2. Find first ACTIVE terminal
    # Use with_for_update() if dialect supports it
    stmt = (
        select(Terminal)
        .where(Terminal.status == "ACTIVE")
        .order_by(Terminal.id)
        .limit(1)
        .with_for_update()
    )
    try:
        res = await db.execute(stmt)
        terminal = res.scalar_one_or_none()
    except Exception:
        # Fallback for SQLite / dialects without FOR UPDATE
        stmt = (
            select(Terminal)
            .where(Terminal.status == "ACTIVE")
            .order_by(Terminal.id)
            .limit(1)
        )
        res = await db.execute(stmt)
        terminal = res.scalar_one_or_none()

    if not terminal:
        raise NoTerminalAvailableError("No terminals available")

    # 3. Create IDs and timestamps
    res_id = uuid.uuid4()
    session_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=timeout_seconds)

    # 4. Create Reservation
    reservation = Reservation(
        id=res_id,
        customer_name=request.customer_name,
        card_uid=request.card_uid,
        requested_services=services,
        status="ASSIGNED",
        assigned_terminal_id=terminal.id,
        session_id=session_id,
        created_at=now,
        expires_at=expires_at,
        updated_at=now,
    )
    db.add(reservation)

    # 5. Create Session
    session_obj = Session(
        id=session_id,
        terminal_id=terminal.id,
        reservation_id=res_id,
        status="STARTED",
        started_at=now,
        updated_at=now,
    )
    db.add(session_obj)

    # 6. Update Terminal
    terminal.status = "OCCUPIED"
    terminal.current_session_id = str(session_id)
    terminal.updated_at = now

    await db.commit()
    await db.refresh(reservation)

    # 7. Publish MQTT command
    send_assign_reservation(
        mqtt_client=mqtt_client,
        terminal_id=terminal.id,
        reservation_id=res_id,
        session_id=session_id,
        card_uid=request.card_uid,
        requested_services=services,
        timeout_seconds=timeout_seconds,
    )

    return reservation


async def get_reservations(
    db: AsyncSession,
    status: Optional[str] = None
) -> List[Reservation]:
    stmt = select(Reservation).order_by(Reservation.created_at.desc())
    if status:
        stmt = stmt.where(Reservation.status == status)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_reservation(
    db: AsyncSession,
    reservation_id: uuid.UUID
) -> Optional[Reservation]:
    stmt = select(Reservation).where(Reservation.id == reservation_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def cancel_reservation(
    db: AsyncSession,
    reservation_id: uuid.UUID,
    mqtt_client: Optional[Any] = None
) -> Optional[Reservation]:
    reservation = await get_reservation(db, reservation_id)
    if not reservation or reservation.status not in ("PENDING", "ASSIGNED"):
        return None

    now = datetime.now(timezone.utc)

    # Free terminal if assigned
    if reservation.assigned_terminal_id:
        term_stmt = select(Terminal).where(Terminal.id == reservation.assigned_terminal_id)
        term_res = await db.execute(term_stmt)
        terminal = term_res.scalar_one_or_none()
        if terminal and terminal.current_session_id == str(reservation.session_id):
            terminal.status = "ACTIVE"
            terminal.current_session_id = None
            terminal.updated_at = now

    # Cancel session if exists
    if reservation.session_id:
        sess_stmt = select(Session).where(Session.id == reservation.session_id)
        sess_res = await db.execute(sess_stmt)
        sess = sess_res.scalar_one_or_none()
        if sess and sess.status in ("STARTED", "RUNNING"):
            sess.status = "CANCELLED"
            sess.ended_at = now
            sess.updated_at = now

    reservation.status = "CANCELLED"
    reservation.updated_at = now
    await db.commit()
    await db.refresh(reservation)
    return reservation
