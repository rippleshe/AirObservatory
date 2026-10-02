from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta

from backend.config import get_settings
from backend.db import init_db
from backend.ml.forecasting import refresh_baseline_forecasts
from backend.pipelines.cams import refresh_cams
from backend.pipelines.openaq import refresh_openaq
from backend.pipelines.weather import backfill_weather


async def main() -> None:
    init_db()
    # The archive lags several days; ending at "today" only returns NULL hours.
    settings = get_settings()
    weather_end = datetime.now(UTC).date() - timedelta(days=settings.weather_archive_lag_days)
    weather_start = weather_end - timedelta(days=2)
    cams, openaq, weather = await asyncio.gather(
        refresh_cams(),
        refresh_openaq(),
        backfill_weather(
            start_date=weather_start.isoformat(),
            end_date=weather_end.isoformat(),
            batch_size=10,
        ),
    )
    baselines = refresh_baseline_forecasts()
    print(
        json.dumps(
            {"cams": cams, "openaq": openaq, "weather": weather, "baselines": baselines},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
