from __future__ import annotations

import argparse
import asyncio
import json

from backend.db import init_db
from backend.pipelines.cams import backfill_cams


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--city", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    init_db()
    result = await backfill_cams(args.city, args.start, args.end)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
