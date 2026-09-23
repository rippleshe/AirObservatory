from __future__ import annotations

import sqlite3

from .db import connect

TABLES_FOR_STATUS = (
    "locations",
    "provider_bindings",
    "air_observations",
    "air_model_analysis",
    "forecasts",
    "ingestion_runs",
    "model_runs",
)


def table_counts() -> dict[str, int]:
    with connect() as con:
        return {
            name: int(con.execute(f"SELECT COUNT(*) AS n FROM {name}").fetchone()["n"])
            for name in TABLES_FOR_STATUS
        }


def latest_ingestion(provider: str) -> sqlite3.Row | None:
    with connect() as con:
        return con.execute(
            """
            SELECT provider, dataset, started_at, finished_at, latest_source_time,
                   status, message, error_count, latency_seconds
            FROM ingestion_runs
            WHERE provider=?
            ORDER BY started_at DESC
            LIMIT 1
            """,
            (provider,),
        ).fetchone()


def overview_rows(
    table: str,
    time_column: str,
    value_column: str,
    aqi_column: str,
) -> list[sqlite3.Row]:
    with connect() as con:
        return con.execute(
            f"""
            WITH latest AS (
              SELECT location_id, MAX({time_column}) AS source_time
              FROM {table}
              WHERE {value_column} IS NOT NULL
              GROUP BY location_id
            )
            SELECT l.location_id, l.name, l.province, l.latitude, l.longitude,
                   a.{time_column} AS source_time, a.fetched_at,
                   a.{value_column} AS metric_value, a.{aqi_column} AS aqi,
                   a.pm25, a.pm10, a.no2, a.o3, a.quality_flag,
                   s.provider AS source, s.cadence_minutes, s.is_authoritative
            FROM latest x
            JOIN {table} a
              ON a.location_id=x.location_id AND a.{time_column}=x.source_time
            JOIN locations l ON l.location_id=a.location_id
            JOIN sources s ON s.source_id=a.source_id
            WHERE l.active=1 AND l.station_type='city_reference'
            ORDER BY l.location_id
            """
        ).fetchall()


def location_row(location_id: int) -> sqlite3.Row | None:
    with connect() as con:
        return con.execute(
            "SELECT * FROM locations WHERE location_id=? AND active=1",
            (location_id,),
        ).fetchone()


def latest_model_row(location_id: int) -> sqlite3.Row | None:
    with connect() as con:
        return con.execute(
            """
            SELECT a.valid_at AS source_time, a.fetched_at, a.pm25, a.pm10,
                   a.no2, a.o3, a.so2, a.co, a.reference_aqi AS aqi,
                   'European AQI (model reference)' AS aqi_standard,
                   a.quality_flag, s.provider AS source, s.is_authoritative
            FROM air_model_analysis a
            JOIN sources s ON s.source_id=a.source_id
            WHERE a.location_id=?
            ORDER BY a.valid_at DESC
            LIMIT 1
            """,
            (location_id,),
        ).fetchone()


def recent_observation_rows(location_id: int, limit: int = 256) -> list[sqlite3.Row]:
    with connect() as con:
        return con.execute(
            """
            SELECT o.observed_at AS source_time, o.fetched_at, o.pm25, o.pm10,
                   o.no2, o.o3, o.so2, o.co, o.aqi, o.aqi_standard,
                   o.quality_flag, o.raw_ref, s.provider AS source, s.is_authoritative
            FROM air_observations o
            JOIN sources s ON s.source_id=o.source_id
            WHERE o.location_id=?
            ORDER BY o.observed_at DESC
            LIMIT ?
            """,
            (location_id, limit),
        ).fetchall()


def series_rows(
    location_id: int,
    table: str,
    time_column: str,
    value_column: str,
    since: str,
) -> list[sqlite3.Row]:
    with connect() as con:
        return con.execute(
            f"""
            SELECT a.{time_column} AS source_time, a.{value_column} AS value,
                   a.quality_flag, s.provider AS source
            FROM {table} a
            JOIN sources s ON s.source_id=a.source_id
            WHERE a.location_id=?
              AND a.{value_column} IS NOT NULL
              AND a.{time_column}>=?
            ORDER BY a.{time_column}
            """,
            (location_id, since),
        ).fetchall()


def latest_forecast_rows(location_id: int, variable: str) -> list[sqlite3.Row]:
    with connect() as con:
        return con.execute(
            """
            WITH latest AS (
                SELECT model_name, model_version, MAX(issued_at) AS issued_at
                FROM forecasts
                WHERE location_id=? AND variable=?
                GROUP BY model_name, model_version
            )
            SELECT f.*, s.provider AS source
            FROM forecasts f
            JOIN latest x
              ON x.model_name=f.model_name
             AND x.model_version=f.model_version
             AND x.issued_at=f.issued_at
            LEFT JOIN sources s ON s.source_id=f.source_id
            WHERE f.location_id=? AND f.variable=?
            ORDER BY f.model_name, f.target_at
            """,
            (location_id, variable, location_id, variable),
        ).fetchall()

def backtest_rows(location_id: int) -> list[sqlite3.Row]:
    with connect() as con:
        return con.execute(
            """
            SELECT model_name, model_version, horizon_hours, error, absolute_error
            FROM forecast_backtest_pm25
            WHERE location_id=?
            ORDER BY model_name, horizon_hours
            """,
            (location_id,),
        ).fetchall()


def recent_ingestion_rows(limit: int = 20) -> list[sqlite3.Row]:
    with connect() as con:
        return con.execute(
            """
            SELECT provider, dataset, started_at, finished_at, latest_source_time,
                   status, message, error_count, latency_seconds
            FROM ingestion_runs
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()


def provider_binding_rows() -> list[sqlite3.Row]:
    with connect() as con:
        return con.execute(
            """
            SELECT b.location_id, l.city, b.provider_name, b.external_name,
                   b.external_location_id, b.last_at, b.active
            FROM provider_bindings b
            JOIN locations l ON l.location_id=b.location_id
            ORDER BY l.location_id
            """
        ).fetchall()

def active_location_rows() -> list[sqlite3.Row]:
    with connect() as con:
        return con.execute(
            """
            SELECT location_id, name, city, province, latitude, longitude, timezone
            FROM locations
            WHERE active=1 AND station_type='city_reference'
            ORDER BY location_id
            """
        ).fetchall()
