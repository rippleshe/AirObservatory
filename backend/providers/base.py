from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class ModelAnalysisPoint:
    valid_at: datetime
    pm25: float | None = None
    pm10: float | None = None
    no2: float | None = None
    o3: float | None = None
    so2: float | None = None
    co: float | None = None
    reference_aqi: float | None = None


@dataclass(frozen=True)
class ModelLiveBundle:
    current: ModelAnalysisPoint
    forecast: tuple[ModelAnalysisPoint, ...]


@dataclass(frozen=True)
class GroundMeasurement:
    observed_at: datetime
    parameter: str
    value: float
    unit: str
    sensor_id: int
    has_flags: bool = False


@dataclass(frozen=True)
class GroundSite:
    external_location_id: int
    name: str
    provider: str
    country_code: str | None
    latitude: float
    longitude: float
    first_at: datetime | None
    last_at: datetime | None
    sensors: dict[str, int]
    distance_m: float


class AirModelProvider(Protocol):
    name: str

    async def fetch_range(
        self,
        latitude: float,
        longitude: float,
        start_date: str,
        end_date: str,
    ) -> list[ModelAnalysisPoint]:
        ...

    async def fetch_live(
        self,
        latitude: float,
        longitude: float,
        forecast_hours: int = 24,
    ) -> ModelLiveBundle:
        ...
