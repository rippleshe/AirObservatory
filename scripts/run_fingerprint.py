from __future__ import annotations

import argparse
import json

from backend.analytics.materialize import materialize_city_fingerprint
from backend.db import init_db


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=int, default=24 * 90)
    parser.add_argument("--components", type=int, default=5)
    parser.add_argument("--max-clusters", type=int, default=6)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    init_db()
    result = materialize_city_fingerprint(
        hours=args.hours,
        max_components=args.components,
        max_clusters=args.max_clusters,
    )
    summary = {
        key: result[key]
        for key in (
            "run_id",
            "window_start",
            "window_end",
            "city_count",
            "sample_hours_min",
            "sample_hours_max",
            "cluster_count",
            "silhouette",
            "features",
            "explained_variance",
        )
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
