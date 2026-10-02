from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from time import perf_counter
from uuid import uuid4

from backend.config import get_settings
from backend.db import connect, get_location, get_source, transaction
from backend.providers.open_meteo import OpenMeteoCAMSProvider


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat()


def _analysis_only(points: list) -> list:
    """Keep hours the model has actually analysed, not its later projections.

    A range fetch ending "today" blends analysis and forecast hours; the
    forecast tail must not masquerade as analysis rows or "current" snapshots
    start reading the future.
    """
    now = datetime.now(UTC)
    return [point for point in points if point.valid_at <= now]


def _prune_forecast_snapshots(keep_snapshots: int = 3) -> int:
    """Cap per-model ``issued_at`` snapshots in ``forecasts``.

    Every refresh inserts a full forecast matrix under a fresh ``issued_at``
    and nothing removed old ones, so the table grew without bound (~7,200
    rows per CAMS cycle). Keep only the latest snapshots per model.
    """
    with transaction() as con:
        cursor = con.execute(
            """
            DELETE FROM forecasts
            WHERE rowid IN (
                SELECT f.rowid
                FROM forecasts f
                JOIN (
                    SELECT model_name, model_version, issued_at,
                           ROW_NUMBER() OVER (
                               PARTITION BY model_name, model_version
                               ORDER BY issued_at DESC
                           ) AS recency
                    FROM (
                        SELECT DISTINCT model_name, model_version, issued_at
                        FROM forecasts
                    )
                ) snapshots
                  ON snapshots.model_name = f.model_name
                 AND snapshots.model_version = f.model_version
                 AND snapshots.issued_at = f.issued_at
                WHERE snapshots.recency > ?
            )
            """,
            (keep_snapshots,),
        )
        return cursor.rowcount


