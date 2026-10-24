from dataclasses import dataclass, field
from typing import Any
import pytest

from src.config import Settings
from src.terminal.meter import Meter
from src.terminal.state_machine import Terminal


@dataclass
class PublishedMessage:
    topic: str
    payload: Any
    qos: int
    retain: bool


class MockMQTTClient:
    def __init__(self):
        self.published: list[PublishedMessage] = []

    def publish(
        self,
        topic: str,
        payload_dict: Any,
        qos: int = 0,
        retain: bool = False,
    ) -> None:
        self.published.append(
            PublishedMessage(topic=topic, payload=payload_dict, qos=qos, retain=retain)
        )

    def clear(self) -> None:
        self.published.clear()

    def get_messages_by_topic(self, topic: str) -> list[PublishedMessage]:
        return [m for m in self.published if m.topic == topic]

    def get_messages_by_type(self, msg_type: str) -> list[PublishedMessage]:
        results = []
        for m in self.published:
            if isinstance(m.payload, dict) and m.payload.get("type") == msg_type:
                results.append(m)
        return results

    @property
    def last_message(self) -> PublishedMessage | None:
        return self.published[-1] if self.published else None


@pytest.fixture
def mock_mqtt_client():
    return MockMQTTClient()


@pytest.fixture
def config():
    return Settings(
        MQTT_BROKER_HOST="localhost",
        MQTT_BROKER_PORT=1883,
        SIMULATOR_PORT=8001,
        TELEMETRY_INTERVAL_SECONDS=0.05,
        RESERVATION_TIMEOUT_SECONDS=1,
        ACK_TIMEOUT_SECONDS=1,
        ERROR_RECOVERY_SECONDS=1,
        RANDOM_SEED=42,
    )


@pytest.fixture
def terminal(mock_mqtt_client, config):
    return Terminal("ST-01", mock_mqtt_client, config)


@pytest.fixture
def meter():
    return Meter(
        meter_type="electricity",
        unit="kWh",
        increment_min=0.05,
        increment_max=0.25,
    )
