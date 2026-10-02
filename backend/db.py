from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .city_catalog import city_seed_rows
from .config import get_settings

SCHEMA_PATH = Path(__file__).resolve().with_name("schema.sql")

CITY_SEEDS = city_seed_rows()

SOURCE_SEEDS = [
    (
        "openmeteo_cams_analysis",
        "Open-Meteo",
        "model_analysis",
        720,
        0,
        "CAMS atmospheric-model analysis field; not a physical ground observation.",
    ),
    (
        "openmeteo_cams_forecast",
        "Open-Meteo",
        "external_forecast",
        720,
        0,
        "CAMS air-quality forecast accessed through Open-Meteo.",
    ),
    (
        "openaq_ground",
        "OpenAQ",
        "ground_observation",
        60,
        0,
        "Ground or sensor observations distributed by OpenAQ; authority varies by station.",
    ),
    (
        "air_observatory_baseline",
        "Air Observatory",
        "self_forecast",
        60,
        0,
        "Deterministic forecast baselines generated from stored observations.",
    ),
    (
        "openmeteo_weather_reanalysis",
        "Open-Meteo",
        "weather_observation",
        60,
        0,
        (
            "Gridded historical weather/reanalysis features from Open-Meteo; "
            "not a station observation."
        ),
    ),
]


class _AutoCloseConnection(sqlite3.Connection):
    """Close on ``with`` exit so ``with connect() as con:`` blocks don't leak.

    ``sqlite3.Connection`` commits/rolls back on context exit but never
    closes; with ~20 call sites relying on ``with connect()``, fixing the
    behavior here beats touching every one.
    """

    def __exit__(self, exc_type, exc_value, tb):  # type: ignore[override]
        try:
            super().__exit__(exc_type, exc_value, tb)
        finally:
            self.close()


def connect() -> sqlite3.Connection:
    db_path = get_settings().resolved_database_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path, timeout=10.0, factory=_AutoCloseConnection)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    con.execute("PRAGMA synchronous = NORMAL")
    con.execute("PRAGMA busy_timeout = 10000")
    return con


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    con = connect()
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init_db() -> None:
    with transaction() as con:
        con.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        con.executemany(
            """
            INSERT INTO locations(
                location_id, name, city, province, latitude, longitude, timezone, station_type
            )
            VALUES (?, ?, ?, ?, ?, ?, 'Asia/Shanghai', 'city_reference')
            ON CONFLICT(name, station_type, external_id) DO UPDATE SET
                city=excluded.city,
                province=excluded.province,
                latitude=excluded.latitude,
                longitude=excluded.longitude,
                active=1
            """,
            CITY_SEEDS,
        )
        con.executemany(
            """
            INSERT INTO sources(
                name, provider, kind, cadence_minutes, is_authoritative, description
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                provider=excluded.provider,
                kind=excluded.kind,
                cadence_minutes=excluded.cadence_minutes,
                is_authoritative=excluded.is_authoritative,
                description=excluded.description
            """,
            SOURCE_SEEDS,
        )


def get_location(city: str) -> sqlite3.Row | None:
    with connect() as con:
        return con.execute(
            "SELECT * FROM locations WHERE city=? AND active=1 ORDER BY location_id LIMIT 1",
            (city,),
        ).fetchone()


def get_source(name: str) -> sqlite3.Row | None:
    with connect() as con:
        return con.execute("SELECT * FROM sources WHERE name=?", (name,)).fetchone()
