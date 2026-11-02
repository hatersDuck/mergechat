"""Application configuration."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_JEV_BASE_URL = "https://polza.ai/api"


class Settings(BaseSettings):
    """Environment-backed settings for the Phase 0 spike."""

    model_config = SettingsConfigDict(
        env_prefix="MERGECHAT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "sqlite:///./mergechat.db"
    session_encryption_key: SecretStr = SecretStr("")
    log_level: str = "INFO"
    retention_days: int = Field(default=30, ge=1)
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    api_reload: bool = False
    api_token: SecretStr = SecretStr("")

    jev_base_url: str = DEFAULT_JEV_BASE_URL
    jev_api_key: SecretStr = SecretStr("")
    jev_model: str | None = None
    jev_timeout_seconds: float = 30.0
    jev_confidence_threshold: float = Field(default=0.5, ge=0.0, le=1.0)

    max_phone: str | None = None
    max_session_name: str = "mergechat.db"
    max_work_dir: str = "sessions"
    max_connect_timeout_seconds: float = 20.0

    @field_validator("jev_base_url", mode="before")
    @classmethod
    def _default_jev_base_url(cls, value: object) -> object:
        if value is None or (isinstance(value, str) and not value.strip()):
            return DEFAULT_JEV_BASE_URL
        return value

    @property
    def async_database_url(self) -> str:
        """Return the database URL using the asyncio SQLite driver."""
        url = self.database_url
        if url.startswith("sqlite:///"):
            return url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
        if url.startswith("sqlite+aiosqlite:///"):
            return url
        return url

    @property
    def has_session_encryption(self) -> bool:
        return bool(self.session_encryption_key.get_secret_value().strip())

    @property
    def has_jev_credentials(self) -> bool:
        return bool(self.jev_api_key.get_secret_value().strip())

    @property
    def max_work_path(self) -> Path:
        return Path(self.max_work_dir)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    """Clear the settings cache (used by tests)."""
    get_settings.cache_clear()
