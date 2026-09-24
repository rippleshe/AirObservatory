from __future__ import annotations

from datetime import UTC, datetime

import httpx

from backend.config import get_settings

from .base import ModelAnalysisPoint, ModelLiveBundle

OPEN_METEO_API_VERSION = 1
AIR_URL = (
    "https://air-quality-api.open-meteo.com/"
    f"v{OPEN_METEO_API_VERSION}/air-quality"
)
HOURLY = "pm2_5,pm10,nitrogen_dioxide,ozone,sulphur_dioxide,carbon_monoxide,european_aqi"


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

    async def _get(self, params: dict) -> dict | list[dict]:
        settings = get_settings()
        async with httpx.AsyncClient(
            headers={"User-Agent": "AirObservatory/air-quality"},
            timeout=settings.http_timeout_seconds,
        ) as client:
            response = await client.get(AIR_URL, params=params)
            response.raise_for_status()
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
