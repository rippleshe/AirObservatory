from __future__ import annotations

import math

import pandas as pd

from backend.db import connect, get_source

PCA_FEATURES = (
    "pm25",
    "pm10",
    "no2",
    "o3",
    "so2",
    "co",
    "temperature_2m",
    "relative_humidity_2m",
    "pressure_msl",
    "precipitation",
    "wind_speed_10m",
    "wind_direction_sin",
    "wind_direction_cos",
    "boundary_layer_height",
)


def load_city_feature_frame(location_id: int, hours: int = 24 * 90) -> pd.DataFrame:
    weather_source = get_source("openmeteo_weather_reanalysis")
    if weather_source is None:
        raise RuntimeError("Weather source is not initialized")

    with connect() as con:
        rows = con.execute(
            """
            SELECT
                a.valid_at AS time,
                a.pm25,
                a.pm10,
                a.no2,
                a.o3,
                a.so2,
                a.co,
                w.temperature_2m,
                w.relative_humidity_2m,
                w.pressure_msl,
                w.precipitation,
                w.wind_speed_10m,
                w.wind_direction_10m,
                w.boundary_layer_height
            FROM air_model_analysis a
            JOIN weather_observations w
              ON w.location_id=a.location_id
             AND w.observed_at=a.valid_at
             AND w.source_id=?
            WHERE a.location_id=?
            ORDER BY a.valid_at DESC
            LIMIT ?
            """,
            (weather_source["source_id"], location_id, hours),
        ).fetchall()

    if not rows:
        return pd.DataFrame(columns=("time", *PCA_FEATURES))

    frame = pd.DataFrame([dict(row) for row in reversed(rows)])
    direction = pd.to_numeric(frame.pop("wind_direction_10m"), errors="coerce")
    radians = direction.map(
        lambda value: math.radians(value) if pd.notna(value) else value
    )
    frame["wind_direction_sin"] = radians.map(
        lambda value: math.sin(value) if pd.notna(value) else value
    )
    frame["wind_direction_cos"] = radians.map(
        lambda value: math.cos(value) if pd.notna(value) else value
    )
    return frame[["time", *PCA_FEATURES]]
