"""Shared periodic metric sampling service.

P5 adds a single, application-wide sampling stream that both the Performance
page and the floating desktop panel consume. One ``QTimer`` drives the cadence;
every tick submits :meth:`MetricsSampler.sample` to the shared ``TaskRunner``
so sampling never blocks the GUI thread. Results are marshalled back to the GUI
thread and broadcast through a signal so every subscriber sees the same sample.
"""

from __future__ import annotations

import logging
from collections import deque
from datetime import UTC, datetime, timedelta

from PySide6.QtCore import QObject, QTimer, Signal

from ..config import Settings
from ..models import CollectorResult, MetricSample
from ..platform.base import Platform
from ..services.sampler import MetricsSampler
from ..storage import db, repository
from ..ui.tasks import TaskRunner

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_S = 5.0
MAX_HISTORY_SAMPLES = 17280  # 24 hours at 5-second cadence (24 * 60 * 60 / 5)


class SamplerService(QObject):
    """Own one periodic sampling stream shared by every consumer.

    ``sampled`` is emitted on the GUI thread with each successfully stored
    ``MetricSample``. Consumers (pages, floating panel) connect to it and draw
    from ``latest`` / ``history`` without starting any timer of their own.
    """

    sampled = Signal(object)

    def __init__(
        self,
        platform: Platform,
        db_path,
        settings: Settings,
        task_runner: TaskRunner | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._sampler = MetricsSampler(platform, db_path, settings)
        self._db_path = db_path
        self._task_runner = task_runner
        self._interval_ms = max(1000, int(float(settings.sampling_interval_s) * 1000))
        self._retention_days = max(0, int(settings.history_retention_days))

        self._timer = QTimer(self)
        self._timer.setInterval(self._interval_ms)
        self._timer.timeout.connect(self._tick)

        self._latest: MetricSample | None = None
        self._history: deque[MetricSample] = deque()
        self._running = False
        self._sampling = False

    def set_task_runner(self, task_runner: TaskRunner) -> None:
        """Set the task runner after construction (e.g., from MainWindow)."""
        self._task_runner = task_runner

    # ------------------------------------------------------------------ control

    @property
    def running(self) -> bool:
        return self._running

    @property
    def latest(self) -> MetricSample | None:
        return self._latest

    @property
    def history(self) -> list[MetricSample]:
        return list(self._history)

    def start(self) -> None:
        """Begin periodic sampling. Safe to call more than once."""
        if self._running:
            return
        self._running = True
        self._sampling = False
        self._timer.start()
        logger.info("sampler service started (interval %d ms)", self._interval_ms)

    def stop(self) -> None:
        """Stop periodic sampling. Any in-flight sample finishes on its own."""
        self._running = False
        self._timer.stop()
        logger.info("sampler service stopped")

    def sample_once(self, on_done) -> None:
        """Collect a single sample on demand (for manual refresh).

        Runs on the shared TaskRunner so it never blocks the GUI thread.
        ``on_done`` is called with (CollectorResult, Exception | None) on the GUI thread.
        """
        if self._task_runner is None:
            # No task runner available; call on_done with a failed result
            from ..models import CollectorResult
            on_done(CollectorResult.failed("metrics", "sampler service not ready"), None)
            return
        if self._sampling:
            # A periodic sample is in flight; avoid stacking requests
            from ..models import CollectorResult
            on_done(CollectorResult.failed("metrics", "sampling in progress"), None)
            return
        self._sampling = True
        self._task_runner.submit(
            self._sampler.sample,
            with_token=False,
            on_done=lambda result, error: self._on_manual_sampled(result, error, on_done),
        )

    def _on_manual_sampled(self, result: CollectorResult, error: Exception | None, on_done) -> None:
        """Handle completion of a manual sample request."""
        self._sampling = False
        if error is not None or not isinstance(result, CollectorResult):
            logger.warning("manual sample failed: %s", error)
            if isinstance(result, CollectorResult):
                on_done(result, error)
            else:
                on_done(CollectorResult.failed("metrics", str(error)), error)
            return

        if not result.ok or not isinstance(result.data, MetricSample):
            logger.debug("manual sample not stored: %s", result.status)
            on_done(result, None)
            return

        sample = result.data
        self._latest = sample
        self._history.append(sample)
        self._prune()
        self.sampled.emit(sample)
        logger.debug(
            "manual sample stored: cpu %.1f%%, memory %.1f%%",
            sample.cpu_percent,
            sample.memory_percent,
        )
        on_done(result, None)

    # ---------------------------------------------------------------- sampling

    def _tick(self) -> None:
        if not self._running or self._sampling or self._task_runner is None:
            return
        self._sampling = True
        self._task_runner.submit(
            self._sampler.sample,
            with_token=False,
            on_done=self._on_sampled,
        )

    def _on_sampled(self, result: CollectorResult, error: Exception | None) -> None:
        """Run on the GUI thread when a background sample finishes."""
        self._sampling = False
        if error is not None or not isinstance(result, CollectorResult):
            logger.warning("periodic sample failed: %s", error)
            self._prune()
            return

        if not result.ok or not isinstance(result.data, MetricSample):
            logger.debug("periodic sample not stored: %s", result.status)
            self._prune()
            return

        sample = result.data
        self._latest = sample
        self._history.append(sample)
        self._prune()
        self.sampled.emit(sample)
        logger.debug(
            "periodic sample stored: cpu %.1f%%, memory %.1f%%",
            sample.cpu_percent,
            sample.memory_percent,
        )

    # ---------------------------------------------------------------- retention

    def _prune(self) -> None:
        if not self._history:
            return
        if self._retention_days > 0:
            cutoff = datetime.now(UTC) - timedelta(days=self._retention_days)
            while self._history and self._history[0].timestamp < cutoff:
                self._history.popleft()
        # Cap in-memory history regardless of retention setting.
        while len(self._history) > MAX_HISTORY_SAMPLES:
            self._history.popleft()
        self._prune_db()

    def _prune_db(self) -> None:
        conn = db.connect(self._db_path)
        try:
            repository.prune_snapshots(conn, self._retention_days)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("periodic prune failed: %s", exc)
        finally:
            conn.close()
