import uuid
import pytest
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.models import Terminal, Reservation, Session, MeterReading, Invoice, ProcessedMessage
from src.mqtt.handlers import EventHandler


@pytest.mark.asyncio
async def test_session_started_handler(session_factory, mock_mqtt_client):
    handler = EventHandler(session_factory, mock_mqtt_client)

    sess_id = uuid.uuid4()
    res_id = uuid.uuid4()

    async with session_factory() as db:
        db.add(Terminal(id="ST-01", status="OCCUPIED", current_session_id=str(sess_id)))
        db.add(Reservation(
            id=res_id,
            customer_name="Test",
            card_uid="RFID-01",
            requested_services=["electricity"],
            status="ASSIGNED",
            assigned_terminal_id="ST-01",
            session_id=sess_id,
            expires_at=datetime.now(timezone.utc),
        ))
        db.add(Session(
            id=sess_id,
            terminal_id="ST-01",
            reservation_id=res_id,
            status="STARTED",
        ))
        await db.commit()

    msg = {
        "messageId": str(uuid.uuid4()),
        "terminalId": "ST-01",
        "reservationId": str(res_id),
        "sessionId": str(sess_id),
        "timestamp": "2026-10-24T10:00:00Z",
        "schemaVersion": "1.0",
        "type": "SESSION_STARTED",
        "payload": {"activeMeters": ["electricity"], "state": "RUNNING"},
    }

    await handler.handle_message("energy/terminals/ST-01/events", msg)

    async with session_factory() as db:
        sess = await db.get(Session, sess_id)
        assert sess.status == "RUNNING"
        res = await db.get(Reservation, res_id)
        assert res.status == "IN_PROGRESS"


@pytest.mark.asyncio
async def test_final_readings_handler_triggers_billing(session_factory, mock_mqtt_client):
    handler = EventHandler(session_factory, mock_mqtt_client)

    sess_id = uuid.uuid4()
    res_id = uuid.uuid4()

    async with session_factory() as db:
        from src.db.seed import seed_database
        await seed_database(db)

        db.add(Reservation(
            id=res_id,
            customer_name="Ahmed",
            card_uid="RFID-A1",
            requested_services=["electricity", "water", "gas"],
            status="IN_PROGRESS",
            assigned_terminal_id="ST-01",
            session_id=sess_id,
            expires_at=datetime.now(timezone.utc),
        ))
        db.add(Session(
            id=sess_id,
            terminal_id="ST-01",
            reservation_id=res_id,
            status="RUNNING",
        ))
        await db.commit()

    msg = {
        "messageId": str(uuid.uuid4()),
        "terminalId": "ST-01",
        "reservationId": str(res_id),
        "sessionId": str(sess_id),
        "timestamp": "2026-10-24T10:05:00Z",
        "schemaVersion": "1.0",
        "type": "FINAL_READINGS",
        "payload": {
            "readings": [
                {"meterType": "electricity", "value": 12.450, "unit": "kWh"},
                {"meterType": "water", "value": 2.380, "unit": "m3"},
                {"meterType": "gas", "value": 18.700, "unit": "thermie"},
            ],
            "sessionDurationSeconds": 300,
            "state": "STOPPING",
        },
    }

    await handler.handle_message("energy/terminals/ST-01/events", msg)

    async with session_factory() as db:
        # Check session is COMPLETED
        sess = await db.get(Session, sess_id)
        assert sess.status == "COMPLETED"

        # Check invoice was calculated and stored
        inv_stmt = select(Invoice).where(Invoice.session_id == sess_id)
        inv_res = await db.execute(inv_stmt)
        invoice = inv_res.scalar_one_or_none()
        assert invoice is not None
        assert float(invoice.total_amount) == 5.492

    # Check COMPLETE_SESSION command sent back to terminal
    assert len(mock_mqtt_client.published_messages) >= 1
    topic, payload, qos, _ = mock_mqtt_client.published_messages[-1]
    assert topic == "energy/terminals/ST-01/commands"
    assert payload["type"] == "COMPLETE_SESSION"


@pytest.mark.asyncio
async def test_duplicate_message_ignored(session_factory, mock_mqtt_client):
    handler = EventHandler(session_factory, mock_mqtt_client)
    msg_id = str(uuid.uuid4())

    msg = {
        "messageId": msg_id,
        "terminalId": "ST-01",
        "reservationId": None,
        "sessionId": None,
        "timestamp": "2026-10-24T10:00:00Z",
        "schemaVersion": "1.0",
        "type": "COMMAND_ACK",
        "payload": {"success": True},
    }

    # First delivery
    await handler.handle_message("energy/terminals/ST-01/events", msg)

    async with session_factory() as db:
        rec = await db.get(ProcessedMessage, msg_id)
        assert rec is not None

    # Second delivery should be ignored safely
    await handler.handle_message("energy/terminals/ST-01/events", msg)


@pytest.mark.asyncio
async def test_telemetry_upsert(session_factory, mock_mqtt_client):
    handler = EventHandler(session_factory, mock_mqtt_client)
    sess_id = uuid.uuid4()

    msg1 = {
        "messageId": str(uuid.uuid4()),
        "terminalId": "ST-01",
        "reservationId": None,
        "sessionId": str(sess_id),
        "timestamp": "2026-10-24T10:00:03Z",
        "schemaVersion": "1.0",
        "type": "METER_READINGS",
        "payload": {
            "readings": [
                {"meterType": "electricity", "value": 0.200, "unit": "kWh"},
            ]
        },
    }
    await handler.handle_message("energy/terminals/ST-01/telemetry", msg1)

    async with session_factory() as db:
        r1 = (await db.execute(select(MeterReading).where(MeterReading.session_id == sess_id))).scalars().all()
        assert len(r1) == 1
        assert float(r1[0].cumulative_value) == 0.200

    # Next telemetry tick updates value rather than accumulating unlimited rows
    msg2 = {
        "messageId": str(uuid.uuid4()),
        "terminalId": "ST-01",
        "reservationId": None,
        "sessionId": str(sess_id),
        "timestamp": "2026-10-24T10:00:06Z",
        "schemaVersion": "1.0",
        "type": "METER_READINGS",
        "payload": {
            "readings": [
                {"meterType": "electricity", "value": 0.450, "unit": "kWh"},
            ]
        },
    }
    await handler.handle_message("energy/terminals/ST-01/telemetry", msg2)

    async with session_factory() as db:
        r2 = (await db.execute(select(MeterReading).where(MeterReading.session_id == sess_id))).scalars().all()
        assert len(r2) == 1
        assert float(r2[0].cumulative_value) == 0.450
