from __future__ import annotations

import asyncio
import json

from backend.db import init_db
from backend.ml.forecasting import refresh_baseline_forecasts
from backend.pipelines.cams import refresh_cams
from backend.pipelines.openaq import refresh_openaq


async def main() -> None:
    init_db()
    cams, openaq = await asyncio.gather(refresh_cams(), refresh_openaq())
    baselines = refresh_baseline_forecasts()
    print(
        json.dumps(
            {"cams": cams, "openaq": openaq, "baselines": baselines},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
