from __future__ import annotations

from datetime import UTC, datetime

import httpx

from backend.config import get_settings

from .base import WeatherPoint

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
WEATHER_HOURLY = (
    "temperature_2m,relative_humidity_2m,pressure_msl,precipitation,"
    "wind_speed_10m,wind_direction_10m,boundary_layer_height"
)


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=UTC)


def _points(data: dict) -> list[WeatherPoint]:
    hourly = data["hourly"]
    return [
        WeatherPoint(
            observed_at=_dt(value),
            temperature_2m=hourly["temperature_2m"][index],
            relative_humidity_2m=hourly["relative_humidity_2m"][index],
            pressure_msl=hourly["pressure_msl"][index],
            precipitation=hourly["precipitation"][index],
            wind_speed_10m=hourly["wind_speed_10m"][index],
            wind_direction_10m=hourly["wind_direction_10m"][index],
            boundary_layer_height=hourly["boundary_layer_height"][index],
        )
        for index, value in enumerate(hourly["time"])
    ]


class OpenMeteoWeatherProvider:
    name = "openmeteo_weather_reanalysis"

    async def _get(self, params: dict) -> dict | list[dict]:
        settings = get_settings()
        async with httpx.AsyncClient(
            headers={"User-Agent": "AirObservatory/weather"},
            timeout=settings.http_timeout_seconds,
        ) as client:
            response = await client.get(ARCHIVE_URL, params=params)
            response.raise_for_status()
            return response.json()

    async def fetch_range(
        self,
        latitude: float,
        longitude: float,
        start_date: str,
        end_date: str,
    ) -> list[WeatherPoint]:
        data = await self._get(
            {
                "latitude": latitude,
                "longitude": longitude,
                "hourly": WEATHER_HOURLY,
                "start_date": start_date,
                "end_date": end_date,
                "timezone": "UTC",
            }
        )
        if not isinstance(data, dict):
            raise RuntimeError("Open-Meteo returned an unexpected multi-location response")
        return _points(data)

    async def fetch_range_batch(
        self,
        coordinates: list[tuple[float, float]],
        start_date: str,
        end_date: str,
    ) -> list[list[WeatherPoint]]:
        if not coordinates:
            return []
        if len(coordinates) == 1:
            latitude, longitude = coordinates[0]
            return [await self.fetch_range(latitude, longitude, start_date, end_date)]

        data = await self._get(
            {
                "latitude": ",".join(str(latitude) for latitude, _ in coordinates),
                "longitude": ",".join(str(longitude) for _, longitude in coordinates),
                "hourly": WEATHER_HOURLY,
                "start_date": start_date,
                "end_date": end_date,
                "timezone": "UTC",
            }
        )
        if not isinstance(data, list) or len(data) != len(coordinates):
            raise RuntimeError(
                "Open-Meteo weather batch response count does not match coordinates"
            )
        return [_points(item) for item in data]