async def refresh_cams(forecast_hours: int | None = None) -> dict:
    settings = get_settings()
    horizon = forecast_hours or settings.forecast_hours
    source_analysis = get_source("openmeteo_cams_analysis")
    source_forecast = get_source("openmeteo_cams_forecast")
    if source_analysis is None or source_forecast is None:
        raise RuntimeError("Database is not initialized with CAMS sources")

    with connect() as con:
        locations = con.execute(
            """
            SELECT * FROM locations
            WHERE active=1 AND station_type='city_reference'
            ORDER BY location_id
            """
        ).fetchall()

    run_id = str(uuid4())
    started = datetime.now(UTC)
    t0 = perf_counter()
    with transaction() as con:
        con.execute(
            """
            INSERT INTO ingestion_runs(run_id, provider, dataset, started_at, status)
            VALUES (?, 'Open-Meteo', 'cams_live_and_forecast', ?, 'running')
            """,
            (run_id, started.isoformat()),
        )

    accepted_current = 0
    forecast_rows = 0
    errors: list[str] = []
    latest_source_time: str | None = None
    batch_size = 20

    async with OpenMeteoCAMSProvider() as provider:
        for start in range(0, len(locations), batch_size):
            batch = locations[start : start + batch_size]
            coordinates = [
                (location["latitude"], location["longitude"])
                for location in batch
            ]
            try:
                bundles = await provider.fetch_live_batch(
                    coordinates,
                    forecast_hours=horizon,
                )
                batch_results = list(zip(batch, bundles, strict=True))
            except Exception:
                # A batch failure should not take the whole national field offline.
                batch_results = []
                for location in batch:
                    try:
                        bundle = await provider.fetch_live(
                            location["latitude"],
                            location["longitude"],
                            forecast_hours=horizon,
                        )
                        batch_results.append((location, bundle))
                    except Exception as exc:
                        errors.append(f'{location["city"]}: {exc}')
                        batch_results.append((location, None))

            fetched_at = datetime.now(UTC).isoformat()
            # Commit per batch instead of one ~8k-row transaction: a shorter
            # write lock keeps concurrent OpenAQ/weather cycles from dying on
            # `database is locked`.
            with transaction() as con:
                for location, bundle in batch_results:
                    if bundle is None:
                        continue

                    current = bundle.current
                    valid_at = _iso(current.valid_at)
                    latest_source_time = max(latest_source_time or valid_at, valid_at)
                    con.execute(
                        """
                        INSERT INTO air_model_analysis(
                            location_id, source_id, valid_at, fetched_at, model_run_at,
                            pm25, pm10, no2, o3, so2, co, reference_aqi, quality_flag
                        ) VALUES (?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, 'ok')
                        ON CONFLICT(location_id, source_id, valid_at) DO UPDATE SET
                            fetched_at=excluded.fetched_at,
                            pm25=excluded.pm25,
                            pm10=excluded.pm10,
                            no2=excluded.no2,
                            o3=excluded.o3,
                            so2=excluded.so2,
                            co=excluded.co,
                            reference_aqi=excluded.reference_aqi,
                            quality_flag='ok'
                        """,
                        (
                            location["location_id"],
                            source_analysis["source_id"],
                            valid_at,
                            fetched_at,
                            current.pm25,
                            current.pm10,
                            current.no2,
                            current.o3,
                            current.so2,
                            current.co,
                            current.reference_aqi,
                        ),
                    )
                    accepted_current += 1

                    snapshot_at = valid_at
                    model_revision = "cams-global-openmeteo"
                    for hours_ahead, point in enumerate(bundle.forecast, start=1):
                        for variable, value, unit in (
                            ("pm25", point.pm25, "µg/m³"),
                            ("pm10", point.pm10, "µg/m³"),
                            ("no2", point.no2, "µg/m³"),
                            ("o3", point.o3, "µg/m³"),
                            ("reference_aqi", point.reference_aqi, "EAQI"),
                        ):
                            if value is None:
                                continue
                            con.execute(
                                """
                                INSERT INTO forecasts(
                                    location_id, source_id, model_name, model_version,
                                    issued_at, target_at, horizon_hours, variable,
                                    predicted_value, unit, fetched_at, metadata_json
                                ) VALUES (?, ?, 'CAMS', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                ON CONFLICT(
                                    location_id, model_name, model_version,
                                    issued_at, target_at, variable
                                ) DO UPDATE SET
                                    predicted_value=excluded.predicted_value,
                                    fetched_at=excluded.fetched_at,
                                    metadata_json=excluded.metadata_json
                                """,
                                (
                                    location["location_id"],
                                    source_forecast["source_id"],
                                    model_revision,
                                    snapshot_at,
                                    _iso(point.valid_at),
                                    hours_ahead,
                                    variable,
                                    value,
                                    unit,
                                    fetched_at,
                                    json.dumps(
                                        {
                                            "provider": "Open-Meteo",
                                            "domain": "cams_global",
                                            "snapshot_semantics": "source_valid_time_proxy",
                                        },
                                        ensure_ascii=False,
                                    ),
                                ),
                            )
                            forecast_rows += 1

            # Yield the write lock between batches so concurrent loops are not
            # starved by back-to-back transactions.
            await asyncio.sleep(0.25)

    pruned = _prune_forecast_snapshots()

    finished = datetime.now(UTC)
    status = "success" if not errors else ("partial" if accepted_current else "error")
    with transaction() as con:
        con.execute(
            """
            UPDATE ingestion_runs SET
                finished_at=?, latest_source_time=?, inserted_rows=?,
                error_count=?, latency_seconds=?, status=?, message=?
            WHERE run_id=?
            """,
            (
                finished.isoformat(),
                latest_source_time,
                accepted_current + forecast_rows,
                len(errors),
                perf_counter() - t0,
                status,
                f"{accepted_current} current locations; {forecast_rows} forecast values"
                + (f"; pruned {pruned} stale forecast rows" if pruned else "")
                + (f"; errors: {' | '.join(errors)}" if errors else ""),
                run_id,
            ),
        )

    return {
        "run_id": run_id,
        "locations": accepted_current,
        "forecast_values": forecast_rows,
        "pruned_forecast_rows": pruned,
        "errors": errors,
        "latest_source_time": latest_source_time,
    }


