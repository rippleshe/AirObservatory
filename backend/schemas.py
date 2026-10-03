from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

DataKind = Literal["observation", "model_analysis"]
Metric = Literal["pm25", "pm10", "no2", "o3", "so2", "co", "aqi", "reference_aqi"]
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

class NationalCity(BaseModel):
    location_id: int
    name: str
    province: str | None = None
    region: str
    lat: float
    lon: float
    pm25: float | None = None
    pm25_change_24h: float | None = None
    china_aqi: int | None = None
    china_aqi_level: str | None = None
    primary_pollutants: list[str] = Field(default_factory=list)
    health_effect: str | None = None
    advice: str | None = None
    european_aqi_reference: float | None = None
    has_recent_ground_observation: bool
    source_time: datetime


class NationalRegion(BaseModel):
    region: str
    city_count: int
    mean_pm25: float | None = None
    mean_china_aqi: float | None = None


class NationalSummary(BaseModel):
    city_count: int
    model_coverage: int
    recent_ground_coverage: int
    mean_pm25: float | None = None
    high_pollution_city_count: int
    worst_city: str | None = None
    worst_city_aqi: int | None = None
    level_counts: dict[str, int] = Field(default_factory=dict)


class NationalOverviewResponse(BaseModel):
    generated_at: datetime
    latest_source_time: datetime | None = None
    aqi_standard: str
    aqi_semantics: str
    summary: NationalSummary
    regions: list[NationalRegion]
    cities: list[NationalCity]


class NationalSeriesCity(BaseModel):
    location_id: int
    name: str
    province: str | None = None
    lat: float
    lon: float
    values: list[float | None]


class NationalSeriesResponse(BaseModel):
    variable: str
    unit: str
    hours: int
    data_kind: DataKind = "model_analysis"
    times: list[datetime]
    cities: list[NationalSeriesCity]


class NationalWeatherCity(BaseModel):
    location_id: int
    name: str
    province: str | None = None
    lat: float
    lon: float
    wind_speed: list[float | None]
    wind_direction: list[float | None]
    temperature: list[float | None]


class NationalWeatherResponse(BaseModel):
    hours: int
    times: list[datetime]
    cities: list[NationalWeatherCity]


class PCAExplainedVariance(BaseModel):
    component: str
    variance_ratio: float
    cumulative_ratio: float


class PCALoading(BaseModel):
    feature: str
    values: dict[str, float]


class PCAScore(BaseModel):
    time: datetime
    values: dict[str, float]


class CorrelationRow(BaseModel):
    feature: str
    values: dict[str, float]


class CityStructureMeta(BaseModel):
    run_id: str
    location_id: int
    city: str
    created_at: datetime
    window_start: datetime
    window_end: datetime
    sample_count: int
    input_rows: int
    dropped_rows: int
    missing_fraction: float
    standardization: str
    missing_strategy: str
    pollution_source: str
    weather_source: str
    features: list[str]


class CityStructureResponse(BaseModel):
    meta: CityStructureMeta
    explained_variance: list[PCAExplainedVariance]
    loadings: list[PCALoading]
    scores: list[PCAScore]
    correlation: list[CorrelationRow]

class CoverageDay(BaseModel):
    day: str
    observation_hours: int
    model_hours: int
    weather_hours: int
    observation_coverage: float
    model_coverage: float
    weather_coverage: float


class TrustBinding(BaseModel):
    provider: str
    station_name: str
    external_location_id: str
    first_at: datetime | None = None
    last_at: datetime | None = None
    active: bool
    kind: str
    is_authoritative: bool


class AnalysisArtifactSummary(BaseModel):
    run_id: str
    analysis_type: str
    version: str
    window_start: datetime
    window_end: datetime
    created_at: datetime
    status: str


class CoverageResponse(BaseModel):
    location_id: int
    city: str
    days: int
    coverage: list[CoverageDay]
    bindings: list[TrustBinding]
    analyses: list[AnalysisArtifactSummary]


class BacktestSample(BaseModel):
    model_name: str
    model_revision: str
    target_at: datetime
    horizon_hours: int
    predicted_value: float
    observed_value: float
    error: float
    absolute_error: float


class BacktestResponse(BaseModel):
    location_id: int
    city: str
    target: str
    unit: str
    metrics: list[ModelMetric]
    samples: list[BacktestSample]

class FingerprintFeatureScore(BaseModel):
    feature: str
    zscore: float


class FingerprintClusterProfile(BaseModel):
    cluster: int
    city_count: int
    top_features: list[FingerprintFeatureScore]


class CityFingerprintPoint(BaseModel):
    location_id: int
    city: str
    province: str | None = None
    region: str
    sample_hours: int
    cluster: int
    values: dict[str, float]
    features: dict[str, float]


class CityFingerprintMeta(BaseModel):
    run_id: str
    created_at: datetime
    window_start: datetime
    window_end: datetime
    city_count: int
    sample_hours_min: int
    sample_hours_max: int
    features: list[str]
    standardization: str
    local_structure_warning: str
    cluster_method: str
    cluster_count: int
    silhouette: float | None = None


class CityFingerprintResponse(BaseModel):
    meta: CityFingerprintMeta
    explained_variance: list[PCAExplainedVariance]
    loadings: list[PCALoading]
    points: list[CityFingerprintPoint]
    cluster_profiles: list[FingerprintClusterProfile]
