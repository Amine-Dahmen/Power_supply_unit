import asyncio
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI

from src.api.routes import router
from src.config import get_settings
from src.mqtt.client import MQTTClient
from src.mqtt.handlers import CommandHandler
from src.terminal.manager import TerminalManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("simulator")


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = get_settings()
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.get_event_loop()
    mqtt_client = MQTTClient(config, loop)
    manager = TerminalManager(mqtt_client, config)
    handler = CommandHandler(manager, mqtt_client)
    mqtt_client.set_message_handler(handler.handle_message)
    mqtt_client.connect()
    await manager.start()
    app.state.manager = manager
    app.state.mqtt_client = mqtt_client
    logger.info("Simulator started with terminals: ST-01, ST-02, ST-03")
    yield
    mqtt_client.disconnect()
    logger.info("Simulator shut down")


app = FastAPI(title="Energy Terminal Simulator", version="1.0.0", lifespan=lifespan)
app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok"}
