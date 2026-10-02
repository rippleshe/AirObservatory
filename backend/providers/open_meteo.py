from __future__ import annotations

from datetime import UTC, datetime

import httpx

from backend.config import Settings, get_settings

from .base import ModelAnalysisPoint, ModelLiveBundle
from .http import request_with_retries

OPEN_METEO_API_VERSION = 1
AIR_URL = (
    "https://air-quality-api.open-meteo.com/"
    f"v{OPEN_METEO_API_VERSION}/air-quality"
)
HOURLY = "pm2_5,pm10,nitrogen_dioxide,ozone,sulphur_dioxide,carbon_monoxide,european_aqi"
USER_AGENT = "AirObservatory/air-quality"


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=UTC)


def _point(data: dict, prefix: str = "current", index: int | None = None) -> ModelAnalysisPoint:
    block = data[prefix]

    def value(name: str):
        values = block.get(name)
        if index is None:
            return values
        return values[index] if values else None

    time_value = block["time"] if index is None else block["time"][index]
    return ModelAnalysisPoint(
        valid_at=_dt(time_value),
        pm25=value("pm2_5"),
        pm10=value("pm10"),
        no2=value("nitrogen_dioxide"),
        o3=value("ozone"),
        so2=value("sulphur_dioxide"),
        co=value("carbon_monoxide"),
        reference_aqi=value("european_aqi"),
    )


class OpenMeteoCAMSProvider:
    name = "openmeteo_cams_analysis"

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> OpenMeteoCAMSProvider:
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
                response = await request_with_retries(client, AIR_URL, params)
                return response.json()
        response = await request_with_retries(self._client, AIR_URL, params)
        return response.json()

    @staticmethod
    def _range_points(data: dict) -> list[ModelAnalysisPoint]:
        return [
            _point(data, "hourly", index)
            for index in range(len(data["hourly"]["time"]))
        ]

    async def fetch_range(
        self,
        latitude: float,
        longitude: float,
        start_date: str,
        end_date: str,
    ) -> list[ModelAnalysisPoint]:
        data = await self._get(
            {
                "latitude": latitude,
                "longitude": longitude,
                "hourly": HOURLY,
                "start_date": start_date,
                "end_date": end_date,
                "timezone": "UTC",
                "domains": "cams_global",
            }
        )
        if not isinstance(data, dict):
            raise RuntimeError("Open-Meteo returned an unexpected multi-location response")
        return self._range_points(data)

    async def fetch_range_batch(
        self,
        coordinates: list[tuple[float, float]],
        start_date: str,
        end_date: str,
    ) -> list[list[ModelAnalysisPoint]]:
        if not coordinates:
            return []
        if len(coordinates) == 1:
            latitude, longitude = coordinates[0]
            return [await self.fetch_range(latitude, longitude, start_date, end_date)]

        data = await self._get(
            {
                "latitude": ",".join(str(latitude) for latitude, _ in coordinates),
                "longitude": ",".join(str(longitude) for _, longitude in coordinates),
                "hourly": HOURLY,
                "start_date": start_date,
                "end_date": end_date,
                "timezone": "UTC",
                "domains": "cams_global",
            }
        )
        if not isinstance(data, list) or len(data) != len(coordinates):
            raise RuntimeError(
                "Open-Meteo historical batch response count does not match coordinates"
            )
        return [self._range_points(item) for item in data]

    @staticmethod
    def _live_bundle(data: dict, forecast_hours: int) -> ModelLiveBundle:
        current = _point(data)
        forecast = tuple(
            _point(data, "hourly", i)
            for i, value in enumerate(data["hourly"]["time"])
            if _dt(value) > current.valid_at
        )[:forecast_hours]
        return ModelLiveBundle(current=current, forecast=forecast)

    async def fetch_live(
        self,
        latitude: float,
        longitude: float,
        forecast_hours: int = 24,
    ) -> ModelLiveBundle:
        data = await self._get(
            {
                "latitude": latitude,
                "longitude": longitude,
                "current": HOURLY,
                "hourly": HOURLY,
                "forecast_hours": forecast_hours + 1,
                "timezone": "UTC",
                "domains": "cams_global",
            }
        )
        if not isinstance(data, dict):
            raise RuntimeError("Open-Meteo returned an unexpected multi-location response")
        return self._live_bundle(data, forecast_hours)

    async def fetch_live_batch(
        self,
        coordinates: list[tuple[float, float]],
        forecast_hours: int = 24,
    ) -> list[ModelLiveBundle]:
        if not coordinates:
            return []
        if len(coordinates) == 1:
            latitude, longitude = coordinates[0]
            return [await self.fetch_live(latitude, longitude, forecast_hours)]

        data = await self._get(
            {
                "latitude": ",".join(str(latitude) for latitude, _ in coordinates),
                "longitude": ",".join(str(longitude) for _, longitude in coordinates),
                "current": HOURLY,
                "hourly": HOURLY,
                "forecast_hours": forecast_hours + 1,
                "timezone": "UTC",
                "domains": "cams_global",
            }
        )
        if not isinstance(data, list) or len(data) != len(coordinates):
            raise RuntimeError(
                "Open-Meteo batch response count does not match requested coordinates"
            )
        return [self._live_bundle(item, forecast_hours) for item in data]
