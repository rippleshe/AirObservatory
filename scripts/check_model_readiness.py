from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from backend.ml.readiness import check_pm25_training_readiness


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--location-id", type=int, default=1)
    args = parser.parse_args()
    result = check_pm25_training_readiness(args.location_id)
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
