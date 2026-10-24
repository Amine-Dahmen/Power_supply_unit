import asyncio
from enum import Enum
import logging
import random
import time
from typing import Any

from src.models.messages import (
    build_card_rejected,
    build_command_ack,
    build_error_cleared,
    build_error_event,
    build_final_readings,
    build_meter_readings_telemetry,
    build_reservation_expired,
    build_session_started,
    build_state_changed,
    build_status,
)
from src.terminal.meter import Meter

logger = logging.getLogger(__name__)


class TerminalState(str, Enum):
    ACTIVE = "ACTIVE"
    WAITING_FOR_CARD = "WAITING_FOR_CARD"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"


class Terminal:
    def __init__(self, terminal_id: str, mqtt_client: Any, config: Any):
        self.terminal_id = terminal_id
        self._mqtt_client = mqtt_client
        self._config = config
        self.state: TerminalState = TerminalState.ACTIVE
        self.reservation_id: str | None = None
        self.session_id: str | None = None
        self.card_uid: str | None = None
        self.requested_services: list[str] = []
        self._timeout_task: asyncio.Task | None = None
        self._telemetry_task: asyncio.Task | None = None
        self._sequence_number: int = 0
        self._session_start_time: float | None = None

        self.meters: dict[str, Meter] = {}
        for m_type, unit, inc_min, inc_max in [
            ("electricity", "kWh", 0.05, 0.25),
            ("water", "m3", 0.005, 0.05),
            ("gas", "thermie", 0.1, 0.5),
        ]:
            rng = (
                random.Random(config.RANDOM_SEED + hash(m_type))
                if config.RANDOM_SEED is not None
                else None
            )
            self.meters[m_type] = Meter(
                meter_type=m_type,
                unit=unit,
                increment_min=inc_min,
                increment_max=inc_max,
                rng=rng,
            )

    def publish_status(self) -> None:
        """Publish retained terminal status."""
        status_payload = build_status(
            terminal_id=self.terminal_id,
            state=self.state.value,
            session_id=self.session_id,
            reservation_id=self.reservation_id,
        )
        self._mqtt_client.publish(
            f"energy/terminals/{self.terminal_id}/status",
            status_payload,
            qos=1,
            retain=True,
        )

    async def assign_reservation(
        self,
        msg_id: str | None,
        reservation_id: str | None,
        session_id: str | None,
        card_uid: str | None,
        services: list[str] | None = None,
        timeout_s: float | None = None,
    ) -> dict[str, Any]:
        """Assign reservation command handler."""
        if self.state != TerminalState.ACTIVE:
            return {
                "success": False,
                "reason": f"Terminal not in ACTIVE state (current: {self.state.value})",
            }

        self.reservation_id = reservation_id
        self.session_id = session_id
        self.card_uid = card_uid
        self.requested_services = services or []
        self.state = TerminalState.WAITING_FOR_CARD

        timeout = (
            timeout_s
            if timeout_s is not None
            else self._config.RESERVATION_TIMEOUT_SECONDS
        )
        self._timeout_task = asyncio.create_task(self._reservation_timeout(timeout))

        ack = build_command_ack(
            terminal_id=self.terminal_id,
            reservation_id=self.reservation_id,
            session_id=self.session_id,
            acked_message_id=msg_id or "",
            command_type="ASSIGN_RESERVATION",
            success=True,
            new_state=self.state.value,
        )
        self._mqtt_client.publish(
            f"energy/terminals/{self.terminal_id}/events",
            ack,
            qos=1,
        )
        self.publish_status()
        return {
            "success": True,
            "terminalId": self.terminal_id,
            "state": self.state.value,
            "reservationId": self.reservation_id,
        }

    async def present_card(self, card_uid: str) -> dict[str, Any]:
        """Handle RFID card tap on terminal."""
        if self.state == TerminalState.WAITING_FOR_CARD:
            if card_uid != self.card_uid:
                evt = build_card_rejected(
                    terminal_id=self.terminal_id,
                    reservation_id=self.reservation_id,
                    presented_card_uid=card_uid,
                    reason="CARD_UID_MISMATCH",
                    state=self.state.value,
                )
                self._mqtt_client.publish(
                    f"energy/terminals/{self.terminal_id}/events",
                    evt,
                    qos=1,
                )
                return {"success": False, "reason": "CARD_UID_MISMATCH"}

            # Cancel reservation timeout
            if self._timeout_task and not self._timeout_task.done():
                self._timeout_task.cancel()
                self._timeout_task = None

            self.state = TerminalState.RUNNING
            self._sequence_number = 0
            self._session_start_time = time.time()
            self._telemetry_task = asyncio.create_task(self._run_telemetry())

            evt = build_session_started(
                terminal_id=self.terminal_id,
                reservation_id=self.reservation_id,
                session_id=self.session_id,
                active_meters=list(self.meters.keys()),
                state=self.state.value,
            )
            self._mqtt_client.publish(
                f"energy/terminals/{self.terminal_id}/events",
                evt,
                qos=1,
            )
            self.publish_status()
            return {
                "success": True,
                "terminalId": self.terminal_id,
                "state": self.state.value,
                "sessionId": self.session_id,
            }

        elif self.state == TerminalState.RUNNING:
            if card_uid != self.card_uid:
                return {"success": False, "reason": "CARD_UID_MISMATCH"}

            # Cancel telemetry task
            if self._telemetry_task and not self._telemetry_task.done():
                self._telemetry_task.cancel()
                self._telemetry_task = None

            readings = [m.reading for m in self.meters.values()]
            duration = (
                int(time.time() - self._session_start_time)
                if self._session_start_time
                else 0
            )
            self.state = TerminalState.STOPPING

            evt = build_final_readings(
                terminal_id=self.terminal_id,
                reservation_id=self.reservation_id,
                session_id=self.session_id,
                readings_list=readings,
                session_duration_seconds=duration,
                state=self.state.value,
            )
            self._mqtt_client.publish(
                f"energy/terminals/{self.terminal_id}/events",
                evt,
                qos=1,
            )
            self.publish_status()

            self._timeout_task = asyncio.create_task(self._ack_timeout())
            return {
                "success": True,
                "terminalId": self.terminal_id,
                "state": self.state.value,
                "sessionId": self.session_id,
                "readings": readings,
                "sessionDurationSeconds": duration,
            }

        else:
            return {
                "success": False,
                "reason": f"Invalid terminal state for card tap: {self.state.value}",
            }

    async def complete_session(self, session_id: str | None) -> dict[str, Any]:
        """Handle COMPLETE_SESSION command from backend."""
        if self.state != TerminalState.STOPPING or session_id != self.session_id:
            return {
                "success": False,
                "reason": f"Cannot complete session: state={self.state.value}, session_id mismatch",
            }

        if self._timeout_task and not self._timeout_task.done():
            self._timeout_task.cancel()
            self._timeout_task = None

        self.state = TerminalState.COMPLETED
        evt1 = build_state_changed(
            terminal_id=self.terminal_id,
            reservation_id=self.reservation_id,
            session_id=self.session_id,
            previous_state=TerminalState.STOPPING.value,
            new_state=TerminalState.COMPLETED.value,
            reason="SESSION_COMPLETED",
        )
        self._mqtt_client.publish(
            f"energy/terminals/{self.terminal_id}/events",
            evt1,
            qos=1,
        )

        # Immediately clear session and return to ACTIVE
        self._clear_session()
        self.state = TerminalState.ACTIVE
        evt2 = build_state_changed(
            terminal_id=self.terminal_id,
            reservation_id=None,
            session_id=None,
            previous_state=TerminalState.COMPLETED.value,
            new_state=TerminalState.ACTIVE.value,
            reason="SESSION_CLEANUP",
        )
        self._mqtt_client.publish(
            f"energy/terminals/{self.terminal_id}/events",
            evt2,
            qos=1,
        )
        self.publish_status()
        return {
            "success": True,
            "terminalId": self.terminal_id,
            "state": self.state.value,
        }

    async def _run_telemetry(self) -> None:
        """Periodic telemetry loop while in RUNNING state."""
        try:
            while True:
                for meter in self.meters.values():
                    meter.tick()
                self._sequence_number += 1
                readings = [m.reading for m in self.meters.values()]
                telemetry = build_meter_readings_telemetry(
                    terminal_id=self.terminal_id,
                    reservation_id=self.reservation_id,
                    session_id=self.session_id,
                    readings_list=readings,
                    sequence_number=self._sequence_number,
                )
                self._mqtt_client.publish(
                    f"energy/terminals/{self.terminal_id}/telemetry",
                    telemetry,
                    qos=0,
                )
                await asyncio.sleep(self._config.TELEMETRY_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"[{self.terminal_id}] Error in telemetry loop: {e}")

    async def _reservation_timeout(self, timeout_s: float) -> None:
        """Wait for card tap; revert to ACTIVE if timed out."""
        try:
            await asyncio.sleep(timeout_s)
            expired_res_id = self.reservation_id
            self._clear_session()
            self.state = TerminalState.ACTIVE
            evt = build_reservation_expired(
                terminal_id=self.terminal_id,
                reservation_id=expired_res_id,
                reason="TIMEOUT",
                timeout_seconds=int(timeout_s),
                state=self.state.value,
            )
            self._mqtt_client.publish(
                f"energy/terminals/{self.terminal_id}/events",
                evt,
                qos=1,
            )
            self.publish_status()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"[{self.terminal_id}] Error in reservation timeout: {e}")

    async def _ack_timeout(self) -> None:
        """Timeout waiting for COMPLETE_SESSION acknowledgement."""
        try:
            await asyncio.sleep(self._config.ACK_TIMEOUT_SECONDS)
            prev_state = self.state.value
            self.state = TerminalState.ERROR
            err_evt = build_error_event(
                terminal_id=self.terminal_id,
                reservation_id=self.reservation_id,
                session_id=self.session_id,
                error_code="ACK_TIMEOUT",
                description="Timeout waiting for COMPLETE_SESSION acknowledgement",
                previous_state=prev_state,
                state=self.state.value,
            )
            self._mqtt_client.publish(
                f"energy/terminals/{self.terminal_id}/events",
                err_evt,
                qos=1,
            )
            self.publish_status()

            await asyncio.sleep(self._config.ERROR_RECOVERY_SECONDS)
            self._clear_session()
            self.state = TerminalState.ACTIVE
            cleared_evt = build_error_cleared(
                terminal_id=self.terminal_id,
                reservation_id=None,
                session_id=None,
                state=self.state.value,
            )
            self._mqtt_client.publish(
                f"energy/terminals/{self.terminal_id}/events",
                cleared_evt,
                qos=1,
            )
            self.publish_status()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"[{self.terminal_id}] Error in ack timeout: {e}")

    def _clear_session(self) -> None:
        """Clear all session data and reset meters."""
        self.reservation_id = None
        self.session_id = None
        self.card_uid = None
        self.requested_services = []
        self._sequence_number = 0
        self._session_start_time = None
        for meter in self.meters.values():
            meter.reset()

        try:
            current_task = asyncio.current_task()
        except RuntimeError:
            current_task = None

        if (
            self._timeout_task
            and not self._timeout_task.done()
            and self._timeout_task is not current_task
        ):
            self._timeout_task.cancel()
            self._timeout_task = None

        if (
            self._telemetry_task
            and not self._telemetry_task.done()
            and self._telemetry_task is not current_task
        ):
            self._telemetry_task.cancel()
            self._telemetry_task = None
