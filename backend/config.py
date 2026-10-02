from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / ".env",
        env_prefix="AIR_OBSERVATORY_",
        extra="ignore",
    )

    database_path: Path = Path("data/air_observatory.db")
    http_timeout_seconds: float = Field(default=30.0, ge=5.0, le=120.0)
    cams_refresh_seconds: int = Field(default=900, ge=300)
    openaq_refresh_seconds: int = Field(default=300, ge=300)
    weather_refresh_seconds: int = Field(default=21_600, ge=3_600)
    weather_archive_lag_days: int = Field(default=5, ge=1, le=20)
    forecast_hours: int = Field(default=24, ge=1, le=120)
    openaq_radius_m: int = Field(default=25_000, ge=1_000, le=25_000)
    openaq_api_key: SecretStr | None = Field(
        default=None,
        validation_alias="OPENAQ_API_KEY",
    )

    @property
    def resolved_database_path(self) -> Path:
        path = self.database_path
        return path if path.is_absolute() else ROOT / path


@lru_cache
def get_settings() -> Settings:
    return Settings()
