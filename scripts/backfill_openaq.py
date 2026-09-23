from __future__ import annotations

import argparse
import asyncio
import json

from backend.db import init_db
from backend.pipelines.openaq import backfill_openaq


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--city", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument(
        "--parameter",
        default="pm25",
        choices=("pm25", "pm10", "no2", "o3", "so2", "co"),
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    init_db()
    result = await backfill_openaq(
        args.city,
        args.start,
        args.end,
        parameter=args.parameter,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
