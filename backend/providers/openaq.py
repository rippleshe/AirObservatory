from __future__ import annotations

import asyncio
import math
from datetime import UTC, datetime
from typing import Any

import httpx

from backend.config import Settings, get_settings

from .base import GroundMeasurement, GroundSite

API_ROOT = "https://api.openaq.org/v3"
SUPPORTED_PARAMETERS = {"pm25", "pm10", "no2", "o3", "so2", "co"}


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


class OpenAQProvider:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        secret = self.settings.openaq_api_key
        if secret is None:
            raise RuntimeError("OPENAQ_API_KEY is not configured")
        self._client = httpx.AsyncClient(
            base_url=API_ROOT,
            headers={
                "X-API-Key": secret.get_secret_value(),
                "User-Agent": "AirObservatory/air-quality",
            },
            timeout=self.settings.http_timeout_seconds,
        )

    async def __aenter__(self) -> OpenAQProvider:
        return self

    async def __aexit__(self, *_args: object) -> None:
        await self._client.aclose()

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = await self._client.get(path, params=params)
                if response.status_code == 429 or response.status_code >= 500:
                    retry_after = response.headers.get("Retry-After")
                    delay = (
                        float(retry_after)
                        if retry_after and retry_after.isdigit()
                        else 0.5 * (2**attempt)
                    )
                    await asyncio.sleep(min(delay, 5.0))
                    continue
                response.raise_for_status()
                return response.json()
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                last_error = exc
                if attempt < 2:
                    await asyncio.sleep(0.5 * (2**attempt))
        if last_error is not None:
            raise last_error
        raise RuntimeError(f"OpenAQ request failed after retries: {path}")

    async def discover_site(
        self,
        latitude: float,
        longitude: float,
        country_code: str = "CN",
    ) -> GroundSite | None:
        payload = await self._get(
            "/locations",
            {
                "coordinates": f"{latitude:.4f},{longitude:.4f}",
                "radius": self.settings.openaq_radius_m,
                "parameters_id": 2,
                "limit": 100,
                "page": 1,
            },
        )
        sites: list[GroundSite] = []
        for row in payload.get("results", []):
            coordinates = row.get("coordinates") or {}
            lat = coordinates.get("latitude")
            lon = coordinates.get("longitude")
            if lat is None or lon is None:
                continue
            country = (row.get("country") or {}).get("code")
            if country and country != country_code:
                continue

            sensors: dict[str, int] = {}
            for sensor in row.get("sensors", []):
                parameter = sensor.get("parameter") or {}
                name = parameter.get("name")
                if name in SUPPORTED_PARAMETERS and sensor.get("id") is not None:
                    sensors[name] = int(sensor["id"])
            if "pm25" not in sensors:
                continue

            sites.append(
                GroundSite(
                    external_location_id=int(row["id"]),
                    name=str(row.get("name") or f"OpenAQ {row['id']}"),
                    provider=str((row.get("provider") or {}).get("name") or "OpenAQ"),
                    country_code=country,
                    latitude=float(lat),
                    longitude=float(lon),
                    first_at=_dt((row.get("datetimeFirst") or {}).get("utc")),
                    last_at=_dt((row.get("datetimeLast") or {}).get("utc")),
                    sensors=sensors,
                    distance_m=_distance_m(latitude, longitude, float(lat), float(lon)),
                )
            )
        if not sites:
            return None

        now = datetime.now(UTC)

        def score(site: GroundSite) -> tuple[int, float, float, float]:
            last = site.last_at
            first = site.first_at
            recent = int(last is not None and (now - last).total_seconds() <= 24 * 3600)
            last_ts = last.timestamp() if last else 0.0
            span = (last - first).total_seconds() if last and first else 0.0
            return recent, last_ts, span, -site.distance_m

        return max(sites, key=score)

    async def fetch_latest(self, site: GroundSite) -> list[GroundMeasurement]:
        payload = await self._get(f"/locations/{site.external_location_id}/latest", {"limit": 100})
        sensor_to_parameter = {sensor_id: name for name, sensor_id in site.sensors.items()}
        points: list[GroundMeasurement] = []
        for row in payload.get("results", []):
            sensor_id = int(row["sensorsId"])
            parameter = sensor_to_parameter.get(sensor_id)
            observed_at = _dt((row.get("datetime") or {}).get("utc"))
            if parameter is None or observed_at is None:
                continue
            points.append(
                GroundMeasurement(
                    observed_at=observed_at,
                    parameter=parameter,
                    value=float(row["value"]),
                    unit="µg/m³",
                    sensor_id=sensor_id,
                )
            )
        return points

    async def fetch_hourly(
        self,
        site: GroundSite,
        parameter: str,
        start: datetime,
        end: datetime,
    ) -> list[GroundMeasurement]:
        sensor_id = site.sensors.get(parameter)
        if sensor_id is None:
            return []

        points: list[GroundMeasurement] = []
        page = 1
        limit = 1000
        while True:
            payload = await self._get(
                f"/sensors/{sensor_id}/hours",
                {
                    "datetime_from": start.astimezone(UTC).isoformat(),
                    "datetime_to": end.astimezone(UTC).isoformat(),
                    "limit": limit,
                    "page": page,
                },
            )
            rows = payload.get("results", [])
            for row in rows:
                observed_at = _dt(((row.get("period") or {}).get("datetimeFrom") or {}).get("utc"))
                if observed_at is None or row.get("value") is None:
                    continue
                points.append(
                    GroundMeasurement(
                        observed_at=observed_at,
                        parameter=parameter,
                        value=float(row["value"]),
                        unit=str((row.get("parameter") or {}).get("units") or "µg/m³"),
                        sensor_id=sensor_id,
                        has_flags=bool((row.get("flagInfo") or {}).get("hasFlags")),
                    )
                )

            if len(rows) < limit:
                break
            page += 1
            if page > 100:
                raise RuntimeError("OpenAQ pagination exceeded 100 pages")
        return points
