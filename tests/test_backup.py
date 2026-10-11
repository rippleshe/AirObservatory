from __future__ import annotations

import sqlite3

import pytest

from scripts.backup import backup_database, restore_to_new_file


def test_online_backup_roundtrip_and_never_overwrites(tmp_path):
    source = tmp_path / "live.db"
    with sqlite3.connect(source) as con:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("CREATE TABLE readings (time TEXT PRIMARY KEY, value REAL)")
        con.execute("INSERT INTO readings VALUES ('2026-10-11T00:00Z', 17.5)")
    archive = backup_database(source, tmp_path / "archive")
    recovered = tmp_path / "restore.db"
    restore_to_new_file(archive, recovered)
    with sqlite3.connect(recovered) as con:
        assert con.execute("SELECT value FROM readings").fetchone()[0] == 17.5
        assert con.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    with pytest.raises(FileExistsError):
        restore_to_new_file(archive, recovered)


def test_corrupted_backup_never_leaves_partial_restore(tmp_path):
    source = tmp_path / "corrupted.db.gz"
    source.write_bytes(b"invalid gzip")
    target = tmp_path / "recovered.db"
    with pytest.raises(OSError):
        restore_to_new_file(source, target)
    assert not target.exists()
