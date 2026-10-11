"""Crash-safe SQLite backups. The source may be in WAL mode and actively written."""
from __future__ import annotations

import gzip
import os
import shutil
import sqlite3
import tempfile
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

from backend.config import get_settings


def backup_database(source: Path | None = None, destination: Path | None = None) -> Path:
    db = source or get_settings().resolved_database_path
    folder = destination or db.parent / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    # Do not create a fresh empty database when the expected source is missing.
    if not db.is_file():
        raise FileNotFoundError(db)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    archive = folder / f"air_observatory-{stamp}.db.gz"
    temp_db: Path | None = None
    temp_gz = archive.with_suffix(".gz.part")
    try:
        with tempfile.NamedTemporaryFile(
            prefix="sqlite-snapshot-", suffix=".db", dir=folder, delete=False
        ) as f:
            temp_db = Path(f.name)
        with (
            closing(
                sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=30)
            ) as source_con,
            closing(sqlite3.connect(temp_db)) as backup_con,
        ):
            source_con.backup(backup_con, pages=256, sleep=0.1)
            status = backup_con.execute("PRAGMA quick_check").fetchone()[0]
            if status != "ok":
                raise RuntimeError(f"Snapshot failed SQLite integrity check: {status}")
        with temp_db.open("rb") as origin, gzip.open(temp_gz, "wb", compresslevel=3) as compressed:
            shutil.copyfileobj(origin, compressed, 1024 * 1024)
        os.replace(temp_gz, archive)
        return archive
    finally:
        if temp_db is not None:
            temp_db.unlink(missing_ok=True)
        temp_gz.unlink(missing_ok=True)


def restore_to_new_file(archive: Path, destination: Path) -> Path:
    """Recovery always creates a new file: no silent overwriting of live data."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with (
            destination.open("xb") as recovered,
            gzip.open(archive, "rb") as packed,
        ):
            shutil.copyfileobj(packed, recovered, 1024 * 1024)
    except FileExistsError:
        raise
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    try:
        with closing(sqlite3.connect(f"file:{destination.as_posix()}?mode=ro", uri=True)) as con:
            status = con.execute("PRAGMA quick_check").fetchone()[0]
            if status != "ok":
                raise RuntimeError(f"Restored database failed integrity check: {status}")
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    return destination


def prune_backups(folder: Path, now: datetime | None = None) -> int:
    """Keep the 48 most recent hourly copies and one per day over the past month."""
    files = sorted(folder.glob("air_observatory-*.db.gz"), reverse=True)
    cutoff = (now or datetime.now(UTC)) - timedelta(days=30)
    days_kept: set[str] = set()
    keep: set[Path] = set(files[:48])
    for file in files:
        stamp = file.name.removeprefix("air_observatory-").removesuffix(".db.gz")
        try:
            time = datetime.strptime(stamp, "%Y%m%dT%H%M%S%fZ").replace(tzinfo=UTC)
        except ValueError:
            continue
        day = stamp[:8]
        if time >= cutoff and day not in days_kept:
            keep.add(file)
            days_kept.add(day)
    removed = 0
    for file in files:
        if file not in keep:
            file.unlink()
            removed += 1
    return removed


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Online SQLite backup and safe restoration")
    parser.add_argument("--backup-dir", type=Path, default=None)
    parser.add_argument("--restore", type=Path, default=None, help="Existing .db.gz archive")
    parser.add_argument("--restore-to", type=Path, default=None, help="New target database path")
    args = parser.parse_args()
    if (args.restore is None) != (args.restore_to is None):
        parser.error("--restore and --restore-to are required together")
    if args.restore:
        print(f"Restored, integrity checked: {restore_to_new_file(args.restore, args.restore_to)}")
    else:
        path = backup_database(destination=args.backup_dir)
        print(f"Verified SQLite archive: {path}")
        print(f"Expired backup files: {prune_backups(path.parent)}")


if __name__ == "__main__":
    main()
