"""Deterministic local demo library — one command, one database per developer.

The course does not grade the data, so nobody should need a 300 MB SQLite file,
an OpenAQ key or a running collector just to see a page render. This script
fills the configured database with structurally complete, internally consistent
synthetic records anchored to the hour it runs: CAMS analysis fields, weather,
sparse ground observations, forecast snapshots, and the ingestion bookkeeping
the status page reads.

Where per-city differences come from: ``backend/city_geography.csv`` — measured
elevation, relief and population, plus synthetic road, industry and emission
columns. The emission index drives each city's level (``_regime``), so the belt the
map draws is a consequence of the table instead of a coordinate hardcoded here.
``scripts/build_city_geography.py`` wrote it and says which columns are synthetic.

Three rules it does not break:

- the analysis layer still runs for real — the PCA artifacts are produced by
  ``backend.analytics`` over this input, not invented;
- a database the script did not create is never rewritten. It is moved aside
  instead, so a real collection library cannot be destroyed by ``--force``;
- the library is not uniformly healthy. Every page here is built around
  provenance, freshness and coverage, so the window contains a stopped station,
  a lagging weather archive and a rate-limited ground batch — the states the UI
  has a designed treatment for.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from backend.analytics.aqi import realtime_aqi
from backend.analytics.materialize import (
    materialize_city_fingerprint,
    materialize_city_structure,
)
from backend.city_catalog import CityGeography, geography_for
from backend.config import get_settings
from backend.db import connect, init_db, transaction
from backend.repository import active_location_rows

HOUR = timedelta(hours=1)
# Every city in the catalog is Asia/Shanghai; wall-clock fields drive the day
# cycle while stored timestamps stay UTC, exactly as the real pipelines do.
LOCAL_OFFSET = timedelta(hours=8)
SEED_MARKER = "seed_demo"
DEFAULT_DAYS = 60
DEFAULT_SEED = 20261016
# Ground coverage is deliberately partial: the national layer has to show the
# difference between the model field and the cities that actually observe.
OBSERVED_CITY_STRIDE = 3
OBSERVATION_MISSING_RATE = 0.10
OBSERVATION_OUTAGE_RATE = 0.006
FORECAST_HORIZON = 24
SNAPSHOT_STEP_HOURS = 12
SNAPSHOT_COUNT = 6
AQI_STANDARD_TEXT = "HJ 633-2026（按地面观测浓度实时换算）"
# The national field has to reach every AQI band in a single hour. The city level
# is driven by the emission index from backend/city_geography.csv, stretched across
# the roster's own range so the bands stay reachable however that table changes.
# The ceiling is set from the measured anatomy rather than from taste: at the
# evening anchor the hour multiplies the level by K (median ~1.4, up to ~3.6 across
# cities), so a ceiling of 330 left eighteen cities pinned to the top of the AQI
# scale and the province representatives reading 中度污染 and worse. At 170 the same
# hour spreads 优 through 严重污染 with the top of the roster catching the cap,
# which is what a dust-belt hour is supposed to look like.
LEVEL_FLOOR = 26.0
LEVEL_CEILING = 170.0

# The pages are built around provenance, freshness and coverage, so a library
# that only ever shows the healthy path demonstrates none of them. These inject
# the three degraded states the UI has a designed treatment for: a batch that
# hit provider rate limits, a station that stopped reporting, and a weather
# archive that lags at the tail.
PARTIAL_BATCH_ERRORS = 2
LAGGING_CITY_COUNT = 3
WEATHER_LAG_HOURS = 6
OFFLINE_STATION_HOURS = 40

# model_name, source name, revision, relative error at +1h, growth per hour.
# The revision is constant per model on purpose: the forecast endpoint groups
# snapshots by (model, revision) and keeps the newest, so a per-snapshot
# revision would show up as six parallel series instead of one.
MODEL_SPECS = (
    ("CAMS", "openmeteo_cams_forecast", "cams-global-openmeteo", 0.040, 0.0090),
    ("LSTM", None, None, 0.025, 0.0055),
    ("Persistence", "air_observatory_baseline", "demo-baseline", 0.060, 0.0170),
    ("Rolling Mean", "air_observatory_baseline", "demo-baseline", 0.050, 0.0140),
)
INGESTION_RUNS = (
    ("Open-Meteo", "cams_live_and_forecast"),
    ("OpenAQ", "ground_latest"),
    ("Open-Meteo", "weather_reanalysis"),
    ("Air Observatory", "baseline_forecasts"),
)
FACT_TABLES = (
    "air_observations",
    "air_model_analysis",
    "weather_observations",
    "forecasts",
    "provider_bindings",
    "provider_discovery_checks",
    "ingestion_runs",
    "analysis_runs",
    "model_runs",
)


@dataclass(frozen=True)
class Regime:
    """Per-city latent factors.

    These are what make the synthetic library usable rather than merely full:
    without them every city would clear the same way in wind, answer ozone the
    same way and sit at the same level, so the fingerprint PCA would find one
    featureless blob and the relationship charts would have nothing to show.
    """

    level: float
    diurnal: float
    weekly: float
    wind_clearance: float
    blh_clearance: float
    ozone: float
    ozone_peak: float
    temperature_bias: float
    humidity: float
    rain_rate: float
    wind_scale: float
    wind_direction: float
    dust: float


class CitySeries:
    """Hourly truth for one city plus the rows the API reads from it."""

    def __init__(
        self,
        location,
        regime: Regime,
        sources: dict[str, int],
        start: datetime,
        hours: int,
        weather_lag: bool = False,
    ) -> None:
        self.location = location
        self.regime = regime
        self.start = start
        self.hours = hours
        self.weather_lag = weather_lag
        self.pm25: list[float] = []
        self.pollutants: list[tuple[float, ...]] = []
        self.model_rows: list[tuple] = []
        self.weather_rows: list[tuple] = []
        self._sources = sources
        self._gust = 0.0
        self._moisture = 0.0
        self._build()

    def _build(self) -> None:
        regime = self.regime
        latitude = float(self.location["latitude"])
        location_id = int(self.location["location_id"])
        analysis_source = self._sources["openmeteo_cams_analysis"]
        weather_source = self._sources["openmeteo_weather_reanalysis"]
        lat_lapse = 0.42 * (latitude - 22.0)
        for index in range(self.hours + FORECAST_HORIZON + 1):
            stamp = self.start + index * HOUR
            local = stamp + LOCAL_OFFSET
            hour = local.hour + local.minute / 60.0
            progress = min(1.0, index / max(1, self.hours))
            # Synoptic-scale persistence (~2 days): a comb of hourly gusts would
            # make every chart look synthetic and would drown the day cycle.
            self._gust = 0.94 * self._gust + _gauss(0.0, 0.55)
            self._moisture = 0.93 * self._moisture + _gauss(0.0, 0.7)

            season_mean = 35.5 - 15.0 * progress - lat_lapse
            temperature = (
                season_mean
                + 6.5 * math.sin(2 * math.pi * (hour - 9.0) / 24.0)
                + 2.0 * self._gust
                + regime.temperature_bias
                + _gauss(0.0, 0.8)
            )
            humidity = _clamp(
                regime.humidity - 1.1 * (temperature - season_mean) + _gauss(0.0, 4.0),
                18.0,
                97.0,
            )
            wind = _clamp(
                regime.wind_scale
                * (1.5 + 1.9 * abs(self._gust))
                * (1.0 + 0.18 * math.sin(2 * math.pi * (hour - 14.0) / 24.0)),
                0.2,
                18.0,
            )
            wind_from = (
                regime.wind_direction
                + 40.0 * math.sin(2 * math.pi * hour / 24.0)
                + 55.0 * self._gust
            ) % 360.0
            boundary_layer = _clamp(
                90.0
                + 1350.0
                * max(0.0, math.sin(2 * math.pi * (hour - 6.5) / 24.0)) ** 1.4
                * (1.0 + 0.25 * self._gust)
                + 45.0 * (temperature - season_mean),
                60.0,
                2600.0,
            )
            wet_threshold = 1.55 - 2.4 * regime.rain_rate
            precipitation = (
                min(12.0, max(0.0, (self._moisture - wet_threshold) * 1.6))
                if self._moisture > wet_threshold
                else 0.0
            )

            day_shape = (
                0.62 * _day_shape(hour, 8.0, 3.2)
                + 0.62 * _day_shape(hour, 21.0, 2.6)
                - 0.50 * _day_shape(hour, 14.5, 3.5)
            )
            wind_factor = 1.0 / (1.0 + regime.wind_clearance * wind / 6.0)
            blh_factor = (550.0 / max(boundary_layer, 80.0)) ** regime.blh_clearance
            hygroscopic = 1.0 + 0.0016 * max(0.0, humidity - 55.0)
            washout = 1.0 - 0.35 * min(1.0, precipitation / 2.0)

            pm25 = _clamp(
                regime.level
                * (0.72 + 0.62 * progress)
                * (1.0 + regime.diurnal * day_shape)
                * (1.0 - (regime.weekly if local.weekday() >= 5 else 0.0))
                * wind_factor
                * blh_factor
                * hygroscopic
                * washout
                * (1.0 + _gauss(0.0, 0.09)),
                2.0,
                520.0,
            )
            pm10 = _clamp(pm25 * (1.35 + 0.55 * regime.dust) + abs(_gauss(0.0, 4.0)), 3.0, 900.0)
            no2 = _clamp(6.0 + pm25 * 0.42 + _gauss(0.0, 3.0), 2.0, 180.0)
            o3 = _clamp(
                regime.ozone
                * (0.45 + 1.05 * _day_shape(hour, regime.ozone_peak, 4.5))
                * (1.0 + 0.022 * (temperature - 18.0))
                * (1.0 - 0.18 * min(1.0, pm25 / 160.0))
                + _gauss(0.0, 4.0),
                3.0,
                320.0,
            )
            so2 = _clamp(4.0 + 0.12 * pm25 + abs(_gauss(0.0, 2.0)), 1.0, 90.0)
            co = _clamp(250.0 + 6.5 * pm25 + abs(_gauss(0.0, 40.0)), 150.0, 5000.0)
            reference = _clamp(_european_aqi(pm25, pm10, no2, o3) + _gauss(0.0, 3.0), 5.0, 200.0)

            self.pm25.append(pm25)
            self.pollutants.append((pm25, pm10, no2, o3, so2, co, reference))
            if index < self.hours:
                self.model_rows.append(
                    (
                        location_id,
                        analysis_source,
                        _iso(stamp),
                        _iso(stamp + timedelta(minutes=35)),
                        pm25,
                        pm10,
                        no2,
                        o3,
                        so2,
                        co,
                        reference,
                    )
                )
                # A lagging archive writes all-NULL rows for its newest hours
                # instead of omitting them — the same shape the real weather
                # pipeline produces while Open-Meteo's archive catches up.
                lagging = self.weather_lag and index >= self.hours - WEATHER_LAG_HOURS
                self.weather_rows.append(
                    (
                        location_id,
                        weather_source,
                        _iso(stamp),
                        _iso(stamp + timedelta(minutes=50)),
                        *(
                            (None,) * 7
                            if lagging
                            else (
                                temperature,
                                humidity,
                                1013.0 + 8.0 * (latitude / 40.0) + 2.0 * self._gust,
                                precipitation,
                                wind,
                                wind_from,
                                boundary_layer,
                            )
                        ),
                    )
                )

    def release(self) -> None:
        """The row buffers are only needed until they are written; a run over
        every city would otherwise hold the whole country's hours in memory."""
        self.pollutants = []
        self.model_rows = []
        self.weather_rows = []

    @property
    def location_id(self) -> int:
        return int(self.location["location_id"])

    @property
    def city(self) -> str:
        return str(self.location["city"])


