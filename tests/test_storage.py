"""SQLite connection, migration and repositories."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from pcinsight.config import Settings
from pcinsight.errors import StorageError
from pcinsight.models import MetricSample
from pcinsight.storage import db, repository


@pytest.fixture()
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connection = db.connect(tmp_path / "pcinsight.db")
    db.migrate(connection)
    yield connection
    connection.close()


def test_migrate_creates_schema(conn: sqlite3.Connection) -> None:
    tables = {
        row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }

    assert {
        "meta",
        "settings",
        "snapshots",
        "storage_scans",
        "storage_items",
        "diagnostic_runs",
        "findings",
    } <= tables
    assert db.schema_version(conn) == db.SCHEMA_VERSION


def test_migrate_is_idempotent(conn: sqlite3.Connection) -> None:
    assert db.migrate(conn) == db.SCHEMA_VERSION
    assert db.migrate(conn) == db.SCHEMA_VERSION


def test_every_schema_version_has_a_step() -> None:
    assert set(db._MIGRATIONS) == set(range(1, db.SCHEMA_VERSION + 1))


def test_upgrade_from_v1_preserves_data(
    conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    conn.execute("INSERT INTO meta (key, value) VALUES (?, ?)", ("keep", "me"))
    conn.commit()

    def _migrate_v2(target: sqlite3.Connection) -> None:
        target.execute("ALTER TABLE meta ADD COLUMN extra TEXT")
        target.execute("PRAGMA user_version = 2")

    monkeypatch.setattr(db, "SCHEMA_VERSION", 2)
    monkeypatch.setitem(db._MIGRATIONS, 2, _migrate_v2)

    assert db.migrate(conn) == 2
    assert conn.execute("SELECT value FROM meta WHERE key = 'keep'").fetchone()["value"] == "me"
    columns = {row[1] for row in conn.execute("PRAGMA table_info(meta)")}
    assert "extra" in columns


def test_migrate_rejects_newer_schema(tmp_path: Path) -> None:
    conn = db.connect(tmp_path / "pcinsight.db")
    conn.execute("PRAGMA user_version = 99")
    conn.commit()

    with pytest.raises(StorageError):
        db.migrate(conn)

    conn.close()


def test_meta_roundtrip(conn: sqlite3.Connection) -> None:
    assert repository.get_meta(conn, "missing", "fallback") == "fallback"

    repository.set_meta(conn, "schema_note", "p0")

    assert repository.get_meta(conn, "schema_note") == "p0"


def test_settings_roundtrip(conn: sqlite3.Connection) -> None:
    assert repository.get_settings(conn) == Settings()

    settings = Settings(theme="dark", sampling_interval_s=1.5, history_retention_days=7)
    repository.save_settings(conn, settings)

    assert repository.get_settings(conn) == settings


def test_settings_ignore_unknown_keys(conn: sqlite3.Connection) -> None:
    conn.execute("INSERT INTO settings (key, value) VALUES (?, ?)", ("future_key", "x"))
    conn.commit()

    assert repository.get_settings(conn) == Settings()


def test_reset_settings(conn: sqlite3.Connection) -> None:
    repository.save_settings(conn, Settings(theme="light"))
    repository.reset_settings(conn)

    assert repository.get_settings(conn) == Settings()


def test_connect_failure_raises(tmp_path: Path) -> None:
    with pytest.raises(StorageError):
        db.connect(tmp_path)


def _sample(timestamp: datetime, **overrides: object) -> MetricSample:
    values: dict[str, object] = {
        "timestamp": timestamp,
        "cpu_percent": 12.5,
        "memory_percent": 40.0,
        "memory_used_bytes": 1024,
        "disk_read_bytes": 10,
        "disk_write_bytes": 20,
        "net_recv_bytes": 30,
        "net_sent_bytes": 40,
        "top_process": "pcinsight.exe",
        "top_process_percent": 1.5,
    }
    values.update(overrides)
    return MetricSample(**values)


def test_snapshot_roundtrip(conn: sqlite3.Connection) -> None:
    timestamp = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)

    row_id = repository.save_snapshot(conn, _sample(timestamp))

    assert row_id > 0
    assert repository.count_snapshots(conn) == 1
    assert repository.get_snapshots(conn) == [_sample(timestamp)]


def test_snapshot_accepts_naive_timestamps_as_utc(conn: sqlite3.Connection) -> None:
    naive = datetime(2026, 1, 2, 3, 4, 5)

    repository.save_snapshot(conn, _sample(naive))

    stored = repository.get_snapshots(conn)[0]
    assert stored.timestamp == naive.replace(tzinfo=UTC)
    assert stored.timestamp.tzinfo is not None


def test_get_snapshots_orders_oldest_first_and_applies_limit(conn: sqlite3.Connection) -> None:
    first = datetime(2026, 1, 1, tzinfo=UTC)
    second = datetime(2026, 1, 2, tzinfo=UTC)
    third = datetime(2026, 1, 3, tzinfo=UTC)
    for timestamp in (third, first, second):
        repository.save_snapshot(conn, _sample(timestamp))

    assert [item.timestamp for item in repository.get_snapshots(conn)] == [first, second, third]
    assert [item.timestamp for item in repository.get_snapshots(conn, limit=2)] == [second, third]


def test_get_snapshots_since_filters_older_samples(conn: sqlite3.Connection) -> None:
    first = datetime(2026, 1, 1, tzinfo=UTC)
    second = datetime(2026, 1, 2, tzinfo=UTC)
    third = datetime(2026, 1, 3, tzinfo=UTC)
    for timestamp in (first, second, third):
        repository.save_snapshot(conn, _sample(timestamp))

    stored = repository.get_snapshots(conn, since=second)

    assert [item.timestamp for item in stored] == [second, third]


def test_prune_snapshots_deletes_expired_samples(conn: sqlite3.Connection) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    old = now - timedelta(days=40)
    recent = now - timedelta(days=1)
    repository.save_snapshot(conn, _sample(old))
    repository.save_snapshot(conn, _sample(recent))

    removed = repository.prune_snapshots(conn, 30)

    assert removed == 1
    assert [item.timestamp for item in repository.get_snapshots(conn)] == [recent]


def test_prune_snapshots_is_disabled_for_non_positive_retention(conn: sqlite3.Connection) -> None:
    repository.save_snapshot(conn, _sample(datetime.now(UTC) - timedelta(days=400)))

    assert repository.prune_snapshots(conn, 0) == 0
    assert repository.prune_snapshots(conn, -5) == 0
    assert repository.count_snapshots(conn) == 1