import uuid
from datetime import datetime, timezone
from typing import Any


def _get_timestamp() -> str:
    """Generate ISO-8601 UTC timestamp with millisecond precision (e.g. 2026-10-20T22:30:00.000Z)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _create_envelope(
    terminal_id: str,
    reservation_id: str | None,
    session_id: str | None,
    msg_type: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Helper to wrap any payload into standard message envelope."""
    return {
        "messageId": str(uuid.uuid4()),
        "terminalId": terminal_id,
        "reservationId": reservation_id,
        "sessionId": session_id,
        "timestamp": _get_timestamp(),
        "schemaVersion": "1.0",
        "type": msg_type,
        "payload": payload,
    }


def build_command_ack(
    terminal_id: str,
    reservation_id: str | None,
    session_id: str | None,
    acked_message_id: str,
    command_type: str,
    success: bool,
    new_state: str,
) -> dict[str, Any]:
    return _create_envelope(
        terminal_id=terminal_id,
        reservation_id=reservation_id,
        session_id=session_id,
        msg_type="COMMAND_ACK",
        payload={
            "ackedMessageId": acked_message_id,
            "commandType": command_type,
            "success": success,
            "newState": new_state,
        },
    )


def build_session_started(
    terminal_id: str,
    reservation_id: str | None,
    session_id: str | None,
    active_meters: list[str],
    state: str = "RUNNING",
) -> dict[str, Any]:
    return _create_envelope(
        terminal_id=terminal_id,
        reservation_id=reservation_id,
        session_id=session_id,
        msg_type="SESSION_STARTED",
        payload={
            "activeMeters": active_meters,
            "state": state,
        },
    )


def build_final_readings(
    terminal_id: str,
    reservation_id: str | None,
    session_id: str | None,
    readings_list: list[dict[str, Any]],
    session_duration_seconds: int,
    state: str = "STOPPING",
) -> dict[str, Any]:
    return _create_envelope(
        terminal_id=terminal_id,
        reservation_id=reservation_id,
        session_id=session_id,
        msg_type="FINAL_READINGS",
        payload={
            "readings": readings_list,
            "sessionDurationSeconds": session_duration_seconds,
            "state": state,
        },
    )


def build_card_rejected(
    terminal_id: str,
    reservation_id: str | None,
    presented_card_uid: str,
    reason: str = "CARD_UID_MISMATCH",
    state: str = "WAITING_FOR_CARD",
) -> dict[str, Any]:
    return _create_envelope(
        terminal_id=terminal_id,
        reservation_id=reservation_id,
        session_id=None,
        msg_type="CARD_REJECTED",
        payload={
            "presentedCardUid": presented_card_uid,
            "reason": reason,
            "state": state,
        },
    )


def build_reservation_expired(
    terminal_id: str,
    reservation_id: str | None,
    reason: str = "TIMEOUT",
    timeout_seconds: int = 120,
    state: str = "ACTIVE",
) -> dict[str, Any]:
    return _create_envelope(
        terminal_id=terminal_id,
        reservation_id=reservation_id,
        session_id=None,
        msg_type="RESERVATION_EXPIRED",
        payload={
            "reason": reason,
            "timeoutSeconds": timeout_seconds,
            "state": state,
        },
    )


def build_state_changed(
    terminal_id: str,
    reservation_id: str | None,
    session_id: str | None,
    previous_state: str,
    new_state: str,
    reason: str,
) -> dict[str, Any]:
    return _create_envelope(
        terminal_id=terminal_id,
        reservation_id=reservation_id,
        session_id=session_id,
        msg_type="STATE_CHANGED",
        payload={
            "previousState": previous_state,
            "newState": new_state,
            "reason": reason,
        },
    )


def build_error_event(
    terminal_id: str,
    reservation_id: str | None,
    session_id: str | None,
    error_code: str,
    description: str,
    previous_state: str,
    state: str = "ERROR",
) -> dict[str, Any]:
    return _create_envelope(
        terminal_id=terminal_id,
        reservation_id=reservation_id,
        session_id=session_id,
        msg_type="ERROR",
        payload={
            "errorCode": error_code,
            "description": description,
            "previousState": previous_state,
            "state": state,
        },
    )


def build_error_cleared(
    terminal_id: str,
    reservation_id: str | None = None,
    session_id: str | None = None,
    state: str = "ACTIVE",
) -> dict[str, Any]:
    return _create_envelope(
        terminal_id=terminal_id,
        reservation_id=reservation_id,
        session_id=session_id,
        msg_type="ERROR_CLEARED",
        payload={
            "state": state,
            "reason": "AUTO_RECOVERY",
        },
    )


def build_meter_readings_telemetry(
    terminal_id: str,
    reservation_id: str | None,
    session_id: str | None,
    readings_list: list[dict[str, Any]],
    sequence_number: int,
) -> dict[str, Any]:
    return _create_envelope(
        terminal_id=terminal_id,
        reservation_id=reservation_id,
        session_id=session_id,
        msg_type="METER_READINGS",
        payload={
            "readings": readings_list,
            "sequenceNumber": sequence_number,
        },
    )


def build_status(
    terminal_id: str,
    state: str,
    session_id: str | None = None,
    reservation_id: str | None = None,
) -> dict[str, Any]:
    """Retained status payload."""
    return {
        "terminalId": terminal_id,
        "state": state,
        "sessionId": session_id,
        "reservationId": reservation_id,
        "timestamp": _get_timestamp(),
    }