def _gauss(mu: float = 0.0, sigma: float = 1.0) -> float:
    return random.gauss(mu, sigma)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _day_shape(hour: float, peak: float, width: float) -> float:
    delta = abs(hour - peak) % 24.0
    delta = min(delta, 24.0 - delta)
    return math.exp(-((delta / width) ** 2))


def _rng(seed: int, location_id: int) -> random.Random:
    return random.Random(f"{seed}:{location_id}")


def _european_aqi(pm25: float, pm10: float, no2: float, o3: float) -> float:
    """Monotone stand-in for the Open-Meteo European AQI index."""
    return max(pm25 / 2.0, pm10 / 4.0, no2 / 2.0, o3 / 1.6) * 1.15


def _regime(
    rng: random.Random,
    latitude: float,
    longitude: float,
    geography: CityGeography | None,
    level_range: tuple[float, float],
) -> Regime:
    """Per-city latent factors and where they now come from.

    The level used to be read straight off the coordinate ("the further inland and
    north, the dirtier"), which bakes one hardcoded belt into every page. It now
    follows the city's own static drivers from ``backend/city_geography.csv`` —
    industrial land, heating demand, urban size — so the regional structure the map
    and the clustering describe has something to be explained by, and the PCA
    loadings can be read as an emission axis.

    The coordinate gradient stays, in two places: as the fallback for a city with no
    geography row, and as the dust belt, which no column in that table describes
    (aridity is not relief: 青藏 and 华北 sit on opposite sides of that one).
    """
    north = _clamp((latitude - 30.0) / 14.0, 0.0, 1.0)
    west = _clamp((113.0 - longitude) / 25.0, 0.0, 1.0)
    belt = north * (0.35 + 0.65 * west)
    if geography is None:
        emission = belt
        altitude = 0.0
    else:
        low, high = level_range
        emission = _clamp((geography.emission_intensity - low) / max(high - low, 1e-6), 0.0, 1.0)
        altitude = _clamp(geography.elevation_m / 3000.0, 0.0, 1.0)
    return Regime(
        level=(LEVEL_FLOOR + (LEVEL_CEILING - LEVEL_FLOOR) * emission)
        * math.exp(rng.gauss(0.0, 0.18)),
        diurnal=rng.uniform(0.16, 0.50),
        weekly=rng.uniform(0.0, 0.08),
        wind_clearance=rng.uniform(0.55, 1.55),
        blh_clearance=rng.uniform(0.15, 0.55),
        # Clean air holds more ozone, and high ground more of it than low: the two
        # pollutant axes then point in different directions instead of being one.
        ozone=40.0 + 44.0 * (1.0 - emission) + rng.uniform(-6.0, 6.0),
        ozone_peak=rng.uniform(12.5, 17.5),
        temperature_bias=rng.uniform(-2.5, 2.5),
        humidity=rng.uniform(45.0, 80.0),
        rain_rate=rng.uniform(0.04, 0.22),
        wind_scale=rng.uniform(0.65, 1.55) * (1.0 + 0.35 * altitude),
        wind_direction=rng.uniform(0.0, 360.0),
        dust=rng.uniform(0.25, 0.85) + 0.7 * west,
    )


