from __future__ import annotations

from datetime import UTC, datetime

import httpx

from backend.config import Settings, get_settings

from .base import WeatherPoint
from .http import request_with_retries

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
WEATHER_HOURLY = (
    "temperature_2m,relative_humidity_2m,pressure_msl,precipitation,"
    "wind_speed_10m,wind_direction_10m,boundary_layer_height"
)
USER_AGENT = "AirObservatory/weather"


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

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> OpenMeteoWeatherProvider:
        self._client = httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT},
            timeout=self.settings.http_timeout_seconds,
        )
        return self

    async def __aexit__(self, *_args: object) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _get(self, params: dict) -> dict | list[dict]:
        if self._client is None:
            # Tolerate single-shot callers that skip the context manager.
            async with httpx.AsyncClient(
                headers={"User-Agent": USER_AGENT},
                timeout=self.settings.http_timeout_seconds,
            ) as client:
                response = await request_with_retries(client, ARCHIVE_URL, params)
                return response.json()
        response = await request_with_retries(self._client, ARCHIVE_URL, params)
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
