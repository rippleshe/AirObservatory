from __future__ import annotations

from datetime import UTC, datetime

from backend.db import connect, get_source
from backend.pipelines.openaq import _upsert_measurements
from backend.providers.base import GroundMeasurement, GroundSite
from backend.repository import ground_pm25_recent_cities


def test_openaq_repeated_latest_does_not_refresh_historical_rows(isolated_db):
    source = get_source("openaq_ground")
    assert source is not None
    station = GroundSite(
        external_location_id=12345, name="test site", provider="OpenAQ",
        country_code="CN", latitude=39.9, longitude=116.4,
        first_at=None, last_at=None, sensors={"pm25": 1}, distance_m=0.0,
    )
    t = datetime(2024, 1, 1, tzinfo=UTC)
    reading = GroundMeasurement(
        observed_at=t, parameter="pm25", value=15.0, unit="µg/m³", sensor_id=1,
    )
    inserted = _upsert_measurements(1, source["source_id"], station, [reading])
    assert inserted == 1
    with connect() as con:
        before = con.execute(
            "SELECT fetched_at FROM air_observations WHERE location_id=1"
        ).fetchone()[0]
    assert _upsert_measurements(1, source["source_id"], station, [reading]) == 0
    with connect() as con:
        after = con.execute(
            "SELECT fetched_at FROM air_observations WHERE location_id=1"
        ).fetchone()[0]
    assert before == after
    assert ground_pm25_recent_cities() == 0
    corrected = GroundMeasurement(
        observed_at=t, parameter="pm25", value=16.0, unit="µg/m³", sensor_id=1,
    )
    assert _upsert_measurements(1, source["source_id"], station, [corrected]) == 1
    with connect() as con:
        assert con.execute(
            "SELECT pm25 FROM air_observations WHERE location_id=1"
        ).fetchone()[0] == 16.0
