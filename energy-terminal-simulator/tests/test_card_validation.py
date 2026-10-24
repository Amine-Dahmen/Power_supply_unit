import pytest
from src.terminal.state_machine import TerminalState


@pytest.mark.asyncio
async def test_valid_card_accepted(terminal):
    await terminal.assign_reservation(
        msg_id="msg-1",
        reservation_id="res-1",
        session_id="sess-1",
        card_uid="CARD-OK",
    )
    result = await terminal.present_card("CARD-OK")
    assert result["success"] is True
    assert terminal.state == TerminalState.RUNNING

    if terminal._telemetry_task:
        terminal._telemetry_task.cancel()


@pytest.mark.asyncio
async def test_invalid_card_rejected(terminal, mock_mqtt_client):
    await terminal.assign_reservation(
        msg_id="msg-1",
        reservation_id="res-1",
        session_id="sess-1",
        card_uid="CARD-OK",
    )
    result = await terminal.present_card("CARD-BAD")
    assert result["success"] is False
    assert result["reason"] == "CARD_UID_MISMATCH"
    assert terminal.state == TerminalState.WAITING_FOR_CARD

    rejections = mock_mqtt_client.get_messages_by_type("CARD_REJECTED")
    assert len(rejections) == 1
    assert rejections[0].payload["payload"]["presentedCardUid"] == "CARD-BAD"


@pytest.mark.asyncio
async def test_card_in_active_state_rejected(terminal):
    assert terminal.state == TerminalState.ACTIVE
    result = await terminal.present_card("ANY-CARD")
    assert result["success"] is False
    assert "Invalid terminal state" in result["reason"]
    assert terminal.state == TerminalState.ACTIVE
