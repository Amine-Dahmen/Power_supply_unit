import asyncio
import pytest
import pytest_asyncio
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
)
from src.db.models import Base
from src.db.seed import seed_database


class MockMQTTClient:
    def __init__(self):
        self.published_messages: list[tuple[str, dict, int, bool]] = []

    def publish(self, topic: str, payload: dict, qos: int = 0, retain: bool = False):
        self.published_messages.append((topic, payload, qos, retain))

    def connect(self):
        pass

    def disconnect(self):
        pass


@pytest.fixture
def mock_mqtt_client():
    return MockMQTTClient()


@pytest_asyncio.fixture
async def test_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(test_engine):
    return async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def db_session(session_factory) -> AsyncGenerator[AsyncSession, None]:
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def seeded_db(db_session: AsyncSession) -> AsyncSession:
    await seed_database(db_session)
    await db_session.commit()
    return db_session
