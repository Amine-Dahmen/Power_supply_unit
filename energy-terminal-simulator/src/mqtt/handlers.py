import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class CommandHandler:
    def __init__(self, terminal_manager: Any, mqtt_client: Any):
        self.manager = terminal_manager
        self.mqtt = mqtt_client
        self._processed: dict[str, float] = {}  # messageId -> timestamp

    async def handle_message(self, topic: str, data: dict) -> None:
        msg_id = data.get("messageId")
        # Idempotency check
        if msg_id and msg_id in self._processed:
            logger.info(f"Duplicate message {msg_id}, ignoring")
            return

        # Prune old entries (>10 min)
        self._prune()

        # Extract terminalId from topic: energy/terminals/{id}/commands
        parts = topic.split("/")
        terminal_id = parts[2] if len(parts) >= 4 else data.get("terminalId")
        terminal = self.manager.get_terminal(terminal_id)
        if not terminal:
            logger.warning(f"Terminal {terminal_id} not found")
            return

        msg_type = data.get("type")
        if msg_type == "ASSIGN_RESERVATION":
            payload = data.get("payload", {})
            await terminal.assign_reservation(
                msg_id=msg_id,
                reservation_id=data.get("reservationId"),
                session_id=data.get("sessionId"),
                card_uid=payload.get("cardUid"),
                services=payload.get("requestedServices", []),
                timeout_s=payload.get("timeoutSeconds", 120),
            )
        elif msg_type == "COMPLETE_SESSION":
            await terminal.complete_session(data.get("sessionId"))

        # Mark as processed
        if msg_id:
            self._processed[msg_id] = time.time()

    def _prune(self) -> None:
        cutoff = time.time() - 600
        self._processed = {k: v for k, v in self._processed.items() if v > cutoff}
