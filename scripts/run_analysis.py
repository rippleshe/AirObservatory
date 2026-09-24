from __future__ import annotations

import argparse
import json

from backend.analytics.materialize import materialize_city_structure
from backend.db import get_location, init_db
from backend.repository import active_location_rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--location-id", type=int)
    scope.add_argument("--city")
    scope.add_argument("--all", action="store_true")
    parser.add_argument("--hours", type=int, default=24 * 90)
    parser.add_argument("--components", type=int, default=5)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    init_db()
    if args.all:
        results = []
        errors = []
        for location in active_location_rows():
            try:
                result = materialize_city_structure(
                    int(location["location_id"]),
                    hours=args.hours,
                    max_components=args.components,
                )
                results.append(
                    {
                        "location_id": result["location_id"],
                        "city": result["city"],
                        "sample_count": result["sample_count"],
                        "missing_fraction": result["missing_fraction"],
                        "run_id": result["run_id"],
                    }
                )
            except Exception as exc:
                errors.append(
                    {
                        "location_id": int(location["location_id"]),
                        "city": location["city"],
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
        print(
            json.dumps(
                {
                    "status": "success" if not errors else "partial",
                    "cities": len(results),
                    "errors": errors,
                    "results": results,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    location_id = args.location_id
    if location_id is None:
        location = get_location(args.city)
        if location is None:
            raise SystemExit(f"Unknown city: {args.city}")
        location_id = int(location["location_id"])

    result = materialize_city_structure(
        location_id,
        hours=args.hours,
        max_components=args.components,
    )
    summary = {
        key: result[key]
        for key in (
            "run_id",
            "location_id",
            "city",
            "window_start",
            "window_end",
            "sample_count",
            "input_rows",
            "dropped_rows",
            "missing_fraction",
            "features",
            "explained_variance",
        )
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
