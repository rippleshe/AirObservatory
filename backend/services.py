from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from .config import get_settings
from .repository import (
    active_location_rows,
    backtest_rows,
    latest_forecast_rows,
    latest_ingestion,
    latest_model_row,
    location_row,
    overview_rows,
    provider_binding_rows,
    recent_ingestion_rows,
    recent_observation_rows,
    series_rows,
    table_counts,
)
from .schemas import (
    AirState,
    ForecastPoint,
    ForecastResponse,
    ForecastSeries,
    IngestionRun,
    LocationSummary,
    Meta,
    ModelMetric,
    ModelMetricsResponse,
    OverviewLocation,
    OverviewResponse,
    ProviderBinding,
    ProviderStatus,
    SeriesPoint,
    SeriesResponse,
    SnapshotResponse,
    StatusResponse,
    SystemResponse,
    TrainingReadinessResponse,
)

UNITS = {
    "pm25": "µg/m³",
    "pm10": "µg/m³",
    "no2": "µg/m³",
    "o3": "µg/m³",
    "so2": "µg/m³",
    "co": "µg/m³",
    "aqi": "AQI",
    "reference_aqi": "EAQI",
}

ALLOWED_VARIABLES = set(UNITS)
OBSERVATION_METRICS = ("pm25", "pm10", "no2", "o3", "so2", "co", "aqi")


def _now() -> datetime:
    return datetime.now(UTC)


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _freshness(value: str) -> int:
    return max(0, int((_now() - _dt(value)).total_seconds()))


def _health(latest: datetime | None, data_kind: str) -> str:
    if latest is None:
        return "empty"
    threshold = timedelta(hours=15 if data_kind == "model_analysis" else 3)
    return "fresh" if _now() - latest <= threshold else "stale"


def _dominant(row) -> str | None:
    values = {
        "PM2.5": row["pm25"],
        "PM10": row["pm10"],
        "NO₂": row["no2"],
        "O₃": row["o3"],
    }
    available = {key: value for key, value in values.items() if value is not None}
    return max(available, key=available.get) if available else None


def _provider_status(
    provider: str,
    configured: bool,
    stale_after: timedelta,
) -> ProviderStatus:
    if not configured:
        return ProviderStatus(
            configured=False,
            state="disabled",
            message="Provider is not configured",
        )
    row = latest_ingestion(provider)
    if row is None:
        return ProviderStatus(
            configured=True,
            state="unknown",
            message="No ingestion run recorded yet",
        )

    latest_source = _dt(row["latest_source_time"]) if row["latest_source_time"] else None
    last_run = _dt(row["finished_at"] or row["started_at"])
    if row["status"] == "error":
        state = "error"
    elif latest_source is not None and _now() - latest_source > stale_after:
        state = "stale"
    else:
        state = "healthy"
    return ProviderStatus(
        configured=True,
        state=state,
        last_run_at=last_run,
        latest_source_time=latest_source,
        message=row["message"],
    )


def get_status() -> StatusResponse:
    settings = get_settings()
    return StatusResponse(
        ok=True,
        storage="SQLite WAL",
        counts=table_counts(),
        providers={
            "cams": _provider_status("Open-Meteo", True, timedelta(hours=15)),
            "openaq": _provider_status(
                "OpenAQ",
                settings.openaq_api_key is not None,
                timedelta(hours=3),
            ),
        },
    )


def get_overview(metric: str, data_kind: str) -> OverviewResponse:
    if metric not in ALLOWED_VARIABLES:
        raise ValueError(f"Unsupported metric: {metric}")
    if data_kind not in {"observation", "model_analysis"}:
        raise ValueError(f"Unsupported data kind: {data_kind}")

    if data_kind == "model_analysis":
        table, time_col, aqi_col = "air_model_analysis", "valid_at", "reference_aqi"
        value_col = "reference_aqi" if metric == "aqi" else metric
    else:
        table, time_col, aqi_col = "air_observations", "observed_at", "aqi"
        value_col = "aqi" if metric == "reference_aqi" else metric

    rows = overview_rows(table, time_col, value_col, aqi_col)
    latest_time = max((_dt(row["source_time"]) for row in rows), default=None)
    locations = [
        OverviewLocation(
            location_id=row["location_id"],
            name=row["name"],
            province=row["province"],
            lat=row["latitude"],
            lon=row["longitude"],
            value=row["metric_value"],
            aqi=row["aqi"],
            dominant_pollutant=_dominant(row),
            source=row["source"],
            source_time=_dt(row["source_time"]),
            fetched_at=_dt(row["fetched_at"]),
            freshness_seconds=_freshness(row["source_time"]),
            quality_flag=row["quality_flag"],
            is_authoritative=bool(row["is_authoritative"]),
        )
        for row in rows
    ]
    return OverviewResponse(
        meta=Meta(
            generated_at=_now(),
            data_kind=data_kind,
            metric=metric,
            unit=UNITS.get(value_col, ""),
            latest_source_time=latest_time,
            provider_health=_health(latest_time, data_kind),
        ),
        locations=locations,
    )


