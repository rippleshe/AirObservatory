from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from .schemas import (
    BacktestResponse,
    CityFingerprintResponse,
    CityStructureResponse,
    CoverageResponse,
    DataKind,
    ForecastResponse,
    LocationSummary,
    Metric,
    ModelMetricsResponse,
    NationalOverviewResponse,
    NationalSeriesResponse,
    NationalWeatherResponse,
    OverviewResponse,
    SeriesResponse,
    SnapshotResponse,
    StatusResponse,
    SystemResponse,
    TrainingReadinessResponse,
)
from .services import (
    get_backtest,
    get_city_fingerprint,
    get_city_structure,
    get_coverage,
    get_forecast,
    get_locations,
    get_model_metrics,
    get_national_overview,
    get_national_series,
    get_national_weather,
    get_overview,
    get_series,
    get_snapshot,
    get_status,
    get_system_state,
    get_training_readiness,
)

router = APIRouter(prefix="/api")


def _bad_request(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


def _not_found(exc: LookupError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc))


@router.get("/status", response_model=StatusResponse)
def status() -> StatusResponse:
    return get_status()


@router.get("/overview/national", response_model=NationalOverviewResponse)
def national_overview() -> NationalOverviewResponse:
    return get_national_overview()


@router.get("/overview/national/series", response_model=NationalSeriesResponse)
def national_series(
    variable: Annotated[str, Query()] = "pm25",
    hours: Annotated[int, Query(ge=1, le=8760)] = 720,
) -> NationalSeriesResponse:
    try:
        return get_national_series(variable=variable, hours=hours)
    except ValueError as exc:
        raise _bad_request(exc) from exc
    except LookupError as exc:
        raise _not_found(exc) from exc


@router.get("/overview/national/weather", response_model=NationalWeatherResponse)
def national_weather(
    hours: Annotated[int, Query(ge=1, le=8760)] = 720,
    location_id: Annotated[int | None, Query()] = None,
) -> NationalWeatherResponse:
    try:
        return get_national_weather(hours=hours, location_id=location_id)
    except ValueError as exc:
        raise _bad_request(exc) from exc
    except LookupError as exc:
        raise _not_found(exc) from exc


@router.get(
    "/analysis/city-fingerprint",
    response_model=CityFingerprintResponse,
)
def city_fingerprint() -> CityFingerprintResponse:
    try:
        return get_city_fingerprint()
    except LookupError as exc:
        raise _not_found(exc) from exc


@router.get("/overview", response_model=OverviewResponse)
def overview(
    metric: Annotated[Metric, Query()] = "pm25",
    data_kind: Annotated[DataKind, Query()] = "model_analysis",
) -> OverviewResponse:
    try:
        return get_overview(metric, data_kind)
    except ValueError as exc:
        raise _bad_request(exc) from exc


@router.get(
    "/locations/{location_id}/coverage",
    response_model=CoverageResponse,
)
def coverage(
    location_id: int,
    days: Annotated[int, Query(ge=7, le=180)] = 30,
) -> CoverageResponse:
    try:
        return get_coverage(location_id, days)
    except LookupError as exc:
        raise _not_found(exc) from exc


@router.get(
    "/locations/{location_id}/backtest",
    response_model=BacktestResponse,
)
def backtest(location_id: int) -> BacktestResponse:
    try:
        return get_backtest(location_id)
    except LookupError as exc:
        raise _not_found(exc) from exc


@router.get(
    "/locations/{location_id}/structure",
    response_model=CityStructureResponse,
)
def city_structure(location_id: int) -> CityStructureResponse:
    try:
        return get_city_structure(location_id)
    except LookupError as exc:
        raise _not_found(exc) from exc


@router.get("/locations/{location_id}/snapshot", response_model=SnapshotResponse)
def snapshot(location_id: int) -> SnapshotResponse:
    try:
        return get_snapshot(location_id)
    except LookupError as exc:
        raise _not_found(exc) from exc


@router.get("/locations/{location_id}/series", response_model=SeriesResponse)
def series(
    location_id: int,
    variable: Annotated[Metric, Query()] = "pm25",
    data_kind: Annotated[DataKind, Query()] = "model_analysis",
    hours: Annotated[int, Query(ge=1, le=24 * 365)] = 48,
) -> SeriesResponse:
    try:
        return get_series(location_id, variable, data_kind, hours)
    except ValueError as exc:
        raise _bad_request(exc) from exc
    except LookupError as exc:
        raise _not_found(exc) from exc


@router.get("/locations/{location_id}/forecast", response_model=ForecastResponse)
def forecast(
    location_id: int,
    variable: Annotated[Metric, Query()] = "pm25",
) -> ForecastResponse:
    try:
        return get_forecast(location_id, variable)
    except ValueError as exc:
        raise _bad_request(exc) from exc
    except LookupError as exc:
        raise _not_found(exc) from exc

@router.get("/models/{location_id}/metrics", response_model=ModelMetricsResponse)
def model_metrics(location_id: int) -> ModelMetricsResponse:
    try:
        return get_model_metrics(location_id)
    except LookupError as exc:
        raise _not_found(exc) from exc


@router.get(
    "/models/{location_id}/readiness",
    response_model=TrainingReadinessResponse,
)
def training_readiness(location_id: int) -> TrainingReadinessResponse:
    try:
        return get_training_readiness(location_id)
    except (LookupError, ValueError) as exc:
        raise _not_found(LookupError(str(exc))) from exc


@router.get("/system", response_model=SystemResponse)
def system_state(
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> SystemResponse:
    return get_system_state(limit)

@router.get("/locations", response_model=list[LocationSummary])
def locations() -> list[LocationSummary]:
    return get_locations()
