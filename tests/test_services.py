from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from backend.db import get_source, transaction
from backend.main import app
from backend.services import (
    get_city_fingerprint,
    get_city_structure,
    get_forecast,
    get_national_series,
    get_series,
    get_snapshot,
)


def _city_id(city: str) -> int:
    with transaction() as con:
        row = con.execute(
            "SELECT location_id FROM locations WHERE city=?",
            (city,),
        ).fetchone()
    assert row is not None
    return int(row["location_id"])


def test_series_hours_is_a_real_time_window(isolated_db):
    location_id = _city_id("北京")
    source = get_source("openaq_ground")
    assert source is not None

    now = datetime.now(UTC).replace(microsecond=0)
    with transaction() as con:
        con.executemany(
            """
            INSERT INTO air_observations(
                location_id, source_id, observed_at, fetched_at,
                pm25, quality_flag
            ) VALUES (?, ?, ?, ?, ?, 'reported')
            """,
            [
                (
                    location_id,
                    source["source_id"],
                    (now - timedelta(hours=72)).isoformat(),
                    now.isoformat(),
                    11.0,
                ),
                (
                    location_id,
                    source["source_id"],
                    (now - timedelta(hours=1)).isoformat(),
                    now.isoformat(),
                    22.0,
                ),
            ],
        )

    response = get_series(location_id, "pm25", "observation", hours=48)
    assert [point.value for point in response.points] == [22.0]


def test_snapshot_merges_pollutants_without_inventing_same_timestamp(isolated_db):
    location_id = _city_id("北京")
    source = get_source("openaq_ground")
    assert source is not None
    now = datetime.now(UTC).replace(microsecond=0)

    with transaction() as con:
        con.execute(
            """
            INSERT INTO air_observations(
                location_id, source_id, observed_at, fetched_at,
                pm25, quality_flag, raw_ref
            ) VALUES (?, ?, ?, ?, ?, 'reported', ?)
            """,
            (
                location_id,
                source["source_id"],
                now.isoformat(),
                now.isoformat(),
                31.0,
                json.dumps({"station_name": "Station A"}),
            ),
        )
        con.execute(
            """
            INSERT INTO air_observations(
                location_id, source_id, observed_at, fetched_at,
                pm10, quality_flag, raw_ref
            ) VALUES (?, ?, ?, ?, ?, 'reported', ?)
            """,
            (
                location_id,
                source["source_id"],
                (now - timedelta(hours=1)).isoformat(),
                now.isoformat(),
                42.0,
                json.dumps({"station_name": "Station A"}),
            ),
        )

    snapshot = get_snapshot(location_id)
    assert snapshot.observation is not None
    assert snapshot.observation.pm25 == 31.0
    assert snapshot.observation.pm10 == 42.0
    assert snapshot.observation.station_name == "Station A"
    assert snapshot.observation.metric_times["pm25"] != snapshot.observation.metric_times["pm10"]


def test_forecast_returns_latest_snapshot_for_each_model(isolated_db):
    location_id = _city_id("北京")
    source = get_source("air_observatory_baseline")
    assert source is not None
    now = datetime.now(UTC).replace(microsecond=0)

    with transaction() as con:
        for model, issued_offset, value in (
            ("Persistence", 2, 20.0),
            ("Rolling Mean", 1, 18.0),
        ):
            issued = now - timedelta(hours=issued_offset)
            con.execute(
                """
                INSERT INTO forecasts(
                    location_id, source_id, model_name, model_version,
                    issued_at, target_at, horizon_hours, variable,
                    predicted_value, unit, fetched_at
                ) VALUES (?, ?, ?, 'baseline', ?, ?, 1, 'pm25', ?, 'µg/m³', ?)
                """,
                (
                    location_id,
                    source["source_id"],
                    model,
                    issued.isoformat(),
                    (issued + timedelta(hours=1)).isoformat(),
                    value,
                    now.isoformat(),
                ),
            )

    response = get_forecast(location_id, "pm25")
    assert {series.model_name for series in response.series} == {
        "Persistence",
        "Rolling Mean",
    }


def test_national_series_aligns_cities_and_keeps_holes(isolated_db):
    beijing = _city_id("北京")
    shanghai = _city_id("上海")
    source = get_source("air_observatory_baseline")
    assert source is not None
    now = datetime.now(UTC).replace(microsecond=0)

    def insert(location_id: int, hours_back: int, value: float | None) -> None:
        with transaction() as con:
            con.execute(
                """
                INSERT INTO air_model_analysis(
                    location_id, source_id, valid_at, fetched_at,
                    pm25, quality_flag
                ) VALUES (?, ?, ?, ?, ?, 'ok')
                """,
                (
                    location_id,
                    source["source_id"],
                    (now - timedelta(hours=hours_back)).isoformat(),
                    now.isoformat(),
                    value,
                ),
            )

    insert(beijing, 3, 10.0)
    insert(beijing, 2, 30.0)
    insert(beijing, 1, 50.0)
    insert(shanghai, 2, 8.0)
    # Shanghai is missing the newest hour: the hole must survive, not become 0.
    insert(shanghai, 1, None)

    response = get_national_series(variable="pm25", hours=6)
    by_name = {city.name: city for city in response.cities}
    assert len(response.times) == 3
    assert by_name["北京"].values == [10.0, 30.0, 50.0]
    assert by_name["上海"].values == [None, 8.0, None]

    with TestClient(app) as client:
        payload = client.get("/api/overview/national/series?hours=6").json()
    assert payload["variable"] == "pm25"
    assert len(payload["cities"]) == 2