def _level_range(locations: list) -> tuple[float, float]:
    """The roster's own emission range, so one hour still spans 优…严重污染."""
    values = [
        geography.emission_intensity
        for location in locations
        if (geography := geography_for(str(location["city"]))) is not None
    ]
    return (min(values), max(values)) if values else (0.0, 100.0)


def _regimes(locations: list, seed: int) -> dict[int, Regime]:
    level_range = _level_range(locations)
    return {
        int(location["location_id"]): _regime(
            _rng(seed, int(location["location_id"])),
            float(location["latitude"]),
            float(location["longitude"]),
            geography_for(str(location["city"])),
            level_range,
        )
        for location in locations
    }


def _source_ids() -> dict[str, int]:
    with connect() as con:
        return {
            row["name"]: int(row["source_id"])
            for row in con.execute("SELECT name, source_id FROM sources")
        }


def _observation_rows(
    series: CitySeries,
    source_id: int,
    rng: random.Random,
    stop_after: int | None = None,
) -> list[tuple]:
    """Ground station view of the model field: a station bias, an hourly gap
    rate and occasional multi-hour outages, so the coverage and gap rendering
    have something honest to show. `stop_after` models a station that stopped
    reporting mid-window — its rows simply end there and never resume."""
    station_name = f"{series.city}·演示站{series.location_id:03d}"
    raw_ref = json.dumps(
        {
            "openaq_location_id": f"demo-{series.location_id}",
            "station_name": station_name,
            "provider": "合成演示站点",
            "sensors": [
                {"parameter": name, "unit": "µg/m³"}
                for name in ("pm25", "pm10", "no2", "o3", "so2", "co")
            ],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    bias = 1.0 + rng.uniform(-0.12, 0.18)
    rows: list[tuple] = []
    outage = 0
    last_index = series.hours if stop_after is None else min(stop_after, series.hours)
    # The newest hours always report: a gap or an outage landing on the tail
    # would leave the city hero with no ground reading at all, which reads as a
    # broken page rather than as a missing observation.
    protected_tail = last_index - 3
    for index in range(last_index):
        if outage > 0:
            outage -= 1
            continue
        room = protected_tail - index
        if room > 0:
            if rng.random() < OBSERVATION_OUTAGE_RATE:
                # An outage may not run past the protected tail either.
                outage = min(rng.randint(6, 14), room)
                continue
            if rng.random() < OBSERVATION_MISSING_RATE:
                continue
        values = series.pollutants[index]
        walk = bias * (1.0 + rng.gauss(0.0, 0.03))
        observed = [
            max(0.5, value * walk + rng.gauss(0.0, 1.2)) for value in values[:6]
        ]
        aqi = realtime_aqi(
            pm25=observed[0],
            pm10=observed[1],
            no2=observed[2],
            o3=observed[3],
            so2=observed[4],
            co=observed[5],
        ).aqi
        stamp = series.start + index * HOUR
        rows.append(
            (
                series.location_id,
                source_id,
                _iso(stamp),
                _iso(stamp + timedelta(minutes=20)),
                observed[0],
                observed[1],
                observed[2],
                observed[3],
                observed[4],
                observed[5],
                aqi,
                AQI_STANDARD_TEXT,
                raw_ref,
            )
        )
    return rows


def _forecast_rows(
    series: CitySeries, sources: dict[str, int], rng: random.Random, revision: str
) -> list[tuple]:
    """Six snapshots per model: the older ones land on hours the ground network
    already observed (which is what the backtest page pairs against), the last
    one looks forward 24 hours (which is what the signals strip reads)."""
    truth = series.pm25
    rows: list[tuple] = []
    last = series.hours - 1
    snapshots = [
        index
        for index in (
            last - SNAPSHOT_STEP_HOURS * step for step in range(SNAPSHOT_COUNT - 1, -1, -1)
        )
        if index >= 0
    ]
    for index in snapshots:
        issued_at = _iso(series.start + index * HOUR)
        window = truth[max(0, index - 5) : index + 1]
        rolling_mean = sum(window) / len(window)
        for name, source_name, spec_revision, base_error, growth in MODEL_SPECS:
            model_revision = spec_revision or revision
            for horizon in range(1, FORECAST_HORIZON + 1):
                target = index + horizon
                if target >= len(truth):
                    continue
                if name == "Persistence":
                    value = truth[index]
                elif name == "Rolling Mean":
                    value = rolling_mean
                else:
                    sigma = base_error + growth * horizon
                    value = truth[target] * (1.0 + rng.gauss(0.0, sigma)) + _gauss(0.0, 1.5)
                value = max(1.0, value)
                spread = 0.12 + 0.012 * horizon
                rows.append(
                    (
                        series.location_id,
                        sources.get(source_name) if source_name else None,
                        name,
                        model_revision,
                        issued_at,
                        _iso(series.start + target * HOUR),
                        horizon,
                        "pm25",
                        value,
                        max(0.0, value * (1.0 - spread)),
                        value * (1.0 + spread),
                        "µg/m³",
                        _iso(series.start + index * HOUR),
                        json.dumps(
                            {"provider": SEED_MARKER, "note": "synthetic local library"},
                            ensure_ascii=False,
                        ),
                    )
                )
    return rows


def _write_city(
    series: CitySeries,
    sources: dict[str, int],
    seed: int,
    lstm_revision: str,
    stop_after: int | None = None,
) -> None:
    rng = _rng(seed, series.location_id)
    observed = series.location_id % OBSERVED_CITY_STRIDE != 0
    with transaction() as con:
        con.executemany(
            """
            INSERT INTO air_model_analysis(
                location_id, source_id, valid_at, fetched_at,
                pm25, pm10, no2, o3, so2, co, reference_aqi, quality_flag
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ok')
            """,
            series.model_rows,
        )
        con.executemany(
            """
            INSERT INTO weather_observations(
                location_id, source_id, observed_at, fetched_at,
                temperature_2m, relative_humidity_2m, pressure_msl, precipitation,
                wind_speed_10m, wind_direction_10m, boundary_layer_height,
                quality_flag
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'gridded_archive')
            """,
            series.weather_rows,
        )
        con.executemany(
            """
            INSERT INTO forecasts(
                location_id, source_id, model_name, model_version, issued_at,
                target_at, horizon_hours, variable, predicted_value,
                lower_bound, upper_bound, unit, fetched_at, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            _forecast_rows(series, sources, rng, lstm_revision),
        )
        if observed:
            con.executemany(
                """
                INSERT INTO air_observations(
                    location_id, source_id, observed_at, fetched_at,
                    pm25, pm10, no2, o3, so2, co, aqi, aqi_standard,
                    quality_flag, raw_ref
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'reported', ?)
                """,
                _observation_rows(series, sources["openaq_ground"], rng, stop_after),
            )


def _write_bindings(
    locations: list,
    sources: dict[str, int],
    start: datetime,
    hours: int,
    inactive_id: int | None = None,
) -> None:
    now = datetime.now(UTC)
    sensors = json.dumps(
        [
            {"parameter": name, "unit": "µg/m³"}
            for name in ("pm25", "pm10", "no2", "o3", "so2", "co")
        ],
        ensure_ascii=False,
    )
    rows = []
    for location in locations:
        location_id = int(location["location_id"])
        if location_id % OBSERVED_CITY_STRIDE == 0:
            continue
        stopped = location_id == inactive_id
        rows.append(
            (
                location_id,
                sources["openaq_ground"],
                f"demo-{location_id}",
                f"{location['city']}·演示站{location_id:03d}",
                "合成演示站点",
                float(location["latitude"]),
                float(location["longitude"]),
                sensors,
                _iso(start),
                # A stopped station's binding keeps the last hour it delivered.
                _iso(
                    start
                    + timedelta(
                        hours=hours - OFFLINE_STATION_HOURS - 1 if stopped else hours - 1
                    )
                ),
                _iso(now),
                0 if stopped else 1,
            )
        )
    with transaction() as con:
        con.executemany(
            """
            INSERT INTO provider_bindings(
                location_id, source_id, external_location_id, external_name,
                provider_name, latitude, longitude, sensors_json,
                first_at, last_at, last_checked_at, active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )


def _write_ingestion(rows_written: int, start: datetime, end: datetime) -> None:
    now = datetime.now(UTC)
    message = f"本地演示数据：scripts.seed_demo 生成（{SEED_MARKER}，非真实采集）"
    runs = []
    for provider, dataset in INGESTION_RUNS:
        # The ground batch hit provider rate limits, exactly as a real OpenAQ
        # cycle does: the run still succeeded for most stations, and the system
        # page has to be able to show that.
        partial = dataset == "ground_latest"
        runs.append(
            (
                str(uuid4()),
                provider,
                dataset,
                _iso(now - timedelta(minutes=9)),
                _iso(now - timedelta(minutes=8)),
                _iso(start),
                _iso(end),
                _iso(end),
                rows_written,
                int((end - start) / HOUR),
                PARTIAL_BATCH_ERRORS if partial else 0,
                18.4,
                "partial" if partial else "success",
                (
                    f"{message}；2 个站点批次返回 429 限流，已跳过等待下一轮"
                    if partial
                    else message
                ),
            )
        )
    with transaction() as con:
        con.executemany(
            """
            INSERT INTO ingestion_runs(
                run_id, provider, dataset, started_at, finished_at,
                requested_start, requested_end, latest_source_time,
                inserted_rows, updated_rows, error_count, latency_seconds,
                status, message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            runs,
        )


def _write_model_run(rows_written: int, start: datetime, end: datetime, version: str) -> None:
    """One active LSTM registration with per-horizon validation metrics, in the
    shape backend.ml.lstm writes them: the forecast page compares four models
    and needs every one of them to have a validation row."""
    horizons = list(range(1, FORECAST_HORIZON + 1))
    metrics: dict[str, dict] = {}
    for name, _, _, base_error, growth in MODEL_SPECS:
        scale = 42.0
        mae = [round(scale * (base_error + growth * h) * 0.8, 3) for h in horizons]
        rmse = [round(scale * (base_error + growth * h) * 1.15, 3) for h in horizons]
        metrics[name] = {
            "samples": 420,
            "mae": mae,
            "rmse": rmse,
            "mae_overall": round(sum(mae) / len(mae), 3),
            "rmse_overall": round(sum(rmse) / len(rmse), 3),
        }
    split = start + (end - start) * 4 / 5
    with transaction() as con:
        con.execute(
            """
            INSERT INTO model_runs(
                run_id, model_name, model_version, location_scope, target_variable,
                horizons_json, train_start, train_end, validation_start,
                validation_end, features_json, metrics_json, artifact_path,
                created_at, is_active
            ) VALUES (?, 'LSTM', ?, 'global', 'pm25', ?, ?, ?, ?, ?, ?, ?, NULL, ?, 1)
            """,
            (
                str(uuid4()),
                version,
                json.dumps(horizons),
                _iso(start),
                _iso(split),
                _iso(split),
                _iso(end),
                json.dumps(
                    ["pm25", "pm10", "no2", "o3", "so2", "co", "wind_speed_10m"]
                ),
                json.dumps(metrics, ensure_ascii=False),
                _iso(end),
            ),
        )
    print(f"  预测登记 1 条（{rows_written:,} 行事实数据）")


def _clear_facts() -> None:
    with transaction() as con:
        for table in FACT_TABLES:
            con.execute(f"DELETE FROM {table}")
    # Deleted rows leave their pages in the file; without this a re-seed doubles
    # the library size every time instead of replacing it.
    with connect() as con:
        con.execute("VACUUM")


def _probe(path: Path) -> tuple[int, bool]:
    """Read-only look at an existing file: (analysis rows, is a demo library)."""
    if not path.exists():
        return 0, False
    try:
        con = sqlite3.connect(str(path), timeout=5.0)
    except sqlite3.Error:
        return 0, False
    try:
        rows = int(con.execute("SELECT COUNT(*) FROM air_model_analysis").fetchone()[0])
        demo = int(
            con.execute(
                "SELECT COUNT(*) FROM ingestion_runs WHERE message LIKE ?",
                (f"%{SEED_MARKER}%",),
            ).fetchone()[0]
        )
    except sqlite3.Error:
        return 0, False
    finally:
        con.close()
    return rows, bool(demo)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="生成本地演示数据库（一人一份，与真实采集互不影响）"
    )
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS, help="窗口天数，默认 60")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="随机种子，同种子同数据")
    parser.add_argument("--force", action="store_true", help="已有演示数据时清空重造")
    parser.add_argument("--skip-analysis", action="store_true", help="跳过 PCA 物化（自检用）")
    parser.add_argument("--max-cities", type=int, default=0, help="只造前 N 个城（自检用）")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    path = get_settings().resolved_database_path
    existing, is_demo = _probe(path)
    if existing and not args.force:
        print(f"已有数据：{path}（{existing:,} 行 CAMS 分析）")
        print("要按当前时间重造窗口，再跑一次并加 --force。")
        return
    if existing and not is_demo:
        stamp = datetime.now(UTC).strftime("%Y%m%d%H%M")
        aside = path.with_name(f"{path.stem}.backup-{stamp}{path.suffix}")
        path.replace(aside)
        print(f"这份库不是 seed_demo 生成的，已原样改名保留：{aside}")
    elif existing:
        _clear_facts()

    init_db()
    sources = _source_ids()
    locations = list(active_location_rows())
    if args.max_cities:
        locations = locations[: args.max_cities]
    if not locations:
        raise SystemExit("城市目录为空：先跑 uv run python -m scripts.init_db")

    hours = args.days * 24 + 1
    end = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(hours=hours - 1)
    regimes = _regimes(locations, args.seed)
    version = f"demo-numpy-h16-w24-f24-{start.strftime('%Y%m%d%H%M')}"
    # Degraded states: a stopped station in the west, and the three newest
    # cities sitting where the weather archive has not caught up yet.
    observed = [
        int(location["location_id"])
        for location in locations
        if int(location["location_id"]) % OBSERVED_CITY_STRIDE != 0
    ]
    offline_id = observed[-1] if observed else None
    lagging_ids = {
        int(location["location_id"]) for location in locations[-LAGGING_CITY_COUNT:]
    }
    print(f"生成窗口：{_iso(start)} → {_iso(end)}，{len(locations)} 城 × {hours} 小时")
    print(
        f"  注入降级状态：停报站 #{offline_id}（{OFFLINE_STATION_HOURS}h 前停报），"
        f"气象档案滞后 {sorted(lagging_ids)}，地面批次含 {PARTIAL_BATCH_ERRORS} 个限流错误"
    )

    rows_written = 0
    for index, location in enumerate(locations, start=1):
        location_id = int(location["location_id"])
        series = CitySeries(
            location,
            regimes[location_id],
            sources,
            start,
            hours,
            weather_lag=location_id in lagging_ids,
        )
        _write_city(
            series,
            sources,
            args.seed,
            version,
            stop_after=(
                hours - OFFLINE_STATION_HOURS if location_id == offline_id else None
            ),
        )
        rows_written += len(series.model_rows) + len(series.weather_rows)
        series.release()
        if index % 20 == 0 or index == len(locations):
            print(f"  写入 {index}/{len(locations)} 城")

    _write_bindings(locations, sources, start, hours, inactive_id=offline_id)
    _write_ingestion(rows_written, start, end)
    _write_model_run(rows_written, start, end, version)

    if args.skip_analysis:
        print("已跳过 PCA 物化（--skip-analysis）")
    else:
        _materialize([int(location["location_id"]) for location in locations], hours)

    print(f"完成：{path}")
    print("下一步：双击 start_all.bat，打开 http://127.0.0.1:5173/overview")


def _materialize(location_ids: list[int], hours: int) -> None:
    """Run the real PCA code over the synthetic input: the analysis page then
    shows genuine components, loadings and clusters rather than decoration."""
    window = min(hours, 24 * 90)
    for index, location_id in enumerate(location_ids, start=1):
        try:
            materialize_city_structure(location_id, hours=window, max_components=5)
        except Exception as exc:  # noqa: BLE001 - one city must not stop the rest
            print(f"  城市结构 PCA 跳过 {location_id}：{type(exc).__name__}: {exc}")
        if index % 20 == 0 or index == len(location_ids):
            print(f"  城市结构 PCA {index}/{len(location_ids)}")
    fingerprint = materialize_city_fingerprint(
        hours=window, max_components=5, max_clusters=6
    )
    print(
        f"  全国指纹 PCA：{fingerprint['city_count']} 城 / "
        f"{fingerprint['cluster_count']} 群，轮廓系数 {fingerprint['silhouette']}"
    )


if __name__ == "__main__":
    main()