async def backfill_cams(city: str, start_date: str, end_date: str) -> dict:
    location = get_location(city)
    if location is None:
        raise ValueError(f"Unknown city: {city}")
    source = get_source("openmeteo_cams_analysis")
    if source is None:
        raise RuntimeError("Database is not initialized with CAMS sources")

    run_id = str(uuid4())
    started = datetime.now(UTC)
    t0 = perf_counter()
    with transaction() as con:
        con.execute(
            """
            INSERT INTO ingestion_runs(
                run_id, provider, dataset, started_at, requested_start, requested_end, status
            ) VALUES (?, 'Open-Meteo', 'cams_model_analysis', ?, ?, ?, 'running')
            """,
            (run_id, started.isoformat(), start_date, end_date),
        )

    try:
        async with OpenMeteoCAMSProvider() as provider:
            points = await provider.fetch_range(
                location["latitude"],
                location["longitude"],
                start_date,
                end_date,
            )
        points = _analysis_only(points)
        fetched_at = datetime.now(UTC).isoformat()
        with transaction() as con:
            existing = {
                row["valid_at"]
                for row in con.execute(
                    """
                    SELECT valid_at FROM air_model_analysis
                    WHERE location_id=? AND source_id=?
                      AND valid_at>=? AND valid_at<=?
                    """,
                    (
                        location["location_id"],
                        source["source_id"],
                        f"{start_date}T00:00:00+00:00",
                        f"{end_date}T23:59:59.999999+00:00",
                    ),
                ).fetchall()
            }
            inserted = 0
            updated = 0
            for point in points:
                valid_at = _iso(point.valid_at)
                inserted += int(valid_at not in existing)
                updated += int(valid_at in existing)
                con.execute(
                    """
                    INSERT INTO air_model_analysis(
                        location_id, source_id, valid_at, fetched_at, model_run_at,
                        pm25, pm10, no2, o3, so2, co, reference_aqi, quality_flag
                    ) VALUES (?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, 'ok')
                    ON CONFLICT(location_id, source_id, valid_at) DO UPDATE SET
                        fetched_at=excluded.fetched_at,
                        pm25=excluded.pm25,
                        pm10=excluded.pm10,
                        no2=excluded.no2,
                        o3=excluded.o3,
                        so2=excluded.so2,
                        co=excluded.co,
                        reference_aqi=excluded.reference_aqi,
                        quality_flag=excluded.quality_flag
                    """,
                    (
                        location["location_id"],
                        source["source_id"],
                        valid_at,
                        fetched_at,
                        point.pm25,
                        point.pm10,
                        point.no2,
                        point.o3,
                        point.so2,
                        point.co,
                        point.reference_aqi,
                    ),
                )

            latest = _iso(points[-1].valid_at) if points else None
            con.execute(
                """
                UPDATE ingestion_runs SET
                    finished_at=?, latest_source_time=?, inserted_rows=?, updated_rows=?,
                    error_count=0, latency_seconds=?, status='success', message=?
                WHERE run_id=?
                """,
                (
                    datetime.now(UTC).isoformat(),
                    latest,
                    inserted,
                    updated,
                    perf_counter() - t0,
                    f"{len(points)} model-analysis points accepted",
                    run_id,
                ),
            )
        return {
            "run_id": run_id,
            "city": city,
            "points": len(points),
            "start": start_date,
            "end": end_date,
            "latest": latest,
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
                (datetime.now(UTC).isoformat(), perf_counter() - t0, str(exc), run_id),
            )
        raise

