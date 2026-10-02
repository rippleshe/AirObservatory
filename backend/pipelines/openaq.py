from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, time
from time import perf_counter
from uuid import uuid4

from backend.config import get_settings
from backend.db import connect, get_location, get_source, transaction
from backend.providers.base import GroundMeasurement, GroundSite
from backend.providers.openaq import OpenAQProvider

PARAMETER_COLUMNS = {
    "pm25": "pm25",
    "pm10": "pm10",
    "no2": "no2",
    "o3": "o3",
    "so2": "so2",
    "co": "co",
}


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat() if value else None


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def _bound_site(location_id: int, source_id: int) -> GroundSite | None:
    with connect() as con:
        row = con.execute(
            """
            SELECT * FROM provider_bindings
            WHERE location_id=? AND source_id=? AND active=1
            """,
            (location_id, source_id),
        ).fetchone()
    if row is None:
        return None
    sensors = json.loads(row["sensors_json"])
    return GroundSite(
        external_location_id=int(row["external_location_id"]),
        name=row["external_name"],
        provider=row["provider_name"],
        country_code="CN",
        latitude=row["latitude"],
        longitude=row["longitude"],
        first_at=_dt(row["first_at"]),
        last_at=_dt(row["last_at"]),
        sensors={str(k): int(v) for k, v in sensors.items()},
        distance_m=0.0,
    )


# Re-discovering all 60 bindings at once adds 60 /locations calls to the same
# burst and trips the per-minute quota; refresh a few stale bindings per cycle.
MAX_BINDING_AGE_HOURS = 24
DISCOVERY_PER_CYCLE = 3


def _stale_binding_ids(locations, source_id: int) -> list[int]:
    """Location ids whose binding discovery is overdue, oldest check first."""
    with connect() as con:
        rows = con.execute(
            """
            SELECT location_id, last_checked_at FROM provider_bindings
            WHERE source_id=? AND active=1
            """,
            (source_id,),
        ).fetchall()
    now = datetime.now(UTC)
    ages: dict[int, float] = {}
    for row in rows:
        checked = _dt(row["last_checked_at"])
        ages[row["location_id"]] = (
            float("inf") if checked is None else (now - checked).total_seconds() / 3600.0
        )
    stale = [
        loc["location_id"]
        for loc in locations
        if ages.get(loc["location_id"], float("inf")) > MAX_BINDING_AGE_HOURS
    ]
    stale.sort(key=lambda location_id: ages.get(location_id, float("inf")), reverse=True)
    return stale


def _save_binding(location_id: int, source_id: int, site: GroundSite) -> None:
    now = datetime.now(UTC).isoformat()
    with transaction() as con:
        con.execute(
            """
            INSERT INTO provider_bindings(
                location_id, source_id, external_location_id, external_name,
                provider_name, latitude, longitude, sensors_json,
                first_at, last_at, last_checked_at, active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(location_id, source_id) DO UPDATE SET
                external_location_id=excluded.external_location_id,
                external_name=excluded.external_name,
                provider_name=excluded.provider_name,
                latitude=excluded.latitude,
                longitude=excluded.longitude,
                sensors_json=excluded.sensors_json,
                first_at=excluded.first_at,
                last_at=excluded.last_at,
                last_checked_at=excluded.last_checked_at,
                active=1
            """,
            (
                location_id,
                source_id,
                str(site.external_location_id),
                site.name,
                site.provider,
                site.latitude,
                site.longitude,
                json.dumps(site.sensors, ensure_ascii=False, sort_keys=True),
                _iso(site.first_at),
                _iso(site.last_at),
                now,
            ),
        )


async def _site_for_location(
    provider: OpenAQProvider,
    location,
    source_id: int,
    force_discovery: bool = False,
) -> GroundSite | None:
    site = _bound_site(location["location_id"], source_id)
    if site is not None and not force_discovery:
        return site
    discovered = await provider.discover_site(location["latitude"], location["longitude"])
    if discovered is not None:
        _save_binding(location["location_id"], source_id, discovered)
        return discovered
    return site


