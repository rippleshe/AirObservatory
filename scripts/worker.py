from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from backend.analytics.materialize import materialize_city_fingerprint, materialize_city_structure
from backend.config import get_settings
from backend.db import init_db, transaction
from backend.ml import lstm_pipeline
from backend.ml.forecasting import refresh_baseline_forecasts
from backend.pipelines.cams import refresh_cams
from backend.pipelines.openaq import refresh_openaq
from backend.pipelines.weather import backfill_weather
from backend.repository import active_location_rows, latest_city_fingerprint_row
from scripts.backup import backup_database, prune_backups

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("air_observatory.worker")


async def periodic(
    name: str,
    interval_seconds: int,
    job: Callable[[], Awaitable[dict]],
    initial_delay: float = 0.0,
) -> None:
    if initial_delay > 0:
        # Stagger loop starts so the first cycles do not fight over the
        # SQLite write lock (a CAMS refresh commits ~8k rows).
        await asyncio.sleep(initial_delay)
    while True:
        started = asyncio.get_running_loop().time()
        try:
            result = await job()
            status = result.get("status") if isinstance(result, dict) else None
            if status == "disabled":
                # A missing API key used to log as a routine "completed" line.
                logger.error("%s is disabled by configuration: %s", name, result)
            else:
                logger.info("%s refresh completed: %s", name, result)
        except Exception:
            logger.exception("%s refresh failed", name)
        elapsed = asyncio.get_running_loop().time() - started
        sleep_for = max(1.0, interval_seconds - elapsed)
        logger.info("%s cycle took %.1fs; next run in %.0fs", name, elapsed, sleep_for)
        await asyncio.sleep(sleep_for)


async def refresh_observations_and_baselines() -> dict:
    observations = await refresh_openaq()
    baselines = refresh_baseline_forecasts()
    return {"observations": observations, "baselines": baselines}


async def refresh_recent_weather() -> dict:
    # The Open-Meteo archive lags several days: a window ending today only
    # ever returns NULL hours, which is why weather never advanced.
    settings = get_settings()
    end = datetime.now(UTC).date() - timedelta(days=settings.weather_archive_lag_days)
    start = end - timedelta(days=2)
    return await backfill_weather(
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        city=None,
        batch_size=10,
    )


async def refresh_lstm() -> dict:
    # Training runs off-thread: a full sweep takes minutes of numpy and must
    # not stall the event loop the other refresh loops live on.
    if lstm_pipeline.artifact_ready():
        return {"status": "ok", "action": "skipped-fresh"}
    return await asyncio.to_thread(lstm_pipeline.train_and_register)


async def archive_database() -> dict:
    def archive() -> dict:
        path = backup_database()
        return {"status": "ok", "backup": str(path), "expired": prune_backups(path.parent)}

    return await asyncio.to_thread(archive)


async def refresh_research_statistics() -> dict:
    """Update stored research products when the aligned archive has advanced."""
    def refresh() -> dict:
        from backend.db import connect

        with connect() as con:
            newest = con.execute(
                "SELECT MAX(observed_at) FROM weather_observations"
            ).fetchone()[0]
            eligible = con.execute(
                "SELECT COUNT(DISTINCT location_id) FROM weather_observations "
                "WHERE observed_at >= datetime('now', '-14 days')"
            ).fetchone()[0]
        previous = latest_city_fingerprint_row()
        previous_size = (
            json.loads(previous["metrics_json"]).get("eligible_city_count", 0)
            if previous else 0
        )
        if newest is None or (
            previous
            and previous_size >= eligible
            and datetime.fromisoformat(previous["created_at"])
            >= datetime.now(UTC) - timedelta(hours=20)
        ):
            return {"status": "ok", "action": "already-current"}
        completed = 0
        for city in active_location_rows():
            try:
                materialize_city_structure(int(city["location_id"]))
                completed += 1
            except ValueError as exc:
                logger.warning("PCA skipped for %s: %s", city["city"], exc)
        fingerprint = materialize_city_fingerprint()
        return {
            "status": "ok",
            "city_pca": completed,
            "fingerprint_cities": fingerprint["city_count"],
            "analysis_end": fingerprint["window_end"],
        }

    return await asyncio.to_thread(refresh)


def _fail_stale_running_runs() -> None:
    """A worker that died mid-run leaves 'running' rows that never resolve."""
    with transaction() as con:
        cursor = con.execute(
            """
            UPDATE ingestion_runs SET
                status='error',
                finished_at=?,
                message='worker restart observed before this run finished'
            WHERE status='running'
            """,
            (datetime.now(UTC).isoformat(),),
        )
        if cursor.rowcount:
            logger.warning(
                "Marked %d stale 'running' ingestion runs as error", cursor.rowcount
            )


async def main() -> None:
    init_db()
    settings = get_settings()
    _fail_stale_running_runs()
    logger.info(
        "Air Observatory worker started "
        "(CAMS every %ss, OpenAQ every %ss, weather archive every %ss, db=%s, OpenAQ key=%s)",
        settings.cams_refresh_seconds,
        settings.openaq_refresh_seconds,
        settings.weather_refresh_seconds,
        settings.resolved_database_path,
        "configured" if settings.openaq_api_key else "MISSING",
    )
    if settings.openaq_api_key is None:
        logger.error("OPENAQ_API_KEY is not set; ground-observation refresh will be skipped")
    await asyncio.gather(
        periodic("CAMS", settings.cams_refresh_seconds, refresh_cams),
        periodic(
            "OpenAQ + baselines",
            settings.openaq_refresh_seconds,
            refresh_observations_and_baselines,
            initial_delay=8.0,
        ),
        periodic(
            "weather archive",
            settings.weather_refresh_seconds,
            refresh_recent_weather,
            initial_delay=20.0,
        ),
        periodic(
            "LSTM nightly",
            86_400,
            refresh_lstm,
            initial_delay=45.0,
        ),
        periodic("verified database backup", 3600, archive_database, initial_delay=5.0),
        periodic(
            "research statistics",
            86_400,
            refresh_research_statistics,
            initial_delay=150.0,
        ),
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Worker stopped")
