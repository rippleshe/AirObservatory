from __future__ import annotations

import argparse
import asyncio
import json

from backend.db import init_db
from backend.pipelines.weather import backfill_weather


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--city")
    scope.add_argument("--all", action="store_true")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--batch-size", type=int, default=10)
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    init_db()
    result = await backfill_weather(
        start_date=args.start,
        end_date=args.end,
        city=None if args.all else args.city,
        batch_size=args.batch_size,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
