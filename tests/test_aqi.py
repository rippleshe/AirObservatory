from backend.analytics.aqi import iaqi, level_of, realtime_aqi
from backend.city_catalog import CITY_CATALOG


def test_city_catalog_keeps_original_ids_and_expands_national_coverage():
    assert [city.location_id for city in CITY_CATALOG[:10]] == list(range(1, 11))
    assert [city.location_id for city in CITY_CATALOG] == list(range(1, len(CITY_CATALOG) + 1))
    assert len(CITY_CATALOG) == 60


def test_hj633_2026_realtime_breakpoints():
    assert iaqi("pm25", 35) == 50
    assert iaqi("pm25", 60) == 100
    assert iaqi("pm10", 120) == 100
    assert iaqi("no2", 200) == 100
    assert iaqi("o3", 400) == 200
    assert iaqi("co", 10_000) == 100  # provider µg/m³ -> standard mg/m³
    assert iaqi("so2", 801) == 200


def test_realtime_aqi_uses_max_iaqi_and_supports_ties():
    result = realtime_aqi(
        pm25=60,
        pm10=120,
        no2=40,
        o3=100,
        so2=20,
        co=1_000,
    )
    assert result.aqi == 100
    assert result.level == "良"
    assert result.primary_pollutants == ("PM2.5", "PM10")
    assert result.health_effect is not None
    assert result.advice is not None
    assert "减少" in result.advice
    assert level_of(201) == "重度污染"
