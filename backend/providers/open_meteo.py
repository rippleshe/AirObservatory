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

    async def _get(self, params: dict) -> dict:
        settings = get_settings()
        async with httpx.AsyncClient(
            headers={"User-Agent": "AirObservatory/air-quality"},
            timeout=settings.http_timeout_seconds,
        ) as client:
            response = await client.get(AIR_URL, params=params)
            response.raise_for_status()
            return response.json()

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
        return [_point(data, "hourly", i) for i in range(len(data["hourly"]["time"]))]

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
        current = _point(data)
        forecast = tuple(
            _point(data, "hourly", i)
            for i, value in enumerate(data["hourly"]["time"])
            if _dt(value) > current.valid_at
        )[:forecast_hours]
        return ModelLiveBundle(current=current, forecast=forecast)
