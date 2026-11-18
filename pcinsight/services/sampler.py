"""Live metric sampling and the local history of samples."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from ..collectors import metrics
from ..config import Settings
from ..errors import StorageError
from ..models import CollectorResult, MetricSample
from ..platform.base import Platform
from ..storage import db, repository

logger = logging.getLogger(__name__)


class MetricsSampler:
    """Collect metric samples and keep them in the local history.

    The sampler owns no timer and starts no thread: ``sample()`` collects and
    stores exactly one point, and ``prune()`` applies the retention setting when
    the caller asks for it. A later phase decides when either one runs.

    Neither method raises for an expected problem. A failure is logged and
    reported through the returned value, so a caller that samples on a schedule
    never has to wrap the call in ``try``/``except``.

    Every storage operation opens its own SQLite connection on the calling
    thread. A connection created on the main thread is never handed to a worker
    thread, which avoids SQLite's thread-safety restriction.
    """

    def __init__(
        self,
        platform: Platform,
        db_path: Path,
        settings: Settings,
    ) -> None:
        self._platform = platform
        self._db_path = db_path
        self._settings = settings

    def _connect(self) -> sqlite3.Connection:
        return db.connect(self._db_path)

    def sample(self) -> CollectorResult:
        """Collect one sample and store it.

        A storage failure never throws the sample away: the result is
        ``PARTIAL`` and still carries the sample in ``data``.
        """
        result = metrics.collect(self._platform)
        if not result.ok or not isinstance(result.data, MetricSample):
            return result

        conn = self._connect()
        try:
            try:
                repository.save_snapshot(conn, result.data)
            except StorageError as exc:
                logger.warning("metric sample was collected but not stored: %s", exc)
                message = f"{result.message}; {exc}" if result.message else str(exc)
                return CollectorResult.partial(
                    result.name,
                    data=result.data,
                    message=message,
                    duration_ms=result.duration_ms,
                )
        finally:
            conn.close()

        logger.debug(
            "metric sample stored: cpu %.1f%%, memory %.1f%%",
            result.data.cpu_percent,
            result.data.memory_percent,
        )
        return result

    def history(self, limit: int = 100, since: datetime | None = None) -> list[MetricSample]:
        """Return stored samples, oldest first."""
        conn = self._connect()
        try:
            return repository.get_snapshots(conn, limit=limit, since=since)
        finally:
            conn.close()

    def prune(self) -> int:
        """Delete samples older than the retention setting and return the count.

        A storage failure is logged and reported as ``0``: the history that is
        already on disk is still valid, so a failed retention pass must not
        interrupt the caller.
        """
        conn = self._connect()
        try:
            try:
                removed = repository.prune_snapshots(
                    conn, self._settings.history_retention_days
                )
            except StorageError as exc:
                logger.warning("cannot prune metric samples: %s", exc)
                return 0
            if removed:
                logger.info("pruned %d metric samples outside the retention window", removed)
            return removed
        finally:
            conn.close()