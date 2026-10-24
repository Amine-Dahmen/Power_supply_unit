import pytest
from httpx import ASGITransport, AsyncClient

from src.config import Settings
from src.main import app
from src.terminal.manager import TerminalManager
from tests.conftest import MockMQTTClient


@pytest.mark.asyncio
async def test_health_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_api_list_and_card_tap():
    mock_mqtt = MockMQTTClient()
    config = Settings(
        TELEMETRY_INTERVAL_SECONDS=0.05,
        RESERVATION_TIMEOUT_SECONDS=5,
        ACK_TIMEOUT_SECONDS=1,
        ERROR_RECOVERY_SECONDS=1,
        RANDOM_SEED=42,
    )
    manager = TerminalManager(mock_mqtt, config)
    app.state.manager = manager
    app.state.mqtt_client = mock_mqtt

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Test GET /terminals
        res = await client.get("/terminals")
        assert res.status_code == 200
        terminals = res.json()
        assert len(terminals) == 3
        assert {t["terminalId"] for t in terminals} == {"ST-01", "ST-02", "ST-03"}

        # Test GET /terminals/ST-01
        res = await client.get("/terminals/ST-01")
        assert res.status_code == 200
        data = res.json()
        assert data["terminalId"] == "ST-01"
        assert data["state"] == "ACTIVE"
        assert "meters" in data

        # Assign reservation to ST-01
        st01 = manager.get_terminal("ST-01")
        await st01.assign_reservation(
            msg_id="api-test-m1",
            reservation_id="res-api-1",
            session_id="sess-api-1",
            card_uid="RFID-CARD-1",
        )

        # Tap wrong card -> 400
        res = await client.post(
            "/terminals/ST-01/card",
            json={"cardUid": "WRONG"},
        )
        assert res.status_code == 400

        # Tap valid card -> 200
        res = await client.post(
            "/terminals/ST-01/card",
            json={"cardUid": "RFID-CARD-1"},
        )
        assert res.status_code == 200
        assert res.json()["state"] == "RUNNING"

        # Stop telemetry task
        if st01._telemetry_task:
            st01._telemetry_task.cancel()
