import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from src.db.models import (
    Terminal,
    Reservation,
    Session,
    MeterReading,
    ProcessedMessage,
)
from src.services.billing_svc import calculate_and_store_invoice
from src.mqtt.publisher import send_complete_session

logger = logging.getLogger(__name__)


class EventHandler:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], mqtt_client: Any):
        self.session_factory = session_factory
        self.mqtt_client = mqtt_client
        self._in_memory_seen: dict[str, float] = {}

    async def handle_message(self, topic: str, data: dict):
        # 1. Handle special non-envelope status messages
        if topic == "energy/simulator/status":
            await self._handle_simulator_status(data)
            return

        if topic.endswith("/status"):
            await self._handle_terminal_status(topic, data)
            return

        msg_id = data.get("messageId")
        # 2. Idempotency check
        if msg_id:
            async with self.session_factory() as db:
                existing = await db.get(ProcessedMessage, msg_id)
                if existing:
                    logger.info(f"Duplicate message {msg_id} on {topic}, ignoring.")
                    return

        # 3. Extract terminalId
        parts = topic.split("/")
        terminal_id = parts[2] if len(parts) >= 4 else data.get("terminalId")
        msg_type = data.get("type")
        payload = data.get("payload", {})
        reservation_id_str = data.get("reservationId")
        session_id_str = data.get("sessionId")

        res_id = uuid.UUID(reservation_id_str) if reservation_id_str else None
        sess_id = uuid.UUID(session_id_str) if session_id_str else None

        async with self.session_factory() as db:
            try:
                if msg_type == "COMMAND_ACK":
                    logger.info(f"Received COMMAND_ACK from {terminal_id}: {payload}")

                elif msg_type == "SESSION_STARTED":
                    await self._handle_session_started(db, terminal_id, sess_id, res_id)

                elif msg_type == "FINAL_READINGS":
                    await self._handle_final_readings(db, terminal_id, sess_id, res_id, payload)

                elif msg_type == "CARD_REJECTED":
                    logger.warning(f"Card rejected on {terminal_id}: {payload}")

                elif msg_type == "RESERVATION_EXPIRED":
                    await self._handle_reservation_expired(db, terminal_id, res_id, sess_id)

                elif msg_type == "STATE_CHANGED":
                    await self._handle_state_changed(db, terminal_id, payload)

                elif msg_type == "ERROR":
                    await self._handle_error(db, terminal_id, sess_id, payload)

                elif msg_type == "ERROR_CLEARED":
                    await self._handle_error_cleared(db, terminal_id)

                elif msg_type == "METER_READINGS":
                    await self._handle_telemetry(db, sess_id, payload)

                # Record message in processed_messages
                if msg_id:
                    now = datetime.now(timezone.utc)
                    db.add(
                        ProcessedMessage(
                            message_id=msg_id,
                            received_at=now,
                            expires_at=now + timedelta(hours=1),
                        )
                    )
                await db.commit()
            except Exception as e:
                await db.rollback()
                logger.error(f"Error handling message {msg_id} ({msg_type}) on {topic}: {e}", exc_info=True)

    async def _handle_session_started(
        self, db: AsyncSession, terminal_id: Optional[str], session_id: Optional[uuid.UUID], reservation_id: Optional[uuid.UUID]
    ):
        now = datetime.now(timezone.utc)
        if session_id:
            sess = await db.get(Session, session_id)
            if sess:
                sess.status = "RUNNING"
                sess.updated_at = now

        if reservation_id:
            res = await db.get(Reservation, reservation_id)
            if res:
                res.status = "IN_PROGRESS"
                res.updated_at = now

        if terminal_id:
            term = await db.get(Terminal, terminal_id)
            if term:
                term.status = "OCCUPIED"
                term.current_session_id = str(session_id) if session_id else term.current_session_id
                term.updated_at = now

    async def _handle_final_readings(
        self,
        db: AsyncSession,
        terminal_id: str,
        session_id: Optional[uuid.UUID],
        reservation_id: Optional[uuid.UUID],
        payload: dict,
    ):
        if not session_id:
            return

        now = datetime.now(timezone.utc)
        readings_data = payload.get("readings", [])

        # Store final readings
        for r in readings_data:
            reading_obj = MeterReading(
                id=uuid.uuid4(),
                session_id=session_id,
                meter_type=r["meterType"],
                cumulative_value=r["value"],
                unit=r["unit"],
                is_final=True,
                recorded_at=now,
            )
            db.add(reading_obj)

        # Update Session
        sess = await db.get(Session, session_id)
        if sess:
            sess.status = "COMPLETED"
            sess.ended_at = now
            sess.updated_at = now

        # Retrieve reservation to know requested_services
        requested_services = ["electricity", "water", "gas"]
        res = None
        if reservation_id:
            res = await db.get(Reservation, reservation_id)
        elif sess and sess.reservation_id:
            res = await db.get(Reservation, sess.reservation_id)

        if res and res.requested_services:
            requested_services = res.requested_services

        await db.flush()

        # Calculate billing and store invoice
        await calculate_and_store_invoice(db, session_id, requested_services)

        if res:
            res.status = "COMPLETED"
            res.updated_at = now

        # Send COMPLETE_SESSION command back to terminal
        send_complete_session(
            mqtt_client=self.mqtt_client,
            terminal_id=terminal_id,
            reservation_id=res.id if res else reservation_id,
            session_id=session_id,
        )

    async def _handle_reservation_expired(
        self, db: AsyncSession, terminal_id: Optional[str], reservation_id: Optional[uuid.UUID], session_id: Optional[uuid.UUID]
    ):
        now = datetime.now(timezone.utc)
        if reservation_id:
            res = await db.get(Reservation, reservation_id)
            if res and res.status in ("PENDING", "ASSIGNED"):
                res.status = "EXPIRED"
                res.updated_at = now

        if session_id:
            sess = await db.get(Session, session_id)
            if sess and sess.status == "STARTED":
                sess.status = "INTERRUPTED"
                sess.ended_at = now
                sess.updated_at = now

        if terminal_id:
            term = await db.get(Terminal, terminal_id)
            if term:
                term.status = "ACTIVE"
                term.current_session_id = None
                term.updated_at = now

    async def _handle_state_changed(self, db: AsyncSession, terminal_id: Optional[str], payload: dict):
        if not terminal_id:
            return
        new_state = payload.get("newState")
        term = await db.get(Terminal, terminal_id)
        if not term:
            return

        now = datetime.now(timezone.utc)
        if new_state == "ACTIVE":
            term.status = "ACTIVE"
            term.current_session_id = None
            term.updated_at = now
        elif new_state in ("RUNNING", "STOPPING", "WAITING_FOR_CARD"):
            term.status = "OCCUPIED"
            term.updated_at = now
        elif new_state == "ERROR":
            term.status = "ERROR"
            term.updated_at = now

    async def _handle_error(
        self, db: AsyncSession, terminal_id: Optional[str], session_id: Optional[uuid.UUID], payload: dict
    ):
        now = datetime.now(timezone.utc)
        if terminal_id:
            term = await db.get(Terminal, terminal_id)
            if term:
                term.status = "ERROR"
                term.updated_at = now

        if session_id:
            sess = await db.get(Session, session_id)
            if sess and sess.status in ("STARTED", "RUNNING"):
                sess.status = "INTERRUPTED"
                sess.ended_at = now
                sess.updated_at = now

    async def _handle_error_cleared(self, db: AsyncSession, terminal_id: Optional[str]):
        if not terminal_id:
            return
        term = await db.get(Terminal, terminal_id)
        if term:
            term.status = "ACTIVE"
            term.current_session_id = None
            term.updated_at = datetime.now(timezone.utc)

    async def _handle_telemetry(self, db: AsyncSession, session_id: Optional[uuid.UUID], payload: dict):
        if not session_id:
            return

        readings = payload.get("readings", [])
        now = datetime.now(timezone.utc)

        for r in readings:
            meter_type = r.get("meterType")
            val = r.get("value")
            unit = r.get("unit")
            if not meter_type or val is None:
                continue

            # Check if a non-final reading exists for this session + meter_type
            stmt = select(MeterReading).where(
                MeterReading.session_id == session_id,
                MeterReading.meter_type == meter_type,
                MeterReading.is_final == False,
            )
            res = await db.execute(stmt)
            reading_obj = res.scalar_one_or_none()
            if reading_obj:
                reading_obj.cumulative_value = val
                reading_obj.recorded_at = now
            else:
                db.add(
                    MeterReading(
                        id=uuid.uuid4(),
                        session_id=session_id,
                        meter_type=meter_type,
                        cumulative_value=val,
                        unit=unit,
                        is_final=False,
                        recorded_at=now,
                    )
                )

    async def _handle_simulator_status(self, data: dict):
        state = data.get("state")
        if state == "OFFLINE":
            async with self.session_factory() as db:
                terms = await db.execute(select(Terminal))
                now = datetime.now(timezone.utc)
                for t in terms.scalars().all():
                    t.status = "OFFLINE"
                    t.updated_at = now
                await db.commit()
                logger.warning("Simulator offline; marked all terminals OFFLINE")

    async def _handle_terminal_status(self, topic: str, data: dict):
        parts = topic.split("/")
        terminal_id = parts[2] if len(parts) >= 4 else data.get("terminalId")
        state = data.get("state")
        if not terminal_id or not state:
            return

        async with self.session_factory() as db:
            term = await db.get(Terminal, terminal_id)
            if term:
                now = datetime.now(timezone.utc)
                if state == "OFFLINE":
                    term.status = "OFFLINE"
                elif state == "ACTIVE":
                    term.status = "ACTIVE"
                    term.current_session_id = None
                elif state in ("WAITING_FOR_CARD", "RUNNING", "STOPPING"):
                    term.status = "OCCUPIED"
                elif state == "ERROR":
                    term.status = "ERROR"
                term.updated_at = now
                await db.commit()
