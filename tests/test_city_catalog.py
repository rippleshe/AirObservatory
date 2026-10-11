from __future__ import annotations

from backend.city_catalog import BASE_CITY_CATALOG, CITY_CATALOG


def test_expanded_city_catalog_preserves_existing_location_ids():
    assert len(BASE_CITY_CATALOG) == 60
    assert len(CITY_CATALOG) == 133
    assert CITY_CATALOG[:60] == BASE_CITY_CATALOG
    assert [city.location_id for city in CITY_CATALOG] == list(range(1, 134))
    assert len({city.name for city in CITY_CATALOG}) == 133
    for city in CITY_CATALOG:
        assert 15 < city.latitude < 55
        assert 73 < city.longitude < 136
