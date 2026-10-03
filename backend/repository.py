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

def national_model_rows() -> list[sqlite3.Row]:
    with connect() as con:
        return con.execute(
            """
            WITH latest AS (
                SELECT location_id, MAX(valid_at) AS valid_at
                FROM air_model_analysis
                GROUP BY location_id
            ),
            current_rows AS (
                SELECT a.*
                FROM latest x
                JOIN air_model_analysis a
                  ON a.location_id=x.location_id AND a.valid_at=x.valid_at
            ),
            previous AS (
                SELECT
                    c.location_id,
                    MAX(h.valid_at) AS previous_time
                FROM current_rows c
                LEFT JOIN air_model_analysis h
                  ON h.location_id=c.location_id
                 AND julianday(h.valid_at)
                     BETWEEN julianday(c.valid_at) - (26.0 / 24.0)
                         AND julianday(c.valid_at) - (22.0 / 24.0)
                GROUP BY c.location_id
            )
            SELECT
                l.location_id,
                l.name,
                l.city,
                l.province,
                l.latitude,
                l.longitude,
                c.valid_at AS source_time,
                c.fetched_at,
                c.pm25,
                c.pm10,
                c.no2,
                c.o3,
                c.so2,
                c.co,
                c.reference_aqi,
                h.pm25 AS pm25_24h,
                (
                    SELECT MAX(o.observed_at)
                    FROM air_observations o
                    WHERE o.location_id=l.location_id
                ) AS latest_ground_time
            FROM current_rows c
            JOIN locations l ON l.location_id=c.location_id
            LEFT JOIN previous p ON p.location_id=c.location_id
            LEFT JOIN air_model_analysis h
              ON h.location_id=c.location_id AND h.valid_at=p.previous_time
            WHERE l.active=1 AND l.station_type='city_reference'
            ORDER BY l.location_id
            """
        ).fetchall()

def latest_city_structure_row(location_id: int) -> sqlite3.Row | None:
    with connect() as con:
        return con.execute(
            """
            SELECT run_id, analysis_type, version, window_start, window_end,
                   created_at, config_json, metrics_json, status
            FROM analysis_runs
            WHERE analysis_type=? AND status='success'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (f"city_structure:{location_id}",),
        ).fetchone()

def coverage_rows(location_id: int, days: int) -> list[sqlite3.Row]:
    with connect() as con:
        return con.execute(
            """
            WITH RECURSIVE dates(day) AS (
                SELECT date('now', ?)
                UNION ALL
                SELECT date(day, '+1 day')
                FROM dates
                WHERE day < date('now')
            ),
            obs AS (
                SELECT substr(observed_at, 1, 10) AS day,
                       COUNT(DISTINCT substr(observed_at, 1, 13)) AS hours
                FROM air_observations
                WHERE location_id=?
                  -- Stored timestamps are 'T'-separated ISO strings while
                  -- datetime('now') emits a space; normalize before comparing.
                  AND observed_at >= replace(datetime('now', ?), ' ', 'T')
                GROUP BY substr(observed_at, 1, 10)
            ),
            model AS (
                SELECT substr(valid_at, 1, 10) AS day,
                       COUNT(DISTINCT substr(valid_at, 1, 13)) AS hours
                FROM air_model_analysis
                WHERE location_id=?
                  AND valid_at >= replace(datetime('now', ?), ' ', 'T')
                GROUP BY substr(valid_at, 1, 10)
            ),
            weather AS (
                SELECT substr(observed_at, 1, 10) AS day,
                       COUNT(DISTINCT substr(observed_at, 1, 13)) AS hours
                FROM weather_observations
                WHERE location_id=?
                  AND observed_at >= replace(datetime('now', ?), ' ', 'T')
                GROUP BY substr(observed_at, 1, 10)
            )
            SELECT dates.day,
                   COALESCE(obs.hours, 0) AS observation_hours,
                   COALESCE(model.hours, 0) AS model_hours,
                   COALESCE(weather.hours, 0) AS weather_hours
            FROM dates
            LEFT JOIN obs USING(day)
            LEFT JOIN model USING(day)
            LEFT JOIN weather USING(day)
            ORDER BY dates.day
            """,
            (
                f"-{days - 1} day",
                location_id,
                f"-{days} day",
                location_id,
                f"-{days} day",
                location_id,
                f"-{days} day",
            ),
        ).fetchall()


def location_binding_rows(location_id: int) -> list[sqlite3.Row]:
    with connect() as con:
        return con.execute(
            """
            SELECT b.location_id, b.provider_name, b.external_name,
                   b.external_location_id, b.first_at, b.last_at, b.active,
                   s.kind, s.is_authoritative
            FROM provider_bindings b
            JOIN sources s ON s.source_id=b.source_id
            WHERE b.location_id=?
            ORDER BY b.provider_name, b.external_name
            """,
            (location_id,),
        ).fetchall()


def location_analysis_rows(location_id: int, limit: int = 10) -> list[sqlite3.Row]:
    with connect() as con:
        return con.execute(
            """
            SELECT run_id, analysis_type, version, window_start, window_end,
                   created_at, status, config_json
            FROM analysis_runs
            WHERE analysis_type LIKE ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (f"%:{location_id}", limit),
        ).fetchall()


def backtest_sample_rows(location_id: int, limit: int = 600) -> list[sqlite3.Row]:
    with connect() as con:
        return con.execute(
            """
            SELECT model_name, model_version, target_at, horizon_hours,
                   predicted_value, observed_value, error, absolute_error
            FROM forecast_backtest_pm25
            WHERE location_id=?
            ORDER BY target_at DESC, model_name, horizon_hours
            LIMIT ?
            """,
            (location_id, limit),
        ).fetchall()

def latest_city_fingerprint_row() -> sqlite3.Row | None:
    with connect() as con:
        return con.execute(
            """
            SELECT run_id, analysis_type, version, window_start, window_end,
                   created_at, config_json, metrics_json, status
            FROM analysis_runs
            WHERE analysis_type='city_fingerprint' AND status='success'
            ORDER BY created_at DESC
            LIMIT 1
            """
        ).fetchone()


def national_series_rows(value_column: str, since: str) -> list[sqlite3.Row]:
    """Hourly model field for every active city since `since`, oldest first."""
    with connect() as con:
        return con.execute(
            f"""
            SELECT a.location_id, l.name, l.province, l.city, l.latitude, l.longitude,
                   a.valid_at AS source_time, a.{value_column} AS value
            FROM air_model_analysis a
            JOIN locations l ON l.location_id=a.location_id
            WHERE l.active=1 AND l.station_type='city_reference'
              AND a.{value_column} IS NOT NULL
              AND a.valid_at>=?
            ORDER BY a.location_id, a.valid_at
            """,
            (since,),
        ).fetchall()


def national_weather_rows(
    since: str, location_id: int | None = None
) -> list[sqlite3.Row]:
    """Hourly weather for every active city (or one) since `since`, oldest first."""
    query = """
        SELECT w.location_id, l.name, l.province, l.latitude, l.longitude,
               w.observed_at, w.wind_speed_10m, w.wind_direction_10m,
               w.temperature_2m
        FROM weather_observations w
        JOIN locations l ON l.location_id=w.location_id
        WHERE l.active=1 AND l.station_type='city_reference'
          AND w.observed_at>=?
    """
    params: list[object] = [since]
    if location_id is not None:
        query += " AND w.location_id=?"
        params.append(location_id)
    query += " ORDER BY w.location_id, w.observed_at"
    with connect() as con:
        return con.execute(query, params).fetchall()
