from __future__ import annotations

import math
from dataclasses import dataclass

STANDARD = "HJ 633-2026"

IAQI_BREAKPOINTS = (0, 50, 100, 150, 200, 300, 400, 500)

# HJ 633-2026 table 3. PM10/PM2.5 real-time IAQI uses the daily-average
# breakpoint columns with the current one-hour concentration.
CONCENTRATION_BREAKPOINTS = {
    "pm25": (0, 35, 60, 115, 150, 250, 350, 500),
    "pm10": (0, 50, 120, 250, 350, 420, 500, 600),
    "no2": (0, 100, 200, 700, 1200, 2340, 3090, 3840),
    "o3": (0, 160, 200, 300, 400, 800, 1000, 1200),
    "co": (0, 5, 10, 35, 60, 90, 120, 150),  # mg/m³
    "so2": (0, 150, 500, 650, 800),  # µg/m³; >800 => IAQI 200 for real-time
}

LEVELS = (
    (50, "优"),
    (100, "良"),
    (150, "轻度污染"),
    (200, "中度污染"),
    (300, "重度污染"),
    (500, "严重污染"),
)

HEALTH_GUIDANCE = {
    "优": (
        "空气质量令人满意，基本无空气污染",
        "各类人群可正常活动",
    ),
    "良": (
        "空气质量可接受，但某些污染物可能对极少数异常敏感人群健康有较弱影响",
        "极少数异常敏感人群应减少户外活动",
    ),
    "轻度污染": (
        "敏感人群症状有轻度加剧，健康人群出现刺激症状",
        "青少年儿童、老年人及心血管系统疾病、呼吸系统疾病患者应减少长时间、高强度的户外锻炼",
    ),
    "中度污染": (
        "进一步加剧敏感人群症状，可能对健康人群心血管系统、呼吸系统有影响",
        "青少年儿童、老年人及心血管系统疾病、呼吸系统疾病患者应避免长时间、高强度的户外锻炼，一般人群适量减少户外运动",
    ),
    "重度污染": (
        "心血管系统和呼吸系统患者症状显著加剧，运动耐受力降低，健康人群普遍出现症状",
        "青少年儿童、老年人和心血管系统疾病、呼吸系统疾病患者应停留在室内，停止户外运动，一般人群减少户外运动",
    ),
    "严重污染": (
        "健康人群运动耐受力降低，有明显强烈症状，提前出现某些疾病",
        "青少年儿童、老年人和病人应当留在室内，避免体力消耗，一般人群应避免户外活动",
    ),
}


@dataclass(frozen=True)
class AQIResult:
    aqi: int | None
    level: str | None
    primary_pollutants: tuple[str, ...]
    iaqi: dict[str, int]
    health_effect: str | None
    advice: str | None


def level_of(aqi: int | None) -> str | None:
    if aqi is None:
        return None
    for upper, label in LEVELS:
        if aqi <= upper:
            return label
    return "严重污染"


def iaqi(pollutant: str, concentration: float | None) -> int | None:
    if concentration is None or concentration < 0:
        return None

    key = pollutant.lower()
    if key not in CONCENTRATION_BREAKPOINTS:
        raise ValueError(f"Unsupported pollutant: {pollutant}")

    value = concentration / 1000.0 if key == "co" else concentration
    bounds = CONCENTRATION_BREAKPOINTS[key]

    if key == "so2" and value > 800:
        return 200
    if value >= bounds[-1]:
        return IAQI_BREAKPOINTS[len(bounds) - 1]

    for index in range(1, len(bounds)):
        high = bounds[index]
        if value <= high:
            low = bounds[index - 1]
            iaqi_low = IAQI_BREAKPOINTS[index - 1]
            iaqi_high = IAQI_BREAKPOINTS[index]
            interpolated = (
                (iaqi_high - iaqi_low)
                / (high - low)
                * (value - low)
                + iaqi_low
            )
            return math.ceil(interpolated)
    return None


def realtime_aqi(
    *,
    pm25: float | None,
    pm10: float | None,
    no2: float | None,
    o3: float | None,
    so2: float | None,
    co: float | None,
) -> AQIResult:
    values = {
        "PM2.5": iaqi("pm25", pm25),
        "PM10": iaqi("pm10", pm10),
        "NO₂": iaqi("no2", no2),
        "O₃": iaqi("o3", o3),
        "SO₂": iaqi("so2", so2),
        "CO": iaqi("co", co),
    }
    available = {name: value for name, value in values.items() if value is not None}
    if not available:
        return AQIResult(
            aqi=None,
            level=None,
            primary_pollutants=(),
            iaqi={},
            health_effect=None,
            advice=None,
        )

    overall = max(available.values())
    primary = (
        tuple(name for name, value in available.items() if value == overall)
        if overall > 50
        else ()
    )
    level = level_of(overall)
    health_effect, advice = HEALTH_GUIDANCE[level]
    return AQIResult(
        aqi=overall,
        level=level,
        primary_pollutants=primary,
        iaqi=available,
        health_effect=health_effect,
        advice=advice,
    )
