import pytest
from src.mqtt.handlers import CommandHandler
from src.terminal.manager import TerminalManager
from src.terminal.state_machine import TerminalState


@pytest.fixture
def manager(mock_mqtt_client, config):
    return TerminalManager(mock_mqtt_client, config)


@pytest.fixture
def handler(manager, mock_mqtt_client):
    return CommandHandler(manager, mock_mqtt_client)


@pytest.mark.asyncio
async def test_assign_reservation_command(handler, manager):
    terminal = manager.get_terminal("ST-01")
    assert terminal.state == TerminalState.ACTIVE

    msg = {
        "messageId": "msg-assign-1",
        "terminalId": "ST-01",
        "reservationId": "res-uuid-1",
        "sessionId": "sess-uuid-1",
        "type": "ASSIGN_RESERVATION",
        "payload": {
            "cardUid": "RFID-TEST-1",
            "requestedServices": ["electricity", "gas"],
            "timeoutSeconds": 60,
        },
    }

    await handler.handle_message("energy/terminals/ST-01/commands", msg)

    assert terminal.state == TerminalState.WAITING_FOR_CARD
    assert terminal.reservation_id == "res-uuid-1"
    assert terminal.session_id == "sess-uuid-1"
    assert terminal.card_uid == "RFID-TEST-1"
    assert "msg-assign-1" in handler._processed

    if terminal._timeout_task:
        terminal._timeout_task.cancel()


@pytest.mark.asyncio
async def test_complete_session_command(handler, manager):
    terminal = manager.get_terminal("ST-02")
    await terminal.assign_reservation(
        msg_id="m1",
        reservation_id="r1",
        session_id="s1",
        card_uid="RFID-TAP",
    )
    await terminal.present_card("RFID-TAP")
    await terminal.present_card("RFID-TAP")
    assert terminal.state == TerminalState.STOPPING

    complete_msg = {
        "messageId": "msg-comp-1",
        "terminalId": "ST-02",
        "reservationId": "r1",
        "sessionId": "s1",
        "type": "COMPLETE_SESSION",
        "payload": {},
    }

    await handler.handle_message("energy/terminals/ST-02/commands", complete_msg)

    assert terminal.state == TerminalState.ACTIVE
    assert terminal.session_id is None
    assert "msg-comp-1" in handler._processed


@pytest.mark.asyncio
async def test_duplicate_message_ignored(handler, manager):
    terminal = manager.get_terminal("ST-01")
    msg = {
        "messageId": "dup-msg-id",
        "terminalId": "ST-01",
        "reservationId": "res-dup",
        "sessionId": "sess-dup",
        "type": "ASSIGN_RESERVATION",
        "payload": {
            "cardUid": "RFID-DUP",
        },
    }

    # First delivery
    await handler.handle_message("energy/terminals/ST-01/commands", msg)
    assert terminal.state == TerminalState.WAITING_FOR_CARD
    if terminal._timeout_task:
        terminal._timeout_task.cancel()

    # Artificially set state back to ACTIVE to test if duplicate message is ignored
    terminal.state = TerminalState.ACTIVE
    terminal.reservation_id = None

    # Second delivery (duplicate)
    await handler.handle_message("energy/terminals/ST-01/commands", msg)
    # Because it is a duplicate, state should NOT have changed to WAITING_FOR_CARD
    assert terminal.state == TerminalState.ACTIVE
    assert terminal.reservation_id is None


@pytest.mark.asyncio
async def test_unknown_terminal_ignored(handler):
    msg = {
        "messageId": "unknown-msg",
        "terminalId": "UNKNOWN-99",
        "type": "ASSIGN_RESERVATION",
        "payload": {},
    }
    # Should not raise exception
    await handler.handle_message("energy/terminals/UNKNOWN-99/commands", msg)
