from __future__ import annotations

from backend.city_catalog import BASE_CITY_CATALOG, CITY_CATALOG

REGIONS = {"东北", "华东", "华中", "华北", "华南", "西北", "西南"}


def test_expanded_city_catalog_preserves_existing_location_ids():
    """The catalog grows by appending verified cities, so the invariants matter
    more than the count: the base 60 keep their ids, the id block stays
    contiguous, names are unique, and every row carries a province, a region and
    coordinates inside China."""
    assert len(BASE_CITY_CATALOG) == 60
    assert CITY_CATALOG[:60] == BASE_CITY_CATALOG
    assert [city.location_id for city in CITY_CATALOG] == list(
        range(1, len(CITY_CATALOG) + 1)
    )
    assert len({city.name for city in CITY_CATALOG}) == len(CITY_CATALOG)
    for city in CITY_CATALOG:
        assert 15 < city.latitude < 55
        assert 73 < city.longitude < 136
        assert city.province
        assert city.region in REGIONS
