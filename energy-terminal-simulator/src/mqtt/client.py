import asyncio
from datetime import datetime, timezone
import json
import logging
from typing import Any, Callable

import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)


def _utc_now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class MQTTClient:
    def __init__(self, config: Any, loop: asyncio.AbstractEventLoop):
        self._loop = loop
        self._config = config
        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id="borne-simulator",
            protocol=mqtt.MQTTv311,
        )
        # LWT: Last Will & Testament
        self._client.will_set(
            topic="energy/simulator/status",
            payload=json.dumps({"state": "OFFLINE", "timestamp": _utc_now_str()}),
            qos=1,
            retain=True,
        )
        self._client.reconnect_delay_set(1, 30)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.on_disconnect = self._on_disconnect
        self._message_handler: Callable[..., Any] | None = None

    def set_message_handler(self, handler: Callable[..., Any]) -> None:
        self._message_handler = handler

    def connect(self) -> None:
        try:
            self._client.connect(
                self._config.MQTT_BROKER_HOST,
                self._config.MQTT_BROKER_PORT,
            )
            self._client.loop_start()
            logger.info(
                f"Connecting to MQTT broker at {self._config.MQTT_BROKER_HOST}:{self._config.MQTT_BROKER_PORT}"
            )
        except Exception as e:
            logger.error(f"Failed to connect to MQTT broker: {e}")

    def disconnect(self) -> None:
        try:
            self.publish(
                "energy/simulator/status",
                {"state": "OFFLINE", "timestamp": _utc_now_str()},
                qos=1,
                retain=True,
            )
            self._client.loop_stop()
            self._client.disconnect()
            logger.info("MQTT client disconnected successfully")
        except Exception as e:
            logger.error(f"Error during MQTT disconnect: {e}")

    def publish(
        self,
        topic: str,
        payload_dict: dict | list | str,
        qos: int = 0,
        retain: bool = False,
    ) -> None:
        try:
            payload = (
                json.dumps(payload_dict)
                if isinstance(payload_dict, (dict, list))
                else str(payload_dict)
            )
            self._client.publish(topic, payload, qos=qos, retain=retain)
        except Exception as e:
            logger.error(f"Failed to publish to {topic}: {e}")

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        if reason_code == 0:
            logger.info("MQTT connected successfully")
            client.subscribe("energy/terminals/+/commands", qos=1)
            # Publish simulator online status
            self.publish(
                "energy/simulator/status",
                {"state": "ONLINE", "timestamp": _utc_now_str()},
                qos=1,
                retain=True,
            )
        else:
            logger.warning(f"MQTT connection failed with reason_code: {reason_code}")

    def _on_message(self, client, userdata, msg) -> None:
        if self._message_handler:
            try:
                raw_payload = msg.payload
                if isinstance(raw_payload, (bytes, bytearray)):
                    raw_payload = raw_payload.decode("utf-8")
                data = json.loads(raw_payload)
                asyncio.run_coroutine_threadsafe(
                    self._message_handler(msg.topic, data), self._loop
                )
            except Exception as e:
                logger.error(f"Error processing MQTT message: {e}")

    def _on_disconnect(self, client, userdata, flags, reason_code, properties) -> None:
        logger.warning(f"MQTT disconnected: {reason_code}. Auto-reconnecting...")
