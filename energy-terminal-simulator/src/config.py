from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", env_file=".env", extra="ignore")

    MQTT_BROKER_HOST: str = "localhost"
    MQTT_BROKER_PORT: int = 1883
    SIMULATOR_PORT: int = 8001
    TELEMETRY_INTERVAL_SECONDS: float = 3.0
    RESERVATION_TIMEOUT_SECONDS: int = 120
    ACK_TIMEOUT_SECONDS: int = 30
    ERROR_RECOVERY_SECONDS: int = 10
    RANDOM_SEED: int | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
