from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from backend.db import connect


@dataclass(frozen=True)
class ForecastTrainingReadiness:
    ready: bool
    location_id: int
    city: str
    observation_rows: int
    observed_start: str | None
    observed_end: str | None
    span_hours: float
    completeness: float
    reasons: tuple[str, ...]


def check_pm25_training_readiness(
    location_id: int,
    min_rows: int = 24 * 90,
    min_span_days: int = 90,
    min_completeness: float = 0.85,
) -> ForecastTrainingReadiness:
    with connect() as con:
        location = con.execute(
            "SELECT location_id, city FROM locations WHERE location_id=?",
            (location_id,),
        ).fetchone()
        if location is None:
            raise ValueError(f"Unknown location_id={location_id}")

        row = con.execute(
            """
            SELECT COUNT(pm25) AS n,
                   MIN(observed_at) AS first_time,
                   MAX(observed_at) AS last_time
            FROM air_observations
            WHERE location_id=? AND pm25 IS NOT NULL AND quality_flag IN ('ok', 'reported')
            """,
            (location_id,),
        ).fetchone()

    n = int(row["n"] or 0)
    first_time = row["first_time"]
    last_time = row["last_time"]
    span_hours = 0.0
    completeness = 0.0

    if first_time and last_time:
        start = datetime.fromisoformat(first_time)
        end = datetime.fromisoformat(last_time)
        span_hours = max(0.0, (end - start).total_seconds() / 3600)
        expected = max(1.0, span_hours + 1)
        completeness = min(1.0, n / expected)

    reasons: list[str] = []
    if n < min_rows:
        reasons.append(f"ground PM2.5 rows {n} < required {min_rows}")
    if span_hours < min_span_days * 24:
        reasons.append(
            f"ground observation span {span_hours / 24:.1f} days "
            f"< required {min_span_days} days"
        )
    if completeness < min_completeness:
        reasons.append(f"hourly completeness {completeness:.1%} < required {min_completeness:.0%}")

    return ForecastTrainingReadiness(
        ready=not reasons,
        location_id=location["location_id"],
        city=location["city"],
        observation_rows=n,
        observed_start=first_time,
        observed_end=last_time,
        span_hours=span_hours,
        completeness=completeness,
        reasons=tuple(reasons),
    )
