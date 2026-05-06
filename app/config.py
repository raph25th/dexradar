from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/dex_radar",
        description="SQLAlchemy database URL.",
    )
    telegram_bot_token: str | None = Field(default=None)
    telegram_chat_id: str | None = Field(default=None)
    dexscreener_base_url: str = Field(default="https://api.dexscreener.com")
    poll_interval_seconds: int = Field(default=300, ge=30)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    @property
    def normalized_dexscreener_base_url(self) -> str:
        return self.dexscreener_base_url.rstrip("/")


@lru_cache
def get_settings() -> Settings:
    return Settings()
