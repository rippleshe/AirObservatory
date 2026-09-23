from __future__ import annotations

import pytest

from backend.config import get_settings
from backend.db import init_db


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "air_observatory_test.db"
    monkeypatch.setenv("AIR_OBSERVATORY_DATABASE_PATH", str(db_path))
    get_settings.cache_clear()
    init_db()
    yield db_path
    get_settings.cache_clear()