async def backfill_cams_catalog(
    start_date: str,
    end_date: str,
    batch_size: int = 10,
) -> dict:
    source = get_source("openmeteo_cams_analysis")
    if source is None:
        raise RuntimeError("Database is not initialized with CAMS sources")

    with connect() as con:
        locations = con.execute(
            """
            SELECT * FROM locations
            WHERE active=1 AND station_type='city_reference'
            ORDER BY location_id
            """
        ).fetchall()

    run_id = str(uuid4())
    started = datetime.now(UTC)
    t0 = perf_counter()
    with transaction() as con:
        con.execute(
            """
            INSERT INTO ingestion_runs(
                run_id, provider, dataset, started_at,
                requested_start, requested_end, status
            ) VALUES (?, 'Open-Meteo', 'cams_model_analysis_catalog', ?, ?, ?, 'running')
            """,
            (run_id, started.isoformat(), start_date, end_date),
        )

    provider = OpenMeteoCAMSProvider()
    fetched_at = datetime.now(UTC).isoformat()
    inserted = 0
    updated = 0
    accepted = 0
    errors: list[str] = []
    latest: str | None = None

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
                results = [
                    (location, _analysis_only(points))
                    for location, points in results
                ]
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
                        results.append((location, _analysis_only(points)))
                    except Exception as exc:
                        errors.append(f'{location["city"]}: {exc}')

            with transaction() as con:
                for location, points in results:
                    existing = {
                        row["valid_at"]
                        for row in con.execute(
                            """
                            SELECT valid_at FROM air_model_analysis
                            WHERE location_id=? AND source_id=?
                              AND valid_at>=? AND valid_at<=?
                            """,
                            (
                                location["location_id"],
                                source["source_id"],
                                f"{start_date}T00:00:00+00:00",
                                f"{end_date}T23:59:59.999999+00:00",
                            ),
                        ).fetchall()
                    }
                    rows = []
                    for point in points:
                        valid_at = _iso(point.valid_at)
                        inserted += int(valid_at not in existing)
                        updated += int(valid_at in existing)
                        rows.append(
                            (
                                location["location_id"],
                                source["source_id"],
                                valid_at,
                                fetched_at,
                                point.pm25,
                                point.pm10,
                                point.no2,
                                point.o3,
                                point.so2,
                                point.co,
                                point.reference_aqi,
                            )
                        )
                    con.executemany(
                        """
                        INSERT INTO air_model_analysis(
                            location_id, source_id, valid_at, fetched_at, model_run_at,
                            pm25, pm10, no2, o3, so2, co, reference_aqi, quality_flag
                        ) VALUES (?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, 'ok')
                        ON CONFLICT(location_id, source_id, valid_at) DO UPDATE SET
                            fetched_at=excluded.fetched_at,
                            pm25=excluded.pm25,
                            pm10=excluded.pm10,
                            no2=excluded.no2,
                            o3=excluded.o3,
                            so2=excluded.so2,
                            co=excluded.co,
                            reference_aqi=excluded.reference_aqi,
                            quality_flag=excluded.quality_flag
                        """,
                        rows,
                    )
                    accepted += len(rows)
                    if points:
                        value = _iso(points[-1].valid_at)
                        latest = max(latest or value, value)

        status = "success" if not errors else ("partial" if accepted else "error")
        with transaction() as con:
            con.execute(
                """
                UPDATE ingestion_runs SET
                    finished_at=?, latest_source_time=?, inserted_rows=?, updated_rows=?,
                    error_count=?, latency_seconds=?, status=?, message=?
                WHERE run_id=?
                """,
                (
                    datetime.now(UTC).isoformat(),
                    latest,
                    inserted,
                    updated,
                    len(errors),
                    perf_counter() - t0,
                    status,
                    f"{accepted} model-analysis points across {len(locations)} cities"
                    + (f"; errors: {' | '.join(errors)}" if errors else ""),
                    run_id,
                ),
            )
        return {
            "run_id": run_id,
            "status": status,
            "cities": len(locations),
            "points": accepted,
            "inserted": inserted,
            "updated": updated,
            "latest": latest,
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