def _model_state(row) -> AirState | None:
    if row is None:
        return None
    source_time = _dt(row["source_time"])
    return AirState(
        data_kind="model_analysis",
        source=row["source"],
        source_time=source_time,
        fetched_at=_dt(row["fetched_at"]),
        pm25=row["pm25"],
        pm10=row["pm10"],
        no2=row["no2"],
        o3=row["o3"],
        so2=row["so2"],
        co=row["co"],
        aqi=row["aqi"],
        aqi_standard=row["aqi_standard"],
        quality_flag=row["quality_flag"],
        metric_times={
            key: source_time
            for key in ("pm25", "pm10", "no2", "o3", "so2", "co", "aqi")
            if row[key] is not None
        },
        is_authoritative=bool(row["is_authoritative"]),
    )


def _observation_state(rows) -> AirState | None:
    if not rows:
        return None

    values: dict[str, float | None] = {metric: None for metric in OBSERVATION_METRICS}
    times: dict[str, datetime] = {}
    quality_flags: list[str] = []
    fetched_times: list[datetime] = []
    station_name: str | None = None
    source = rows[0]["source"]
    authoritative = False
    aqi_standard: str | None = None

    for row in rows:
        row_time = _dt(row["source_time"])
        fetched_times.append(_dt(row["fetched_at"]))
        authoritative = authoritative or bool(row["is_authoritative"])
        if station_name is None and row["raw_ref"]:
            try:
                station_name = json.loads(row["raw_ref"]).get("station_name")
            except (TypeError, json.JSONDecodeError):
                station_name = None

        for metric in OBSERVATION_METRICS:
            if values[metric] is None and row[metric] is not None:
                values[metric] = row[metric]
                times[metric] = row_time
                quality_flags.append(row["quality_flag"])
                if metric == "aqi":
                    aqi_standard = row["aqi_standard"]

        if all(values[metric] is not None for metric in ("pm25", "pm10", "no2", "o3")):
            break

    if not times:
        return None
    source_time = max(times.values())
    quality = (
        "flagged"
        if "flagged" in quality_flags
        else (quality_flags[0] if quality_flags else "reported")
    )
    return AirState(
        data_kind="observation",
        source=source,
        source_time=source_time,
        fetched_at=max(fetched_times),
        pm25=values["pm25"],
        pm10=values["pm10"],
        no2=values["no2"],
        o3=values["o3"],
        so2=values["so2"],
        co=values["co"],
        aqi=values["aqi"],
        aqi_standard=aqi_standard,
        quality_flag=quality,
        station_name=station_name,
        metric_times=times,
        is_authoritative=authoritative,
    )


def get_snapshot(location_id: int) -> SnapshotResponse:
    location = location_row(location_id)
    if location is None:
        raise LookupError("Location not found")

    return SnapshotResponse(
        location_id=location["location_id"],
        name=location["name"],
        city=location["city"],
        province=location["province"],
        lat=location["latitude"],
        lon=location["longitude"],
        observation=_observation_state(recent_observation_rows(location_id)),
        model_analysis=_model_state(latest_model_row(location_id)),
    )


def get_series(location_id: int, variable: str, data_kind: str, hours: int) -> SeriesResponse:
    if variable not in ALLOWED_VARIABLES:
        raise ValueError(f"Unsupported variable: {variable}")
    if data_kind not in {"observation", "model_analysis"}:
        raise ValueError(f"Unsupported data kind: {data_kind}")
    location = location_row(location_id)
    if location is None:
        raise LookupError("Location not found")

    if data_kind == "model_analysis":
        table, time_col = "air_model_analysis", "valid_at"
        value_col = "reference_aqi" if variable == "aqi" else variable
    else:
        table, time_col = "air_observations", "observed_at"
        value_col = "aqi" if variable == "reference_aqi" else variable

    since = (_now() - timedelta(hours=hours)).isoformat()
    rows = series_rows(location_id, table, time_col, value_col, since)
    return SeriesResponse(
        location_id=location["location_id"],
        city=location["city"],
        variable=variable,
        unit=UNITS.get(value_col, ""),
        data_kind=data_kind,
        points=[
            SeriesPoint(
                time=_dt(row["source_time"]),
                value=row["value"],
                source=row["source"],
                quality_flag=row["quality_flag"],
            )
            for row in rows
        ],
    )


