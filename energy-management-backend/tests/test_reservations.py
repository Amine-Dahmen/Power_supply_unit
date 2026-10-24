import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.models import Terminal, Reservation, Session
from src.api.schemas import CreateReservationRequest
from src.services.reservation_svc import (
    create_reservation,
    cancel_reservation,
    NoTerminalAvailableError,
    InvalidServicesError,
)


@pytest.mark.asyncio
async def test_create_reservation_assigns_terminal(seeded_db: AsyncSession, mock_mqtt_client):
    req = CreateReservationRequest(
        customer_name="Ali Trabelsi",
        card_uid="RFID-TEST-01",
        requested_services=["electricity", "water"],
    )

    res = await create_reservation(seeded_db, req, mqtt_client=mock_mqtt_client)
    assert res.id is not None
    assert res.assigned_terminal_id == "ST-01"
    assert res.status == "ASSIGNED"
    assert res.session_id is not None

    # Check terminal updated to OCCUPIED
    term = await seeded_db.get(Terminal, "ST-01")
    assert term.status == "OCCUPIED"
    assert term.current_session_id == str(res.session_id)

    # Check Session created
    sess = await seeded_db.get(Session, res.session_id)
    assert sess is not None
    assert sess.status == "STARTED"

    # Check MQTT command sent
    assert len(mock_mqtt_client.published_messages) == 1
    topic, payload, qos, _ = mock_mqtt_client.published_messages[0]
    assert topic == "energy/terminals/ST-01/commands"
    assert payload["type"] == "ASSIGN_RESERVATION"
    assert payload["payload"]["cardUid"] == "RFID-TEST-01"


@pytest.mark.asyncio
async def test_no_terminals_available(seeded_db: AsyncSession, mock_mqtt_client):
    # Occupy all terminals
    terms_res = await seeded_db.execute(select(Terminal))
    for t in terms_res.scalars().all():
        t.status = "OCCUPIED"
    await seeded_db.commit()

    req = CreateReservationRequest(
        customer_name="Sami",
        card_uid="RFID-SAMI",
        requested_services=["electricity"],
    )

    with pytest.raises(NoTerminalAvailableError):
        await create_reservation(seeded_db, req, mqtt_client=mock_mqtt_client)


@pytest.mark.asyncio
async def test_invalid_requested_services(seeded_db: AsyncSession, mock_mqtt_client):
    req = CreateReservationRequest(
        customer_name="Test",
        card_uid="RFID-XYZ",
        requested_services=["invalid_service"],
    )

    with pytest.raises(InvalidServicesError):
        await create_reservation(seeded_db, req, mqtt_client=mock_mqtt_client)


@pytest.mark.asyncio
async def test_cancel_reservation(seeded_db: AsyncSession, mock_mqtt_client):
    req = CreateReservationRequest(
        customer_name="Mounir",
        card_uid="RFID-MOUNIR",
        requested_services=["electricity"],
    )
    res = await create_reservation(seeded_db, req, mqtt_client=mock_mqtt_client)
    assert res.status == "ASSIGNED"

    cancelled = await cancel_reservation(seeded_db, res.id, mqtt_client=mock_mqtt_client)
    assert cancelled is not None
    assert cancelled.status == "CANCELLED"

    # Terminal should be back to ACTIVE
    term = await seeded_db.get(Terminal, res.assigned_terminal_id)
    assert term.status == "ACTIVE"
    assert term.current_session_id is None
