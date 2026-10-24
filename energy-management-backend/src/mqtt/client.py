import json
import logging
import asyncio
from typing import Optional, Callable, Any
import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)


class MQTTClient:
    def __init__(self, config: Any, loop: asyncio.AbstractEventLoop):
        self._loop = loop
        self._config = config
        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id="borne-backend",
            protocol=mqtt.MQTTv311,
            clean_session=False,
        )
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.on_disconnect = self._on_disconnect
        self._message_handler: Optional[Callable] = None

    def set_message_handler(self, handler: Callable):
        self._message_handler = handler

    def connect(self):
        try:
            self._client.connect(
                self._config.MQTT_BROKER_HOST,
                self._config.MQTT_BROKER_PORT,
                keepalive=60,
            )
            self._client.loop_start()
            logger.info(f"Connecting to MQTT broker at {self._config.MQTT_BROKER_HOST}:{self._config.MQTT_BROKER_PORT}...")
        except Exception as e:
            logger.warning(f"Could not connect immediately to MQTT broker: {e}. Will retry.")

    def disconnect(self):
        try:
            self._client.loop_stop()
            self._client.disconnect()
            logger.info("Disconnected from MQTT broker.")
        except Exception as e:
            logger.error(f"Error disconnecting MQTT: {e}")

    def publish(self, topic: str, payload_dict: dict, qos: int = 0, retain: bool = False):
        try:
            payload = json.dumps(payload_dict)
            self._client.publish(topic, payload, qos=qos, retain=retain)
        except Exception as e:
            logger.error(f"Failed to publish to {topic}: {e}")

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code == 0:
            logger.info("Connected to MQTT broker successfully.")
            client.subscribe("energy/terminals/+/events", qos=1)
            client.subscribe("energy/terminals/+/telemetry", qos=0)
            client.subscribe("energy/terminals/+/status", qos=1)
            client.subscribe("energy/simulator/status", qos=1)
            logger.info("Subscribed to terminal topics.")
        else:
            logger.error(f"MQTT connection failed with code {reason_code}")

    def _on_message(self, client, userdata, msg):
        if self._message_handler:
            try:
                data = json.loads(msg.payload.decode("utf-8"))
                asyncio.run_coroutine_threadsafe(
                    self._message_handler(msg.topic, data), self._loop
                )
            except Exception as e:
                logger.error(f"Error handling MQTT message on topic {msg.topic}: {e}")

    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        logger.warning(f"MQTT disconnected with reason {reason_code}. Reconnecting...")
