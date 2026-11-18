"""All SQL used by PC Insight lives in this module.

Keeping every query here means the schema can evolve in one place and no other
layer ever builds SQL by hand.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

from ..config import Settings
from ..errors import StorageError
from ..models import MetricSample

_COERCERS = {
    "theme": str,
    "sampling_interval_s": float,
    "history_retention_days": int,
    "scan_time_budget_s": int,
    "scan_max_depth": int,
    "export_dir": str,
}


def get_meta(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    """Read a value from the ``meta`` table."""
    try:
        row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    except sqlite3.Error as exc:
        raise StorageError(f"cannot read meta {key!r}: {exc}") from exc
    return default if row is None else str(row["value"])


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    """Insert or update a value in the ``meta`` table."""
    try:
        conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        conn.commit()
    except sqlite3.Error as exc:
        raise StorageError(f"cannot write meta {key!r}: {exc}") from exc


def get_settings(conn: sqlite3.Connection) -> Settings:
    """Read settings, falling back to defaults for missing or invalid values.

    Adding a field to :class:`Settings` requires adding it to ``_COERCERS`` and
    to :func:`save_settings`.
    """
    try:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    except sqlite3.Error as exc:
        raise StorageError(f"cannot read settings: {exc}") from exc

    values: dict[str, object] = {}
    for row in rows:
        key = str(row["key"])
        coercer = _COERCERS.get(key)
        if coercer is None:
            continue
        try:
            values[key] = coercer(str(row["value"]))
        except (TypeError, ValueError):
            continue
    return Settings(**values)


def save_settings(conn: sqlite3.Connection, settings: Settings) -> None:
    """Persist every settings field."""
    payload = {
        "theme": settings.theme,
        "sampling_interval_s": str(settings.sampling_interval_s),
        "history_retention_days": str(settings.history_retention_days),
        "scan_time_budget_s": str(settings.scan_time_budget_s),
        "scan_max_depth": str(settings.scan_max_depth),
        "export_dir": settings.export_dir,
    }
    try:
        conn.executemany(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            list(payload.items()),
        )
        conn.commit()
    except sqlite3.Error as exc:
        raise StorageError(f"cannot save settings: {exc}") from exc


def reset_settings(conn: sqlite3.Connection) -> None:
    """Delete every stored setting so the defaults apply again."""
    try:
        conn.execute("DELETE FROM settings")
        conn.commit()
    except sqlite3.Error as exc:
        raise StorageError(f"cannot reset settings: {exc}") from exc


_SNAPSHOT_COLUMNS = (
    "ts, cpu_percent, memory_percent, memory_used, disk_read, disk_write, "
    "net_recv, net_sent, top_process, top_proc_percent"
)
_SNAPSHOT_SELECT = f"SELECT {_SNAPSHOT_COLUMNS} FROM snapshots"


def _to_epoch_seconds(value: datetime) -> int:
    """Return a datetime as whole Unix seconds; naive values are treated as UTC."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return int(value.timestamp())


def _from_epoch_seconds(value: object) -> datetime:
    return datetime.fromtimestamp(int(value), tz=UTC)


def _row_to_sample(row: sqlite3.Row) -> MetricSample:
    return MetricSample(
        timestamp=_from_epoch_seconds(row["ts"]),
        cpu_percent=float(row["cpu_percent"]),
        memory_percent=float(row["memory_percent"]),
        memory_used_bytes=int(row["memory_used"]),
        disk_read_bytes=int(row["disk_read"] or 0),
        disk_write_bytes=int(row["disk_write"] or 0),
        net_recv_bytes=int(row["net_recv"] or 0),
        net_sent_bytes=int(row["net_sent"] or 0),
        top_process=row["top_process"] or "",
        top_process_percent=float(row["top_proc_percent"] or 0.0),
    )


def save_snapshot(conn: sqlite3.Connection, sample: MetricSample) -> int:
    """Insert one metric sample and return its row id."""
    try:
        cursor = conn.execute(
            f"INSERT INTO snapshots ({_SNAPSHOT_COLUMNS}) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                _to_epoch_seconds(sample.timestamp),
                float(sample.cpu_percent),
                float(sample.memory_percent),
                int(sample.memory_used_bytes),
                int(sample.disk_read_bytes),
                int(sample.disk_write_bytes),
                int(sample.net_recv_bytes),
                int(sample.net_sent_bytes),
                sample.top_process,
                float(sample.top_process_percent),
            ),
        )
        conn.commit()
    except sqlite3.Error as exc:
        raise StorageError(f"cannot save metric sample: {exc}") from exc
    return int(cursor.lastrowid or 0)


def get_snapshots(
    conn: sqlite3.Connection,
    limit: int = 100,
    since: datetime | None = None,
) -> list[MetricSample]:
    """Return the newest ``limit`` samples in chronological order.

    ``since`` restricts the result to samples at or after that moment, and the
    limit still selects the newest samples inside that window.
    """
    limit = max(0, int(limit))
    if since is None:
        sql = f"{_SNAPSHOT_SELECT} ORDER BY ts DESC, id DESC LIMIT ?"
        params: tuple[object, ...] = (limit,)
    else:
        sql = f"{_SNAPSHOT_SELECT} WHERE ts >= ? ORDER BY ts DESC, id DESC LIMIT ?"
        params = (_to_epoch_seconds(since), limit)
    try:
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error as exc:
        raise StorageError(f"cannot read metric samples: {exc}") from exc
    return [_row_to_sample(row) for row in reversed(rows)]


def prune_snapshots(conn: sqlite3.Connection, retention_days: int) -> int:
    """Delete samples older than ``retention_days`` and return the deleted count.

    A retention of zero or less disables pruning and keeps the whole history.
    """
    if retention_days <= 0:
        return 0
    cutoff = _to_epoch_seconds(datetime.now(UTC) - timedelta(days=retention_days))
    try:
        cursor = conn.execute("DELETE FROM snapshots WHERE ts < ?", (cutoff,))
        conn.commit()
    except sqlite3.Error as exc:
        raise StorageError(f"cannot prune metric samples: {exc}") from exc
    return int(cursor.rowcount or 0)


def count_snapshots(conn: sqlite3.Connection) -> int:
    """Return how many metric samples are stored."""
    try:
        row = conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()
    except sqlite3.Error as exc:
        raise StorageError(f"cannot count metric samples: {exc}") from exc
    return int(row[0])