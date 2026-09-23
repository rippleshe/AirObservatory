from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from backend.db import get_source, transaction
from backend.main import app
from backend.services import get_forecast, get_series, get_snapshot


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


def test_public_api_has_no_project_version_prefix(isolated_db):
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/status").status_code == 200
