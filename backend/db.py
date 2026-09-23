from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .config import get_settings

SCHEMA_PATH = Path(__file__).resolve().with_name("schema.sql")

CITY_SEEDS = [
    ("北京", "北京", "北京", 39.9042, 116.4074),
    ("上海", "上海", "上海", 31.2304, 121.4737),
    ("广州", "广州", "广东", 23.1291, 113.2644),
    ("深圳", "深圳", "广东", 22.5431, 114.0579),
    ("成都", "成都", "四川", 30.5728, 104.0668),
    ("重庆", "重庆", "重庆", 29.5630, 106.5516),
    ("武汉", "武汉", "湖北", 30.5928, 114.3055),
    ("西安", "西安", "陕西", 34.3416, 108.9398),
    ("杭州", "杭州", "浙江", 30.2741, 120.1551),
    ("南京", "南京", "江苏", 32.0603, 118.7969),
]

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
]


def connect() -> sqlite3.Connection:
    db_path = get_settings().resolved_database_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path, timeout=5.0)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    con.execute("PRAGMA synchronous = NORMAL")
    con.execute("PRAGMA busy_timeout = 5000")
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
            INSERT INTO locations(name, city, province, latitude, longitude, timezone, station_type)
            VALUES (?, ?, ?, ?, ?, 'Asia/Shanghai', 'city_reference')
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
