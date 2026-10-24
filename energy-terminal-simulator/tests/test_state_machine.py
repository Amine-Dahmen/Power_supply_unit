import asyncio
import pytest

from src.terminal.state_machine import TerminalState


@pytest.mark.asyncio
async def test_initial_state_is_active(terminal):
    assert terminal.state == TerminalState.ACTIVE
    assert terminal.reservation_id is None
    assert terminal.session_id is None
    assert terminal.card_uid is None
    for meter in terminal.meters.values():
        assert meter.cumulative_value == 0.0


@pytest.mark.asyncio
async def test_assign_reservation_transitions_to_waiting(terminal, mock_mqtt_client):
    res = await terminal.assign_reservation(
        msg_id="msg-1",
        reservation_id="res-1",
        session_id="sess-1",
        card_uid="RFID-1234",
        services=["electricity", "water"],
        timeout_s=5,
    )
    assert res["success"] is True
    assert terminal.state == TerminalState.WAITING_FOR_CARD
    assert terminal.reservation_id == "res-1"
    assert terminal.session_id == "sess-1"
    assert terminal.card_uid == "RFID-1234"

    # Check MQTT publications: COMMAND_ACK and retained status
    acks = mock_mqtt_client.get_messages_by_type("COMMAND_ACK")
    assert len(acks) == 1
    assert acks[0].payload["payload"]["ackedMessageId"] == "msg-1"
    assert acks[0].payload["payload"]["newState"] == "WAITING_FOR_CARD"

    status_msgs = mock_mqtt_client.get_messages_by_topic(
        f"energy/terminals/{terminal.terminal_id}/status"
    )
    assert len(status_msgs) >= 1
    assert status_msgs[-1].payload["state"] == "WAITING_FOR_CARD"


@pytest.mark.asyncio
async def test_assign_reservation_fails_if_not_active(terminal):
    await terminal.assign_reservation(
        msg_id="msg-1",
        reservation_id="res-1",
        session_id="sess-1",
        card_uid="RFID-1234",
    )
    # Attempt second assignment while in WAITING_FOR_CARD
    res2 = await terminal.assign_reservation(
        msg_id="msg-2",
        reservation_id="res-2",
        session_id="sess-2",
        card_uid="RFID-5678",
    )
    assert res2["success"] is False
    assert "not in ACTIVE state" in res2["reason"]
    assert terminal.reservation_id == "res-1"


@pytest.mark.asyncio
async def test_present_valid_card_starts_session(terminal, mock_mqtt_client):
    await terminal.assign_reservation(
        msg_id="msg-1",
        reservation_id="res-1",
        session_id="sess-1",
        card_uid="RFID-1234",
    )
    res = await terminal.present_card("RFID-1234")
    assert res["success"] is True
    assert terminal.state == TerminalState.RUNNING

    # Verify SESSION_STARTED event published
    events = mock_mqtt_client.get_messages_by_type("SESSION_STARTED")
    assert len(events) == 1
    assert events[0].payload["payload"]["state"] == "RUNNING"
    assert set(events[0].payload["payload"]["activeMeters"]) == {
        "electricity",
        "water",
        "gas",
    }

    # Verify telemetry loop ticks meters
    await asyncio.sleep(0.12)
    telemetry = mock_mqtt_client.get_messages_by_type("METER_READINGS")
    assert len(telemetry) >= 1

    # Clean up telemetry task
    if terminal._telemetry_task:
        terminal._telemetry_task.cancel()


@pytest.mark.asyncio
async def test_present_wrong_card_rejected(terminal, mock_mqtt_client):
    await terminal.assign_reservation(
        msg_id="msg-1",
        reservation_id="res-1",
        session_id="sess-1",
        card_uid="RFID-CORRECT",
    )
    res = await terminal.present_card("RFID-WRONG")
    assert res["success"] is False
    assert res["reason"] == "CARD_UID_MISMATCH"
    assert terminal.state == TerminalState.WAITING_FOR_CARD

    # Verify CARD_REJECTED event
    events = mock_mqtt_client.get_messages_by_type("CARD_REJECTED")
    assert len(events) == 1
    assert events[0].payload["payload"]["presentedCardUid"] == "RFID-WRONG"


@pytest.mark.asyncio
async def test_second_card_stops_session(terminal, mock_mqtt_client):
    await terminal.assign_reservation(
        msg_id="msg-1",
        reservation_id="res-1",
        session_id="sess-1",
        card_uid="RFID-1234",
    )
    # First tap
    await terminal.present_card("RFID-1234")
    assert terminal.state == TerminalState.RUNNING

    # Allow a quick tick
    await asyncio.sleep(0.06)

    # Second tap
    res = await terminal.present_card("RFID-1234")
    assert res["success"] is True
    assert terminal.state == TerminalState.STOPPING
    assert "readings" in res
    assert len(res["readings"]) == 3

    # Verify FINAL_READINGS event
    final_events = mock_mqtt_client.get_messages_by_type("FINAL_READINGS")
    assert len(final_events) == 1
    assert final_events[0].payload["payload"]["state"] == "STOPPING"
    assert len(final_events[0].payload["payload"]["readings"]) == 3

    # Clean up ack timeout task
    if terminal._timeout_task:
        terminal._timeout_task.cancel()


@pytest.mark.asyncio
async def test_complete_session_returns_to_active(terminal, mock_mqtt_client):
    await terminal.assign_reservation(
        msg_id="msg-1",
        reservation_id="res-1",
        session_id="sess-1",
        card_uid="RFID-1234",
    )
    await terminal.present_card("RFID-1234")
    await terminal.present_card("RFID-1234")
    assert terminal.state == TerminalState.STOPPING

    # Backend sends COMPLETE_SESSION
    res = await terminal.complete_session("sess-1")
    assert res["success"] is True
    assert terminal.state == TerminalState.ACTIVE
    assert terminal.reservation_id is None
    assert terminal.session_id is None
    assert terminal.card_uid is None

    # Check meters are reset
    for meter in terminal.meters.values():
        assert meter.cumulative_value == 0.0

    # Verify STATE_CHANGED events
    state_events = mock_mqtt_client.get_messages_by_type("STATE_CHANGED")
    assert len(state_events) == 2
    assert state_events[0].payload["payload"]["newState"] == "COMPLETED"
    assert state_events[1].payload["payload"]["newState"] == "ACTIVE"


@pytest.mark.asyncio
async def test_reservation_timeout_returns_to_active(terminal, mock_mqtt_client):
    await terminal.assign_reservation(
        msg_id="msg-1",
        reservation_id="res-1",
        session_id="sess-1",
        card_uid="RFID-1234",
        timeout_s=0.05,
    )
    assert terminal.state == TerminalState.WAITING_FOR_CARD

    # Wait for timeout to expire
    await asyncio.sleep(0.08)

    assert terminal.state == TerminalState.ACTIVE
    assert terminal.reservation_id is None
    assert terminal.session_id is None

    # Verify RESERVATION_EXPIRED event
    expired_events = mock_mqtt_client.get_messages_by_type("RESERVATION_EXPIRED")
    assert len(expired_events) == 1
    assert expired_events[0].payload["payload"]["reason"] == "TIMEOUT"
