from __future__ import annotations

from datetime import UTC, datetime, timedelta

from backend.db import connect, get_source
from backend.pipelines.openaq import (
    _record_missing_site,
    _save_binding,
    _stale_binding_ids,
)
from backend.providers.base import GroundSite


def test_missing_site_is_durable_and_skipped_until_recheck(isolated_db):
    source = get_source("openaq_ground")
    assert source is not None
    source_id = source["source_id"]
    with connect() as con:
        rows = con.execute(
            "SELECT location_id FROM locations ORDER BY location_id"
        ).fetchall()
    before = _stale_binding_ids(rows, source_id)
    assert before[0] == 1
    _record_missing_site(1, source_id)
    after = _stale_binding_ids(rows, source_id)
    assert 1 not in after
    assert after[0] == 2


def test_fetch_updates_last_data_time_without_erasing_discovery_age(isolated_db):
    source = get_source("openaq_ground")
    assert source is not None
    sid = source["source_id"]
    site = GroundSite(
        external_location_id=42,
        name="Example", provider="OpenAQ", country_code="CN",
        latitude=39.9, longitude=116.4,
        first_at=None, last_at=datetime.now(UTC) - timedelta(days=3),
        sensors={"pm25": 1}, distance_m=0,
    )
    _save_binding(1, sid, site)
    with connect() as con:
        first = con.execute(
            "SELECT last_checked_at FROM provider_bindings WHERE location_id=1"
        ).fetchone()[0]
    refreshed = GroundSite(
        external_location_id=42,
        name="Example", provider="OpenAQ", country_code="CN",
        latitude=39.9, longitude=116.4,
        first_at=None, last_at=datetime.now(UTC),
        sensors={"pm25": 1}, distance_m=0,
    )
    _save_binding(1, sid, refreshed, discovered=False)
    with connect() as con:
        row = con.execute(
            "SELECT last_at,last_checked_at FROM provider_bindings WHERE location_id=1"
        ).fetchone()
    assert row["last_checked_at"] == first
    assert datetime.fromisoformat(row["last_at"]) > site.last_at
