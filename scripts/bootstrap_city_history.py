"""Backfill newly geocoded cities without re-fetching the legacy city catalog."""
from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta

from backend.config import get_settings
from backend.pipelines.cams import backfill_cams_catalog
from backend.pipelines.weather import backfill_weather


async def main(min_location_id: int, days: int) -> None:
    today = datetime.now(UTC).date()
    start = (today - timedelta(days=days)).isoformat()
    print(f"New-city CAMS history: location_id >= {min_location_id}, since {start}", flush=True)
    cams = await backfill_cams_catalog(
        start, today.isoformat(), min_location_id=min_location_id,
    )
    print(f"CAMS: {cams}", flush=True)
    archive_end = today - timedelta(days=get_settings().weather_archive_lag_days)
    print(f"New-city weather history through {archive_end}", flush=True)
    weather = await backfill_weather(
        start, archive_end.isoformat(), min_location_id=min_location_id,
    )
    print(f"WEATHER: {weather}", flush=True)
    if cams["status"] != "success" or weather["status"] != "success":
        raise RuntimeError("One or more backfill batches require attention; see ingestion_runs")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-location-id", type=int, default=61)
    parser.add_argument("--days", type=int, default=90)
    args = parser.parse_args()
    if args.min_location_id < 1 or not 1 <= args.days <= 365:
        parser.error("Invalid city id or history window")
    asyncio.run(main(args.min_location_id, args.days))