def _upsert_measurements(
    location_id: int,
    source_id: int,
    site: GroundSite,
    points: list[GroundMeasurement],
) -> int:
    if not points:
        return 0
    fetched_at = datetime.now(UTC).isoformat()
    accepted = 0
    # Station-level provenance: one observed_at row carries several parameter
    # columns, and per-parameter refs would overwrite each other on upsert.
    raw_ref = json.dumps(
        {
            "openaq_location_id": site.external_location_id,
            "station_name": site.name,
            "provider": site.provider,
            "sensors": site.sensors,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    with transaction() as con:
        for point in points:
            column = PARAMETER_COLUMNS.get(point.parameter)
            if column is None:
                continue
            quality = "flagged" if point.has_flags else "reported"
            con.execute(
                f"""
                INSERT INTO air_observations(
                    location_id, source_id, observed_at, fetched_at,
                    {column}, quality_flag, raw_ref
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(location_id, source_id, observed_at) DO UPDATE SET
                    fetched_at=excluded.fetched_at,
                    {column}=excluded.{column},
                    quality_flag=CASE
                        WHEN air_observations.quality_flag='flagged'
                          OR excluded.quality_flag='flagged'
                        THEN 'flagged'
                        ELSE 'reported'
                    END,
                    raw_ref=excluded.raw_ref
                """,
                (
                    location_id,
                    source_id,
                    point.observed_at.astimezone(UTC).isoformat(),
                    fetched_at,
                    point.value,
                    quality,
                    raw_ref,
                ),
            )
            accepted += 1
    return accepted


async def refresh_openaq() -> dict:
    settings = get_settings()
    if settings.openaq_api_key is None:
        return {"status": "disabled", "reason": "OPENAQ_API_KEY is not configured"}

    source = get_source("openaq_ground")
    if source is None:
        raise RuntimeError("Database is not initialized with the OpenAQ source")
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
            VALUES (?, 'OpenAQ', 'ground_latest', ?, 'running')
            """,
            (run_id, started.isoformat()),
        )

    # Spread binding re-discovery across cycles instead of one 24h storm.
    stale_bindings = _stale_binding_ids(locations, source["source_id"])
    to_discover = set(stale_bindings[:DISCOVERY_PER_CYCLE])

    semaphore = asyncio.Semaphore(3)

    async with OpenAQProvider(settings) as provider:
        async def fetch(location):
            async with semaphore:
                try:
                    site = await _site_for_location(
                        provider,
                        location,
                        source["source_id"],
                        force_discovery=location["location_id"] in to_discover,
                    )
                    if site is None:
                        return location, None, [], "no PM2.5 site within search radius"
                    points = await provider.fetch_latest(site)
                    return location, site, points, None
                except Exception as exc:
                    return location, None, [], str(exc)

        results = await asyncio.gather(*(fetch(location) for location in locations))

    accepted = 0
    errors: list[str] = []
    no_site: list[str] = []
    latest: datetime | None = None
    for location, site, points, error in results:
        if error is not None:
            errors.append(f'{location["city"]}: {error}')
            continue
        if site is None:
            # A missing nearby station is a coverage gap, not a run failure;
            # reporting it as an error every cycle buried real incidents.
            no_site.append(location["city"])
            continue
        accepted += _upsert_measurements(location["location_id"], source["source_id"], site, points)
        if points:
            point_latest = max(point.observed_at for point in points)
            latest = max(latest, point_latest) if latest else point_latest
            refreshed_site = GroundSite(
                external_location_id=site.external_location_id,
                name=site.name,
                provider=site.provider,
                country_code=site.country_code,
                latitude=site.latitude,
                longitude=site.longitude,
                first_at=site.first_at,
                last_at=point_latest,
                sensors=site.sensors,
                distance_m=site.distance_m,
            )
            _save_binding(location["location_id"], source["source_id"], refreshed_site)

    status = "success" if not errors else ("partial" if accepted else "error")
    message = f"{accepted} latest measurements accepted"
    if no_site:
        message += f"; {len(no_site)} cities without a nearby PM2.5 site: {', '.join(no_site)}"
    if errors:
        message += f"; errors: {' | '.join(errors)}"
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
                _iso(latest),
                accepted,
                len(errors),
                perf_counter() - t0,
                status,
                message,
                run_id,
            ),
        )
    return {
        "run_id": run_id,
        "status": status,
        "accepted": accepted,
        "no_site": no_site,
        "latest_source_time": _iso(latest),
        "errors": errors,
    }


async def backfill_openaq(
    city: str,
    start_date: str,
    end_date: str,
    parameter: str = "pm25",
) -> dict:
    if parameter not in PARAMETER_COLUMNS:
        raise ValueError(f"Unsupported parameter: {parameter}")
    location = get_location(city)
    if location is None:
        raise ValueError(f"Unknown city: {city}")
    source = get_source("openaq_ground")
    if source is None:
        raise RuntimeError("Database is not initialized with the OpenAQ source")

    start = datetime.combine(datetime.fromisoformat(start_date).date(), time.min, tzinfo=UTC)
    end = datetime.combine(datetime.fromisoformat(end_date).date(), time.max, tzinfo=UTC)
    run_id = str(uuid4())
    t0 = perf_counter()
    with transaction() as con:
        con.execute(
            """
            INSERT INTO ingestion_runs(
                run_id, provider, dataset, started_at, requested_start, requested_end, status
            ) VALUES (?, 'OpenAQ', ?, ?, ?, ?, 'running')
            """,
            (
                run_id,
                f"ground_hourly_{parameter}",
                datetime.now(UTC).isoformat(),
                start_date,
                end_date,
            ),
        )

    try:
        async with OpenAQProvider() as provider:
            site = await _site_for_location(provider, location, source["source_id"])
            if site is None:
                raise RuntimeError(f"No OpenAQ PM2.5 site found near {city}")
            points = await provider.fetch_hourly(site, parameter, start, end)
        accepted = _upsert_measurements(location["location_id"], source["source_id"], site, points)
        latest = max((point.observed_at for point in points), default=None)
        with transaction() as con:
            con.execute(
                """
                UPDATE ingestion_runs SET
                    finished_at=?, latest_source_time=?, inserted_rows=?,
                    error_count=0, latency_seconds=?, status='success', message=?
                WHERE run_id=?
                """,
                (
                    datetime.now(UTC).isoformat(),
                    _iso(latest),
                    accepted,
                    perf_counter() - t0,
                    f"{accepted} hourly {parameter} measurements accepted from {site.name}",
                    run_id,
                ),
            )
        return {
            "run_id": run_id,
            "city": city,
            "parameter": parameter,
            "site": site.name,
            "external_location_id": site.external_location_id,
            "points": accepted,
            "latest": _iso(latest),
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
