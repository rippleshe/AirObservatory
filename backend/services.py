from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from .analytics.aqi import STANDARD as AQI_STANDARD
from .analytics.aqi import realtime_aqi
from .city_catalog import region_for
from .config import get_settings
from .ml.lstm_pipeline import city_lstm_run
from .repository import (
    active_location_rows,
    backtest_rows,
    backtest_sample_rows,
    coverage_rows,
    latest_city_fingerprint_row,
    latest_city_structure_row,
    latest_forecast_rows,
    latest_ingestion,
    latest_model_row,
    location_analysis_rows,
    location_binding_rows,
    location_row,
    national_model_rows,
    national_series_rows,
    national_weather_rows,
    overview_rows,
    overview_signal_rows,
    provider_binding_rows,
    recent_ingestion_rows,
    recent_observation_rows,
    series_rows,
    table_counts,
)
from .schemas import (
    AirState,
    AnalysisArtifactSummary,
    BacktestResponse,
    BacktestSample,
    CityFingerprintMeta,
    CityFingerprintPoint,
    CityFingerprintResponse,
    CitySignal,
    CityStructureMeta,
    CityStructureResponse,
    CorrelationRow,
    CoverageDay,
    CoverageResponse,
    FingerprintClusterProfile,
    FingerprintFeatureScore,
    ForecastPoint,
    ForecastResponse,
    ForecastSeries,
    IngestionRun,
    LocationSummary,
    LstmForecastPoint,
    LstmMeta,
    LstmRunResponse,
    LstmStep,
    Meta,
    ModelMetric,
    ModelMetricsResponse,
    NationalCity,
    NationalOverviewResponse,
    NationalRegion,
    NationalSeriesCity,
    NationalSeriesResponse,
    NationalSummary,
    NationalWeatherCity,
    NationalWeatherResponse,
    OverviewLocation,
    OverviewResponse,
    OverviewSignalsResponse,
    PCAExplainedVariance,
    PCALoading,
    PCAScore,
    ProviderBinding,
    ProviderStatus,
    SeriesPoint,
    SeriesResponse,
    SignalPeak,
    SnapshotResponse,
    StatusResponse,
    SystemResponse,
    TrainingReadinessResponse,
    TrustBinding,
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
    keys = set(row.keys())
    result = realtime_aqi(
        pm25=row["pm25"] if "pm25" in keys else None,
        pm10=row["pm10"] if "pm10" in keys else None,
        no2=row["no2"] if "no2" in keys else None,
        o3=row["o3"] if "o3" in keys else None,
        so2=row["so2"] if "so2" in keys else None,
        co=row["co"] if "co" in keys else None,
    )
    return result.primary_pollutants[0] if result.primary_pollutants else None


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

def get_national_series(
    variable: str = "pm25",
    hours: int = 720,
    data_kind: str = "model_analysis",
) -> NationalSeriesResponse:
    """Aligned hourly field across every active city.

    One request replaces N × /locations/{id}/series calls, so the national
    layer can draw evolution forms (ridgeline, stream, horizon) without the
    client stitching a panel by hand. Values stay missing when missing —
    the response is an aligned matrix with holes, never an interpolated field.
    """
    if variable not in ALLOWED_VARIABLES:
        raise ValueError(f"Unsupported variable: {variable}")
    if data_kind != "model_analysis":
        raise ValueError(f"Unsupported data kind: {data_kind}")
    if not 1 <= hours <= 8760:
        raise ValueError("hours must be between 1 and 8760")

    value_col = "reference_aqi" if variable in {"aqi", "reference_aqi"} else variable
    since = (_now() - timedelta(hours=hours)).isoformat()
    rows = national_series_rows(value_col, since)
    if not rows:
        raise LookupError("No national series available")

    times: list[datetime] = []
    seen_times: dict[str, int] = {}
    for row in rows:
        stamp = row["source_time"]
        if stamp not in seen_times:
            seen_times[stamp] = len(times)
            times.append(_dt(stamp))

    cities: dict[int, NationalSeriesCity] = {}
    for row in rows:
        location_id = int(row["location_id"])
        city = cities.get(location_id)
        if city is None:
            city = NationalSeriesCity(
                location_id=location_id,
                name=row["name"],
                province=row["province"],
                lat=float(row["latitude"]),
                lon=float(row["longitude"]),
                values=[None] * len(times),
            )
            cities[location_id] = city
        city.values[seen_times[row["source_time"]]] = float(row["value"])

    return NationalSeriesResponse(
        variable=variable,
        unit=UNITS.get(value_col, UNITS.get(variable, "")),
        hours=hours,
        times=times,
        cities=list(cities.values()),
    )


def get_national_weather(
    hours: int = 720, location_id: int | None = None
) -> NationalWeatherResponse:
    """Aligned hourly weather field (wind + temperature) for the flow layer.

    One request mirrors get_national_series: an aligned matrix with holes,
    never an interpolated field. wind_direction is meteorological degrees
    (0 = from north, clockwise); the frontend converts to u/v. Weather
    archives lag real time, so the newest hours are legitimately null.
    """
    if not 1 <= hours <= 8760:
        raise ValueError("hours must be between 1 and 8760")
    since = (_now() - timedelta(hours=hours)).isoformat()
    rows = national_weather_rows(since, location_id)
    if not rows:
        raise LookupError("No weather series available")

    times: list[datetime] = []
    seen_times: dict[str, int] = {}
    for row in rows:
        stamp = row["observed_at"]
        if stamp not in seen_times:
            seen_times[stamp] = len(times)
            times.append(_dt(stamp))

    cities: dict[int, NationalWeatherCity] = {}
    for row in rows:
        loc = int(row["location_id"])
        city = cities.get(loc)
        if city is None:
            city = NationalWeatherCity(
                location_id=loc,
                name=row["name"],
                province=row["province"],
                lat=float(row["latitude"]),
                lon=float(row["longitude"]),
                wind_speed=[None] * len(times),
                wind_direction=[None] * len(times),
                temperature=[None] * len(times),
            )
            cities[loc] = city
        idx = seen_times[row["observed_at"]]
        if city.wind_speed[idx] is None:
            city.wind_speed[idx] = row["wind_speed_10m"]
            city.wind_direction[idx] = row["wind_direction_10m"]
            city.temperature[idx] = row["temperature_2m"]

    return NationalWeatherResponse(hours=hours, times=times, cities=list(cities.values()))


def get_national_overview() -> NationalOverviewResponse:
    rows = national_model_rows()
    now = _now()
    cities: list[NationalCity] = []
    region_values: dict[str, list[tuple[float | None, int | None]]] = {}
    level_counts = {
        "优": 0,
        "良": 0,
        "轻度污染": 0,
        "中度污染": 0,
        "重度污染": 0,
        "严重污染": 0,
    }

    for row in rows:
        aqi = realtime_aqi(
            pm25=row["pm25"],
            pm10=row["pm10"],
            no2=row["no2"],
            o3=row["o3"],
            so2=row["so2"],
            co=row["co"],
        )
        if aqi.level is not None:
            level_counts[aqi.level] += 1

        region = region_for(row["city"]) or "其他"
        region_values.setdefault(region, []).append((row["pm25"], aqi.aqi))
        latest_ground = (
            _dt(row["latest_ground_time"]) if row["latest_ground_time"] else None
        )
        recent_ground = bool(
            latest_ground is not None and now - latest_ground <= timedelta(hours=3)
        )
        previous_pm25 = row["pm25_24h"]
        change = (
            float(row["pm25"]) - float(previous_pm25)
            if row["pm25"] is not None and previous_pm25 is not None
            else None
        )
        cities.append(
            NationalCity(
                location_id=row["location_id"],
                name=row["name"],
                province=row["province"],
                region=region,
                lat=row["latitude"],
                lon=row["longitude"],
                pm25=row["pm25"],
                pm25_change_24h=change,
                china_aqi=aqi.aqi,
                china_aqi_level=aqi.level,
                primary_pollutants=list(aqi.primary_pollutants),
                health_effect=aqi.health_effect,
                advice=aqi.advice,
                european_aqi_reference=row["reference_aqi"],
                has_recent_ground_observation=recent_ground,
                source_time=_dt(row["source_time"]),
            )
        )

    regions = []
    for region, values in sorted(region_values.items()):
        pm25_values = [value for value, _ in values if value is not None]
        aqi_values = [value for _, value in values if value is not None]
        regions.append(
            NationalRegion(
                region=region,
                city_count=len(values),
                mean_pm25=(
                    sum(pm25_values) / len(pm25_values) if pm25_values else None
                ),
                mean_china_aqi=(
                    sum(aqi_values) / len(aqi_values) if aqi_values else None
                ),
            )
        )

    aqi_cities = [city for city in cities if city.china_aqi is not None]
    worst = max(aqi_cities, key=lambda city: city.china_aqi or -1, default=None)
    pm25_values = [city.pm25 for city in cities if city.pm25 is not None]
    latest_source = max((city.source_time for city in cities), default=None)

    return NationalOverviewResponse(
        generated_at=now,
        latest_source_time=latest_source,
        aqi_standard=AQI_STANDARD,
        aqi_semantics="中国 AQI（CAMS 模式浓度按实时规则换算，非地面监测值）",
        summary=NationalSummary(
            city_count=len(active_location_rows()),
            model_coverage=len(cities),
            recent_ground_coverage=sum(
                city.has_recent_ground_observation for city in cities
            ),
            mean_pm25=(
                sum(pm25_values) / len(pm25_values) if pm25_values else None
            ),
            high_pollution_city_count=sum(
                (city.china_aqi or 0) >= 201 for city in cities
            ),
            worst_city=worst.name if worst else None,
            worst_city_aqi=worst.china_aqi if worst else None,
            level_counts=level_counts,
        ),
        regions=regions,
        cities=cities,
    )

def get_city_structure(location_id: int) -> CityStructureResponse:
    row = latest_city_structure_row(location_id)
    if row is None:
        raise LookupError("No materialized city structure analysis is available")

    payload = json.loads(row["metrics_json"])
    return CityStructureResponse(
        meta=CityStructureMeta(
            run_id=payload["run_id"],
            location_id=payload["location_id"],
            city=payload["city"],
            created_at=_dt(payload["created_at"]),
            window_start=_dt(payload["window_start"]),
            window_end=_dt(payload["window_end"]),
            sample_count=payload["sample_count"],
            input_rows=payload["input_rows"],
            dropped_rows=payload["dropped_rows"],
            missing_fraction=payload["missing_fraction"],
            standardization=payload["standardization"],
            missing_strategy=payload["missing_strategy"],
            pollution_source=payload["pollution_source"],
            weather_source=payload["weather_source"],
            features=payload["features"],
        ),
        explained_variance=[
            PCAExplainedVariance(**item) for item in payload["explained_variance"]
        ],
        loadings=[
            PCALoading(
                feature=item["feature"],
                values={
                    key: value
                    for key, value in item.items()
                    if key != "feature"
                },
            )
            for item in payload["loadings"]
        ],
        scores=[
            PCAScore(
                time=_dt(item["time"]),
                values={key: value for key, value in item.items() if key != "time"},
            )
            for item in payload["scores"]
        ],
        correlation=[
            CorrelationRow(**item) for item in payload["correlation"]
        ],
    )

def get_coverage(location_id: int, days: int = 30) -> CoverageResponse:
    location = location_row(location_id)
    if location is None:
        raise LookupError("Location not found")

    coverage = [
        CoverageDay(
            day=row["day"],
            observation_hours=int(row["observation_hours"]),
            model_hours=int(row["model_hours"]),
            weather_hours=int(row["weather_hours"]),
            observation_coverage=min(1.0, int(row["observation_hours"]) / 24.0),
            model_coverage=min(1.0, int(row["model_hours"]) / 24.0),
            weather_coverage=min(1.0, int(row["weather_hours"]) / 24.0),
        )
        for row in coverage_rows(location_id, days)
    ]
    bindings = [
        TrustBinding(
            provider=row["provider_name"],
            station_name=row["external_name"],
            external_location_id=row["external_location_id"],
            first_at=_dt(row["first_at"]) if row["first_at"] else None,
            last_at=_dt(row["last_at"]) if row["last_at"] else None,
            active=bool(row["active"]),
            kind=row["kind"],
            is_authoritative=bool(row["is_authoritative"]),
        )
        for row in location_binding_rows(location_id)
    ]
    analyses = [
        AnalysisArtifactSummary(
            run_id=row["run_id"],
            analysis_type=row["analysis_type"],
            version=row["version"],
            window_start=_dt(row["window_start"]),
            window_end=_dt(row["window_end"]),
            created_at=_dt(row["created_at"]),
            status=row["status"],
        )
        for row in location_analysis_rows(location_id)
    ]
    return CoverageResponse(
        location_id=location_id,
        city=location["city"],
        days=days,
        coverage=coverage,
        bindings=bindings,
        analyses=analyses,
    )


def get_backtest(location_id: int) -> BacktestResponse:
    location = location_row(location_id)
    if location is None:
        raise LookupError("Location not found")

    metrics = get_model_metrics(location_id).metrics
    samples = [
        BacktestSample(
            model_name=row["model_name"],
            model_revision=row["model_version"],
            target_at=_dt(row["target_at"]),
            horizon_hours=int(row["horizon_hours"]),
            predicted_value=float(row["predicted_value"]),
            observed_value=float(row["observed_value"]),
            error=float(row["error"]),
            absolute_error=float(row["absolute_error"]),
        )
        for row in backtest_sample_rows(location_id)
    ]
    return BacktestResponse(
        location_id=location_id,
        city=location["city"],
        target="pm25",
        unit="µg/m³",
        metrics=metrics,
        samples=samples,
    )

def get_city_fingerprint() -> CityFingerprintResponse:
    row = latest_city_fingerprint_row()
    if row is None:
        raise LookupError("No materialized city fingerprint analysis is available")

    payload = json.loads(row["metrics_json"])
    return CityFingerprintResponse(
        meta=CityFingerprintMeta(
            run_id=payload["run_id"],
            created_at=_dt(payload["created_at"]),
            window_start=_dt(payload["window_start"]),
            window_end=_dt(payload["window_end"]),
            city_count=int(payload["city_count"]),
            sample_hours_min=int(payload["sample_hours_min"]),
            sample_hours_max=int(payload["sample_hours_max"]),
            features=list(payload["features"]),
            standardization=payload["standardization"],
            local_structure_warning=payload["local_structure_warning"],
            cluster_method=payload["cluster_method"],
            cluster_count=int(payload["cluster_count"]),
            silhouette=payload.get("silhouette"),
        ),
        explained_variance=[
            PCAExplainedVariance(**item)
            for item in payload["explained_variance"]
        ],
        loadings=[
            PCALoading(
                feature=item["feature"],
                values={key: value for key, value in item.items() if key != "feature"},
            )
            for item in payload["loadings"]
        ],
        points=[
            CityFingerprintPoint(
                location_id=int(item["location_id"]),
                city=item["city"],
                province=item.get("province"),
                region=item["region"],
                sample_hours=int(item["sample_hours"]),
                cluster=int(item["cluster"]),
                values={
                    key: float(value)
                    for key, value in item.items()
                    if key.startswith("PC")
                },
                features={
                    key: float(value)
                    for key, value in item["features"].items()
                },
            )
            for item in payload["points"]
        ],
        cluster_profiles=[
            FingerprintClusterProfile(
                cluster=int(item["cluster"]),
                city_count=int(item["city_count"]),
                top_features=[
                    FingerprintFeatureScore(
                        feature=feature["feature"],
                        zscore=float(feature["zscore"]),
                    )
                    for feature in item["top_features"]
                ],
            )
            for item in payload["cluster_profiles"]
        ],
    )


def get_city_lstm(location_id: int) -> LstmRunResponse:
    """The trained cell's genuine forward pass for one city — gates, cell and
    hidden states for the 48h replay, the 24h decode, and the run's metrics."""
    payload = city_lstm_run(location_id)
    if payload is None:
        raise LookupError(f"LSTM not ready for location {location_id}")
    return LstmRunResponse(
        location_id=payload["location_id"],
        city=payload["city"],
        unit=payload["unit"],
        hidden=payload["hidden"],
        window_hours=payload["window_hours"],
        replay_hours=payload["replay_hours"],
        feature_names=payload["feature_names"],
        steps=[LstmStep(**step) for step in payload["steps"]],
        forecast=[LstmForecastPoint(**point) for point in payload["forecast"]],
        metrics=[ModelMetric(**row) for row in payload["metrics"]],
        meta=LstmMeta(**payload["meta"]),
    )


def get_overview_signals() -> OverviewSignalsResponse:
    """Data-derived conclusions, no prose: which cities deteriorate fastest
    over the next 24h, the national peak window, how many cities improve.
    Basis is the latest CAMS snapshot against each city's current analysis."""
    now = datetime.now(UTC)
    forecast_rows, analysis_rows = overview_signal_rows()

    current = {
        row["location_id"]: float(row["pm25"])
        for row in analysis_rows
        if row["pm25"] is not None
    }
    per_city: dict[int, dict] = {}
    for row in forecast_rows:
        if row["predicted_value"] is None:
            continue
        entry = per_city.setdefault(
            row["location_id"], {"name": row["city"], "values": []}
        )
        entry["values"].append(
            (int(row["horizon_hours"]), float(row["predicted_value"]), row["target_at"])
        )

    worsening: list[CitySignal] = []
    improving_count = 0
    lead_values: dict[int, list[float]] = {}
    lead_time: dict[int, str] = {}
    evaluated = 0
    for location_id, entry in per_city.items():
        values = entry["values"]
        if len(values) < 12:
            continue
        evaluated += 1
        base = current.get(location_id, values[0][1])
        peak_hour, peak_value, peak_at = max(values, key=lambda item: item[1])
        mean_next = sum(v for _, v, _ in values) / len(values)
        if peak_value - base >= 5.0:
            worsening.append(
                CitySignal(
                    location_id=location_id,
                    name=entry["name"],
                    delta=round(peak_value - base, 1),
                    peak=round(peak_value, 1),
                    peak_at=peak_at,
                )
            )
        if mean_next <= base - 5.0:
            improving_count += 1
        for horizon, value, target_at in values:
            lead_values.setdefault(horizon, []).append(value)
            lead_time.setdefault(horizon, target_at)

    worsening.sort(key=lambda signal: signal.delta, reverse=True)
    national_peak = None
    if lead_values:
        best_lead = max(lead_values, key=lambda h: sum(lead_values[h]) / len(lead_values[h]))
        national_peak = SignalPeak(
            lead_hours=best_lead,
            target_at=lead_time[best_lead],
            value=round(sum(lead_values[best_lead]) / len(lead_values[best_lead]), 1),
        )
    return OverviewSignalsResponse(
        generated_at=now,
        basis="CAMS",
        evaluated=evaluated,
        peak=national_peak,
        worsening=worsening[:3],
        improving_count=improving_count,
    )
