"""SQLite connection and schema migration."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from ..errors import StorageError

SCHEMA_VERSION = 1
SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def connect(path: Path) -> sqlite3.Connection:
    """Open the local database and apply the standard pragmas."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, timeout=10.0)
    except (sqlite3.Error, OSError) as exc:
        raise StorageError(f"cannot open database at {path}: {exc}") from exc

    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def schema_version(conn: sqlite3.Connection) -> int:
    """Return the schema version currently applied to the database."""
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def _migrate_v1(conn: sqlite3.Connection) -> None:
    """Create the baseline schema."""
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(sql)
    conn.execute("PRAGMA user_version = 1")


_MIGRATIONS = {
    1: _migrate_v1,
}


def migrate(conn: sqlite3.Connection) -> int:
    """Apply every migration step between the current and target schema.

    Each step sets ``PRAGMA user_version`` itself, so an interrupted upgrade is
    retried rather than stamped as complete.
    """
    current = schema_version(conn)
    if current > SCHEMA_VERSION:
        raise StorageError(
            f"database schema {current} is newer than the supported version {SCHEMA_VERSION}"
        )

    for version in range(current + 1, SCHEMA_VERSION + 1):
        step = _MIGRATIONS.get(version)
        if step is None:
            raise StorageError(f"no migration step is defined for schema version {version}")
        try:
            step(conn)
            conn.commit()
        except (OSError, sqlite3.Error) as exc:
            conn.rollback()
            raise StorageError(
                f"database migration to version {version} failed: {exc}"
            ) from exc

    return schema_version(conn)