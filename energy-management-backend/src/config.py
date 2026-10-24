from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql+asyncpg://borne:borne_dev@localhost:5432/borne_energy"
    MQTT_BROKER_HOST: str = "localhost"
    MQTT_BROKER_PORT: int = 1883
    BACKEND_PORT: int = 8000
    RESERVATION_TIMEOUT_SECONDS: int = 120

    @property
    def database_url_sync(self) -> str:
        if "+asyncpg" in self.DATABASE_URL:
            return self.DATABASE_URL.replace("+asyncpg", "+psycopg2")
        return self.DATABASE_URL


@lru_cache
def get_settings() -> Settings:
    return Settings()
