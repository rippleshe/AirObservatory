"""The demo library is what every developer's first command produces, so the
one thing worth guarding in CI is that it still fills every read path the four
pages use."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta

from backend.db import connect
from backend.repository import table_counts
from backend.services import (
    get_backtest,
    get_city_fingerprint,
    get_city_structure,
    get_coverage,
    get_forecast,
    get_national_overview,
    get_national_series,
    get_national_weather,
    get_overview,
    get_overview_signals,
    get_series,
    get_snapshot,
    get_status,
    get_system_state,
)
from scripts.seed_demo import (
    LAGGING_CITY_COUNT,
    OFFLINE_STATION_HOURS,
    PARTIAL_BATCH_ERRORS,
    WEATHER_LAG_HOURS,
    main,
)

OBSERVED_CITY = 1  # 1 % 3 != 0
UNOBSERVED_CITY = 3  # 3 % 3 == 0


def _run_seed(monkeypatch, *extra: str) -> None:
    monkeypatch.setattr(
        sys, "argv", ["seed_demo", "--days", "4", "--max-cities", "6", *extra]
    )
    main()


def test_seed_demo_fills_every_read_path(isolated_db, monkeypatch):
    _run_seed(monkeypatch, "--skip-analysis")
    counts = table_counts()
    assert counts["air_model_analysis"] > 0
    assert counts["air_observations"] > 0
    assert counts["forecasts"] > 0
    assert counts["provider_bindings"] > 0

    status = get_status()
    # init_db always seeds the full catalog; --max-cities only limits the data.
    assert status.counts["locations"] >= 6
    assert status.providers["cams"].state == "healthy"

    national = get_national_overview()
    assert national.summary.model_coverage == 6
    assert national.summary.worst_city is not None
    assert sum(national.summary.level_counts.values()) == 6

    assert len(get_national_series("pm25", hours=96).cities) == 6
    assert len(get_national_weather(hours=96).cities) == 6
    overview_observations = get_overview("aqi", "observation").locations
    assert 0 < len(overview_observations) < 6

    snapshot = get_snapshot(OBSERVED_CITY)
    assert snapshot.observation is not None
    assert snapshot.observation.aqi_standard
    assert snapshot.model_analysis is not None

    observation = get_series(OBSERVED_CITY, "pm25", "observation", hours=96)
    assert len(observation.points) > 24
    assert {point.source for point in observation.points} == {"OpenAQ"}
    # The city hero reads the newest ground value: a gap or an outage landing on
    # the tail would leave the page with no ground reading at all.
    model = get_series(OBSERVED_CITY, "pm25", "model_analysis", hours=96)
    newest_ground = max(point.time for point in observation.points)
    newest_model = max(point.time for point in model.points)
    assert (newest_model - newest_ground).total_seconds() <= 3 * 3600

    forecast = get_forecast(OBSERVED_CITY, "pm25")
    assert {series.model_name for series in forecast.series} == {
        "CAMS",
        "LSTM",
        "Persistence",
        "Rolling Mean",
    }
    for series in forecast.series:
        assert len(series.points) == 24

    coverage = get_coverage(OBSERVED_CITY, days=3)
    assert coverage.bindings and coverage.bindings[0].provider == "合成演示站点"
    assert any(day.observation_hours for day in coverage.coverage)

    backtest = get_backtest(OBSERVED_CITY)
    assert len(backtest.samples) >= 30
    assert backtest.metrics

    assert get_overview_signals().evaluated > 0
    assert get_system_state().ingestions


def test_seed_demo_keeps_observation_and_model_separate(isolated_db, monkeypatch):
    _run_seed(monkeypatch, "--skip-analysis")
    with connect() as con:
        kinds = {
            row["kind"]
            for row in con.execute(
                """
                SELECT DISTINCT s.kind
                FROM air_observations o JOIN sources s ON s.source_id=o.source_id
                """
            )
        }
        observed_cities = {
            row["location_id"]
            for row in con.execute("SELECT DISTINCT location_id FROM air_observations")
        }
        model_cities = {
            row["location_id"]
            for row in con.execute("SELECT DISTINCT location_id FROM air_model_analysis")
        }
    assert kinds == {"ground_observation"}
    assert 0 < len(observed_cities) < len(model_cities)
    assert OBSERVED_CITY in observed_cities
    assert UNOBSERVED_CITY not in observed_cities


def test_seed_demo_is_idempotent_without_force(isolated_db, monkeypatch):
    _run_seed(monkeypatch, "--skip-analysis")
    before = table_counts()
    _run_seed(monkeypatch, "--skip-analysis")
    assert table_counts() == before


def test_seed_demo_injects_the_degraded_states(isolated_db, monkeypatch):
    """The pages are built around provenance, freshness and coverage; a library
    that only shows the healthy path demonstrates none of them."""
    _run_seed(monkeypatch, "--skip-analysis")
    state = get_system_state()

    ground = next(run for run in state.ingestions if run.dataset == "ground_latest")
    assert ground.status == "partial"
    assert ground.error_count == PARTIAL_BATCH_ERRORS

    stopped = [binding for binding in state.bindings if not binding.active]
    assert len(stopped) == 1
    offline_id = stopped[0].location_id

    with connect() as con:
        last_observed = con.execute(
            "SELECT MAX(observed_at) AS t FROM air_observations WHERE location_id=?",
            (offline_id,),
        ).fetchone()["t"]
        last_model = con.execute(
            "SELECT MAX(valid_at) AS t FROM air_model_analysis WHERE location_id=?",
            (offline_id,),
        ).fetchone()["t"]
        lagging = con.execute(
            """
            SELECT location_id, COUNT(*) AS blank
            FROM weather_observations
            WHERE wind_speed_10m IS NULL
            GROUP BY location_id
            """
        ).fetchall()
        model_tail = con.execute(
            """
            SELECT COUNT(*) AS n FROM air_model_analysis
            WHERE location_id=? AND pm25 IS NOT NULL
            """,
            (lagging[0]["location_id"] if lagging else 0,),
        ).fetchone()["n"]

    gap_hours = (datetime.fromisoformat(last_model) - datetime.fromisoformat(last_observed))
    assert gap_hours >= timedelta(hours=OFFLINE_STATION_HOURS - 1)
    assert len(lagging) == LAGGING_CITY_COUNT
    assert all(row["blank"] == WEATHER_LAG_HOURS for row in lagging)
    # The archive lags, the model field does not: the pages have to be able to
    # show missing weather next to a complete analysis series.
    assert model_tail > 0


def test_seed_demo_materializes_analysis_artifacts(isolated_db, monkeypatch):
    monkeypatch.setattr(
        sys, "argv", ["seed_demo", "--days", "9", "--max-cities", "8"]
    )
    main()
    structure = get_city_structure(OBSERVED_CITY)
    assert structure.meta.sample_count > 168
    assert structure.explained_variance
    fingerprint = get_city_fingerprint()
    assert fingerprint.meta.city_count == 8
    assert fingerprint.points[0].values
