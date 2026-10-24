import uuid
from datetime import datetime, timezone
from typing import List, Optional, Any


def create_envelope(
    message_type: str,
    terminal_id: str,
    reservation_id: Optional[Any],
    session_id: Optional[Any],
    payload: dict,
) -> dict:
    return {
        "messageId": str(uuid.uuid4()),
        "terminalId": terminal_id,
        "reservationId": str(reservation_id) if reservation_id else None,
        "sessionId": str(session_id) if session_id else None,
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "schemaVersion": "1.0",
        "type": message_type,
        "payload": payload,
    }


def send_assign_reservation(
    mqtt_client: Any,
    terminal_id: str,
    reservation_id: Any,
    session_id: Any,
    card_uid: str,
    requested_services: List[str],
    timeout_seconds: int = 120,
) -> dict:
    msg = create_envelope(
        message_type="ASSIGN_RESERVATION",
        terminal_id=terminal_id,
        reservation_id=reservation_id,
        session_id=session_id,
        payload={
            "cardUid": card_uid,
            "requestedServices": requested_services,
            "timeoutSeconds": timeout_seconds,
        },
    )
    topic = f"energy/terminals/{terminal_id}/commands"
    if mqtt_client:
        mqtt_client.publish(topic, msg, qos=1)
    return msg


def send_complete_session(
    mqtt_client: Any,
    terminal_id: str,
    reservation_id: Any,
    session_id: Any,
) -> dict:
    msg = create_envelope(
        message_type="COMPLETE_SESSION",
        terminal_id=terminal_id,
        reservation_id=reservation_id,
        session_id=session_id,
        payload={},
    )
    topic = f"energy/terminals/{terminal_id}/commands"
    if mqtt_client:
        mqtt_client.publish(topic, msg, qos=1)
    return msg
