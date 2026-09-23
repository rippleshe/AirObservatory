from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from backend.db import connect, get_source, transaction

from .baselines import persistence, rolling_mean


def refresh_baseline_forecasts(max_age_hours: int = 3, horizon_hours: int = 24) -> dict:
    source = get_source("air_observatory_baseline")
    if source is None:
        raise RuntimeError("Database is not initialized with the baseline forecast source")

    with connect() as con:
        locations = con.execute(
            """
            SELECT location_id, city
            FROM locations
            WHERE active=1 AND station_type='city_reference'
            ORDER BY location_id
            """
        ).fetchall()

    generated = 0
    skipped: list[str] = []
    now = datetime.now(UTC)

    with transaction() as con:
        for location in locations:
            rows = con.execute(
                """
                SELECT observed_at, pm25
                FROM air_observations
                WHERE location_id=?
                  AND pm25 IS NOT NULL
                  AND quality_flag IN ('ok', 'reported')
                ORDER BY observed_at DESC
                LIMIT 24
                """,
                (location["location_id"],),
            ).fetchall()
            if not rows:
                skipped.append(f'{location["city"]}: no PM2.5 observations')
                continue

            issued_at = datetime.fromisoformat(rows[0]["observed_at"].replace("Z", "+00:00"))
            if now - issued_at.astimezone(UTC) > timedelta(hours=max_age_hours):
                skipped.append(f'{location["city"]}: latest observation is stale')
                continue

            history = [float(row["pm25"]) for row in reversed(rows)]
            predictions = {
                "Persistence": persistence(history, horizon_hours),
                "Rolling Mean": rolling_mean(
                    history,
                    horizon=horizon_hours,
                    window=min(6, len(history)),
                ),
            }
            fetched_at = now.isoformat()

            for model_name, values in predictions.items():
                for horizon, value in enumerate(values, start=1):
                    target_at = issued_at + timedelta(hours=horizon)
                    con.execute(
                        """
                        INSERT INTO forecasts(
                            location_id, source_id, model_name, model_version,
                            issued_at, target_at, horizon_hours, variable,
                            predicted_value, unit, fetched_at, metadata_json
                        ) VALUES (?, ?, ?, 'baseline', ?, ?, ?, 'pm25', ?, 'µg/m³', ?, ?)
                        ON CONFLICT(
                            location_id, model_name, model_version,
                            issued_at, target_at, variable
                        ) DO UPDATE SET
                            predicted_value=excluded.predicted_value,
                            fetched_at=excluded.fetched_at,
                            metadata_json=excluded.metadata_json
                        """,
                        (
                            location["location_id"],
                            source["source_id"],
                            model_name,
                            issued_at.isoformat(),
                            target_at.isoformat(),
                            horizon,
                            value,
                            fetched_at,
                            json.dumps(
                                {
                                    "inputs": len(history),
                                    "source": "ground_observation",
                                },
                                ensure_ascii=False,
                            ),
                        ),
                    )
                    generated += 1

    return {"generated": generated, "skipped": skipped}
