from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

DataKind = Literal["observation", "model_analysis"]
Metric = Literal["pm25", "pm10", "no2", "o3", "aqi", "reference_aqi"]
ProviderHealth = Literal["fresh", "stale", "empty"]
ProviderState = Literal["healthy", "stale", "error", "disabled", "unknown"]


class Meta(BaseModel):
    generated_at: datetime
    data_kind: DataKind
    metric: str
    unit: str
    latest_source_time: datetime | None = None
    provider_health: ProviderHealth


class OverviewLocation(BaseModel):
    location_id: int
    name: str
    province: str | None = None
    lat: float
    lon: float
    value: float | None = None
    aqi: float | None = None
    dominant_pollutant: str | None = None
    source: str
    source_time: datetime
    fetched_at: datetime
    freshness_seconds: int
    quality_flag: str
    is_authoritative: bool = False


class OverviewResponse(BaseModel):
    meta: Meta
    locations: list[OverviewLocation]


class AirState(BaseModel):
    data_kind: DataKind
    source: str
    source_time: datetime
    fetched_at: datetime
    pm25: float | None = None
    pm10: float | None = None
    no2: float | None = None
    o3: float | None = None
    so2: float | None = None
    co: float | None = None
    aqi: float | None = None
    aqi_standard: str | None = None
    quality_flag: str
    station_name: str | None = None
    metric_times: dict[str, datetime] = Field(default_factory=dict)
    is_authoritative: bool = False


class SnapshotResponse(BaseModel):
    location_id: int
    name: str
    city: str
    province: str | None
    lat: float
    lon: float
    observation: AirState | None = None
    model_analysis: AirState | None = None


class SeriesPoint(BaseModel):
    time: datetime
    value: float | None
    source: str
    quality_flag: str


class SeriesResponse(BaseModel):
    location_id: int
    city: str
    variable: str
    unit: str
    data_kind: DataKind
    points: list[SeriesPoint]


class ForecastPoint(BaseModel):
    target_at: datetime
    horizon_hours: int
    value: float
    lower_bound: float | None = None
    upper_bound: float | None = None


class ForecastSeries(BaseModel):
    model_name: str
    model_revision: str
    snapshot_at: datetime
    source: str
    points: list[ForecastPoint]


class ForecastResponse(BaseModel):
    location_id: int
    city: str
    variable: str
    unit: str
    series: list[ForecastSeries]


class ProviderStatus(BaseModel):
    configured: bool
    state: ProviderState
    last_run_at: datetime | None = None
    latest_source_time: datetime | None = None
    message: str | None = None


class StatusResponse(BaseModel):
    ok: bool
    storage: str
    counts: dict[str, int]
    providers: dict[str, ProviderStatus]


class ModelMetric(BaseModel):
    model_name: str
    model_revision: str
    horizon_hours: int
    samples: int
    mae: float
    rmse: float


class ModelMetricsResponse(BaseModel):
    location_id: int
    city: str
    target: str
    metrics: list[ModelMetric]


class TrainingReadinessResponse(BaseModel):
    ready: bool
    location_id: int
    city: str
    observation_rows: int
    observed_start: datetime | None = None
    observed_end: datetime | None = None
    span_hours: float
    completeness: float
    reasons: list[str]


class IngestionRun(BaseModel):
    provider: str
    dataset: str
    started_at: datetime
    finished_at: datetime | None = None
    latest_source_time: datetime | None = None
    status: str
    message: str | None = None
    error_count: int
    latency_seconds: float | None = None


class ProviderBinding(BaseModel):
    location_id: int
    city: str
    provider: str
    station_name: str
    external_location_id: str
    last_at: datetime | None = None
    active: bool


class SystemResponse(BaseModel):
    ingestions: list[IngestionRun]
    bindings: list[ProviderBinding]

class LocationSummary(BaseModel):
    location_id: int
    name: str
    city: str
    province: str | None = None
    lat: float
    lon: float
    timezone: str
