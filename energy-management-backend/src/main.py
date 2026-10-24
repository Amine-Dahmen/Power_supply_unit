import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from src.config import get_settings
from src.db.session import init_db
from src.db.seed import seed_database
from src.mqtt.client import MQTTClient
from src.mqtt.handlers import EventHandler
from src.api.routers import terminals, reservations, sessions, billing

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("backend")


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = get_settings()

    # 1. Database setup
    engine, session_factory = init_db(config.DATABASE_URL)
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.config = config

    # 2. Run Alembic migrations (when connected to PostgreSQL)
    if "postgresql" in config.DATABASE_URL:
        try:
            from alembic.config import Config as AlembicConfig
            from alembic import command
            alembic_cfg = AlembicConfig("alembic.ini")
            alembic_cfg.set_main_option("sqlalchemy.url", config.database_url_sync)
            command.upgrade(alembic_cfg, "head")
            logger.info("Alembic migrations completed successfully.")
        except Exception as e:
            logger.warning(f"Alembic migration warning: {e}. Ensuring tables via metadata...")
            from src.db.models import Base
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
    else:
        from src.db.models import Base
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    # 3. Seed database
    async with session_factory() as session:
        await seed_database(session)
        await session.commit()
    logger.info("Database seeded.")

    # 4. MQTT Client setup
    loop = asyncio.get_running_loop()
    mqtt_client = MQTTClient(config, loop)
    handler = EventHandler(session_factory, mqtt_client)
    mqtt_client.set_message_handler(handler.handle_message)
    mqtt_client.connect()
    app.state.mqtt_client = mqtt_client

    logger.info("Energy Management Backend started.")
    yield

    mqtt_client.disconnect()
    await engine.dispose()
    logger.info("Energy Management Backend shut down.")


app = FastAPI(
    title="Energy Management Backend",
    description="REST API and MQTT processor for energy terminal management, session tracking, and billing",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(terminals.router, prefix="/terminals", tags=["Terminals"])
app.include_router(reservations.router, prefix="/reservations", tags=["Reservations"])
app.include_router(sessions.router, prefix="/sessions", tags=["Sessions"])
app.include_router(billing.router, tags=["Billing"])


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok"}