def test_public_api_has_no_project_version_prefix(isolated_db):
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/status").status_code == 200

def test_city_structure_reads_materialized_artifact(isolated_db):
    location_id = _city_id("北京")
    now = datetime.now(UTC).replace(microsecond=0)
    payload = {
        "run_id": "structure-test-run",
        "location_id": location_id,
        "city": "北京",
        "created_at": now.isoformat(),
        "window_start": (now - timedelta(days=7)).isoformat(),
        "window_end": now.isoformat(),
        "sample_count": 168,
        "input_rows": 168,
        "dropped_rows": 0,
        "missing_fraction": 0.0,
        "standardization": "z-score",
        "missing_strategy": "complete_case_no_interpolation",
        "pollution_source": "CAMS model analysis",
        "weather_source": "Open-Meteo historical weather/reanalysis",
        "features": ["pm25", "temperature_2m"],
        "explained_variance": [
            {"component": "PC1", "variance_ratio": 0.7, "cumulative_ratio": 0.7}
        ],
        "loadings": [
            {"feature": "pm25", "PC1": 0.71},
            {"feature": "temperature_2m", "PC1": -0.71},
        ],
        "scores": [{"time": now.isoformat(), "PC1": 1.2}],
        "correlation": [
            {
                "feature": "pm25",
                "values": {"pm25": 1.0, "temperature_2m": -0.4},
            },
            {
                "feature": "temperature_2m",
                "values": {"pm25": -0.4, "temperature_2m": 1.0},
            },
        ],
    }
    with transaction() as con:
        con.execute(
            """
            INSERT INTO analysis_runs(
                run_id, analysis_type, version, window_start, window_end,
                created_at, config_json, metrics_json, status
            ) VALUES (?, ?, 'test', ?, ?, ?, '{}', ?, 'success')
            """,
            (
                payload["run_id"],
                f"city_structure:{location_id}",
                payload["window_start"],
                payload["window_end"],
                payload["created_at"],
                json.dumps(payload),
            ),
        )

    response = get_city_structure(location_id)
    assert response.meta.sample_count == 168
    assert response.explained_variance[0].variance_ratio == 0.7
    assert response.loadings[0].values["PC1"] == 0.71

    with TestClient(app) as client:
        result = client.get(f"/api/locations/{location_id}/structure")
        assert result.status_code == 200
        assert result.json()["meta"]["missing_strategy"] == "complete_case_no_interpolation"


def test_weather_source_is_explicitly_non_authoritative_gridded_data(isolated_db):
    source = get_source("openmeteo_weather_reanalysis")
    assert source is not None
    assert source["kind"] == "weather_observation"
    assert source["is_authoritative"] == 0
    assert "not a station observation" in source["description"]

def test_city_fingerprint_reads_materialized_artifact(isolated_db):
    now = datetime.now(UTC).replace(microsecond=0)
    payload = {
        "run_id": "fingerprint-test-run",
        "created_at": now.isoformat(),
        "window_start": (now - timedelta(days=30)).isoformat(),
        "window_end": now.isoformat(),
        "city_count": 3,
        "sample_hours_min": 720,
        "sample_hours_max": 720,
        "features": ["pm25_mean", "wind_speed_mean"],
        "standardization": "z-score across cities",
        "local_structure_warning": "Local PCA axes are not compared across cities.",
        "cluster_method": "KMeans; k selected by maximum silhouette over k=2..6",
        "cluster_count": 2,
        "silhouette": 0.31,
        "explained_variance": [
            {"component": "PC1", "variance_ratio": 0.7, "cumulative_ratio": 0.7},
            {"component": "PC2", "variance_ratio": 0.3, "cumulative_ratio": 1.0},
        ],
        "loadings": [
            {"feature": "pm25_mean", "PC1": 0.8, "PC2": 0.2},
            {"feature": "wind_speed_mean", "PC1": -0.2, "PC2": 0.8},
        ],
        "points": [
            {
                "location_id": 1,
                "city": "北京",
                "province": "北京",
                "region": "华北",
                "sample_hours": 720,
                "cluster": 1,
                "PC1": 1.2,
                "PC2": -0.4,
                "features": {"pm25_mean": 32.0, "wind_speed_mean": 2.1},
            }
        ],
        "cluster_profiles": [
            {
                "cluster": 1,
                "city_count": 1,
                "top_features": [
                    {"feature": "pm25_mean", "zscore": 1.1},
                    {"feature": "wind_speed_mean", "zscore": -0.8},
                ],
            }
        ],
    }
    with transaction() as con:
        con.execute(
            """
            INSERT INTO analysis_runs(
                run_id, analysis_type, version, window_start, window_end,
                created_at, config_json, metrics_json, status
            ) VALUES (?, 'city_fingerprint', 'test', ?, ?, ?, '{}', ?, 'success')
            """,
            (
                payload["run_id"],
                payload["window_start"],
                payload["window_end"],
                payload["created_at"],
                json.dumps(payload),
            ),
        )

    response = get_city_fingerprint()
    assert response.meta.city_count == 3
    assert response.points[0].city == "北京"
    assert response.points[0].values["PC1"] == 1.2
    assert response.cluster_profiles[0].top_features[0].feature == "pm25_mean"

    with TestClient(app) as client:
        result = client.get("/api/analysis/city-fingerprint")
        assert result.status_code == 200
        assert result.json()["meta"]["cluster_count"] == 2
