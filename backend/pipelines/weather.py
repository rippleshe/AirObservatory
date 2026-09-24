from __future__ import annotations

from datetime import UTC, datetime
from time import perf_counter
from uuid import uuid4

from backend.db import connect, get_location, get_source, transaction
from backend.providers.weather import OpenMeteoWeatherProvider


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _locations(city: str | None):
    if city:
        location = get_location(city)
        if location is None:
            raise ValueError(f"Unknown city: {city}")
        return [location]
    with connect() as con:
        return con.execute(
            """
            SELECT * FROM locations
            WHERE active=1 AND station_type='city_reference'
            ORDER BY location_id
            """
        ).fetchall()


async def backfill_weather(
    start_date: str,
    end_date: str,
    city: str | None = None,
    batch_size: int = 10,
) -> dict:
    source = get_source("openmeteo_weather_reanalysis")
    if source is None:
        raise RuntimeError("Database is not initialized with the weather source")

    locations = _locations(city)
    run_id = str(uuid4())
    started = datetime.now(UTC)
    t0 = perf_counter()

    with transaction() as con:
        con.execute(
            """
            INSERT INTO ingestion_runs(
                run_id, provider, dataset, started_at,
                requested_start, requested_end, status
            ) VALUES (?, 'Open-Meteo', 'weather_reanalysis', ?, ?, ?, 'running')
            """,
            (run_id, started.isoformat(), start_date, end_date),
        )

    provider = OpenMeteoWeatherProvider()
    fetched_at = datetime.now(UTC).isoformat()
    accepted = 0
    errors: list[str] = []
    latest_source_time: str | None = None

    try:
        for start in range(0, len(locations), batch_size):
            batch = locations[start : start + batch_size]
            coordinates = [
                (location["latitude"], location["longitude"])
                for location in batch
            ]
            try:
                bundles = await provider.fetch_range_batch(
                    coordinates,
                    start_date,
                    end_date,
                )
                results = list(zip(batch, bundles, strict=True))
            except Exception:
                results = []
                for location in batch:
                    try:
                        points = await provider.fetch_range(
                            location["latitude"],
                            location["longitude"],
                            start_date,
                            end_date,
                        )
                        results.append((location, points))
                    except Exception as exc:
                        errors.append(f'{location["city"]}: {exc}')

            with transaction() as con:
                for location, points in results:
                    rows = [
                        (
                            location["location_id"],
                            source["source_id"],
                            _iso(point.observed_at),
                            fetched_at,
                            point.temperature_2m,
                            point.relative_humidity_2m,
                            point.pressure_msl,
                            point.precipitation,
                            point.wind_speed_10m,
                            point.wind_direction_10m,
                            point.boundary_layer_height,
                        )
                        for point in points
                    ]
                    con.executemany(
                        """
                        INSERT INTO weather_observations(
                            location_id, source_id, observed_at, fetched_at,
                            temperature_2m, relative_humidity_2m, pressure_msl,
                            precipitation, wind_speed_10m, wind_direction_10m,
                            boundary_layer_height, quality_flag
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'gridded_archive')
                        ON CONFLICT(location_id, source_id, observed_at) DO UPDATE SET
                            fetched_at=excluded.fetched_at,
                            temperature_2m=excluded.temperature_2m,
                            relative_humidity_2m=excluded.relative_humidity_2m,
                            pressure_msl=excluded.pressure_msl,
                            precipitation=excluded.precipitation,
                            wind_speed_10m=excluded.wind_speed_10m,
                            wind_direction_10m=excluded.wind_direction_10m,
                            boundary_layer_height=excluded.boundary_layer_height,
                            quality_flag=excluded.quality_flag
                        """,
                        rows,
                    )
                    accepted += len(rows)
                    if points:
                        value = _iso(points[-1].observed_at)
                        latest_source_time = max(latest_source_time or value, value)

        status = "success" if not errors else ("partial" if accepted else "error")
        with transaction() as con:
            con.execute(
                """
                UPDATE ingestion_runs SET
                    finished_at=?, latest_source_time=?, inserted_rows=?,
                    error_count=?, latency_seconds=?, status=?, message=?
                WHERE run_id=?
                """,
                (
                    datetime.now(UTC).isoformat(),
                    latest_source_time,
                    accepted,
                    len(errors),
                    perf_counter() - t0,
                    status,
                    f"{accepted} weather rows accepted across {len(locations)} cities"
                    + (f"; errors: {' | '.join(errors)}" if errors else ""),
                    run_id,
                ),
            )
        return {
            "run_id": run_id,
            "status": status,
            "cities": len(locations),
            "rows": accepted,
            "latest_source_time": latest_source_time,
            "errors": errors,
        }
    except Exception as exc:
        with transaction() as con:
            con.execute(
                """
                UPDATE ingestion_runs SET
                    finished_at=?, error_count=1, latency_seconds=?,
                    status='error', message=?
                WHERE run_id=?
                """,
                (
                    datetime.now(UTC).isoformat(),
                    perf_counter() - t0,
                    str(exc),
                    run_id,
                ),
            )
        raise
