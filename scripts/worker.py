from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from backend.config import get_settings
from backend.db import init_db
from backend.ml.forecasting import refresh_baseline_forecasts
from backend.pipelines.cams import refresh_cams
from backend.pipelines.openaq import refresh_openaq
from backend.pipelines.weather import backfill_weather

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("air_observatory.worker")


async def periodic(
    name: str,
    interval_seconds: int,
    job: Callable[[], Awaitable[dict]],
) -> None:
    while True:
        started = asyncio.get_running_loop().time()
        try:
            result = await job()
            logger.info("%s refresh completed: %s", name, result)
        except Exception:
            logger.exception("%s refresh failed", name)
        elapsed = asyncio.get_running_loop().time() - started
        await asyncio.sleep(max(1.0, interval_seconds - elapsed))


async def refresh_observations_and_baselines() -> dict:
    observations = await refresh_openaq()
    baselines = refresh_baseline_forecasts()
    return {"observations": observations, "baselines": baselines}


async def refresh_recent_weather() -> dict:
    today = datetime.now(UTC).date()
    start = today - timedelta(days=2)
    return await backfill_weather(
        start_date=start.isoformat(),
        end_date=today.isoformat(),
        city=None,
        batch_size=10,
    )


async def main() -> None:
    init_db()
    settings = get_settings()
    await asyncio.gather(
        periodic("CAMS", settings.cams_refresh_seconds, refresh_cams),
        periodic(
            "OpenAQ + baselines",
            settings.openaq_refresh_seconds,
            refresh_observations_and_baselines,
        ),
        periodic(
            "weather archive",
            settings.weather_refresh_seconds,
            refresh_recent_weather,
        ),
    )


if __name__ == "__main__":
    asyncio.run(main())