def get_forecast(location_id: int, variable: str) -> ForecastResponse:
    if variable not in {"pm25", "pm10", "no2", "o3", "reference_aqi"}:
        raise ValueError(f"Unsupported forecast variable: {variable}")
    location = location_row(location_id)
    if location is None:
        raise LookupError("Location not found")

    rows = latest_forecast_rows(location_id, variable)
    grouped: dict[tuple[str, str, str, str], list] = {}
    for row in rows:
        key = (
            row["model_name"],
            row["model_version"],
            row["issued_at"],
            row["source"] or row["model_name"],
        )
        grouped.setdefault(key, []).append(row)

    series = [
        ForecastSeries(
            model_name=key[0],
            model_revision=key[1],
            snapshot_at=_dt(key[2]),
            source=key[3],
            points=[
                ForecastPoint(
                    target_at=_dt(row["target_at"]),
                    horizon_hours=row["horizon_hours"],
                    value=row["predicted_value"],
                    lower_bound=row["lower_bound"],
                    upper_bound=row["upper_bound"],
                )
                for row in group
            ],
        )
        for key, group in grouped.items()
    ]
    return ForecastResponse(
        location_id=location_id,
        city=location["city"],
        variable=variable,
        unit=UNITS.get(variable, ""),
        series=series,
    )

def get_model_metrics(location_id: int) -> ModelMetricsResponse:
    location = location_row(location_id)
    if location is None:
        raise LookupError("Location not found")

    groups: dict[tuple[str, str, int], list[tuple[float, float]]] = {}
    for row in backtest_rows(location_id):
        key = (
            row["model_name"],
            row["model_version"],
            int(row["horizon_hours"]),
        )
        groups.setdefault(key, []).append(
            (float(row["error"]), float(row["absolute_error"]))
        )

    metrics: list[ModelMetric] = []
    for (model_name, revision, horizon), values in groups.items():
        samples = len(values)
        mae = sum(value[1] for value in values) / samples
        rmse = (sum(value[0] ** 2 for value in values) / samples) ** 0.5
        metrics.append(
            ModelMetric(
                model_name=model_name,
                model_revision=revision,
                horizon_hours=horizon,
                samples=samples,
                mae=mae,
                rmse=rmse,
            )
        )
    metrics.sort(key=lambda item: (item.horizon_hours, item.mae, item.model_name))
    return ModelMetricsResponse(
        location_id=location_id,
        city=location["city"],
        target="pm25",
        metrics=metrics,
    )


def get_training_readiness(location_id: int) -> TrainingReadinessResponse:
    from .ml.readiness import check_pm25_training_readiness

    result = check_pm25_training_readiness(location_id)
    return TrainingReadinessResponse(
        ready=result.ready,
        location_id=result.location_id,
        city=result.city,
        observation_rows=result.observation_rows,
        observed_start=_dt(result.observed_start) if result.observed_start else None,
        observed_end=_dt(result.observed_end) if result.observed_end else None,
        span_hours=result.span_hours,
        completeness=result.completeness,
        reasons=list(result.reasons),
    )


def get_system_state(limit: int = 20) -> SystemResponse:
    ingestions = [
        IngestionRun(
            provider=row["provider"],
            dataset=row["dataset"],
            started_at=_dt(row["started_at"]),
            finished_at=_dt(row["finished_at"]) if row["finished_at"] else None,
            latest_source_time=(
                _dt(row["latest_source_time"]) if row["latest_source_time"] else None
            ),
            status=row["status"],
            message=row["message"],
            error_count=int(row["error_count"]),
            latency_seconds=row["latency_seconds"],
        )
        for row in recent_ingestion_rows(limit)
    ]
    bindings = [
        ProviderBinding(
            location_id=row["location_id"],
            city=row["city"],
            provider=row["provider_name"],
            station_name=row["external_name"],
            external_location_id=row["external_location_id"],
            last_at=_dt(row["last_at"]) if row["last_at"] else None,
            active=bool(row["active"]),
        )
        for row in provider_binding_rows()
    ]
    return SystemResponse(ingestions=ingestions, bindings=bindings)

def get_locations() -> list[LocationSummary]:
    return [
        LocationSummary(
            location_id=row["location_id"],
            name=row["name"],
            city=row["city"],
            province=row["province"],
            lat=row["latitude"],
            lon=row["longitude"],
            timezone=row["timezone"],
        )
        for row in active_location_rows()
    ]
