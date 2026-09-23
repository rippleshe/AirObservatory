from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from backend.config import get_settings
from backend.db import init_db
from backend.ml.forecasting import refresh_baseline_forecasts
from backend.pipelines.cams import refresh_cams
from backend.pipelines.openaq import refresh_openaq

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
    )


if __name__ == "__main__":
    asyncio.run(main())
