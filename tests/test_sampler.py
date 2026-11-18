"""MetricsSampler: collection, persistence, history and retention."""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from pcinsight.config import Settings
from pcinsight.errors import PlatformError, StorageError
from pcinsight.models import CollectorResult, CollectorStatus, MetricSample
from pcinsight.services import sampler as sampler_module
from pcinsight.services.sampler import MetricsSampler
from pcinsight.storage import db, repository


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "pcinsight.db"
    connection = db.connect(path)
    db.migrate(connection)
    connection.close()
    return path


def _count(db_path: Path) -> int:
    conn = db.connect(db_path)
    try:
        return repository.count_snapshots(conn)
    finally:
        conn.close()


def _ago(**delta: float) -> datetime:
    return (datetime.now(UTC) - timedelta(**delta)).replace(microsecond=0)


class FakePlatform:
    name = "windows"

    def __init__(self, *, error: Exception | None = None) -> None:
        self._error = error
        self.calls = 0

    def metric_sample(self) -> MetricSample:
        self.calls += 1
        if self._error is not None:
            raise self._error
        return MetricSample(
            timestamp=datetime.now(UTC).replace(microsecond=0),
            cpu_percent=4.0,
            memory_percent=20.0,
            memory_used_bytes=1024,
            disk_read_bytes=10,
            disk_write_bytes=20,
            net_recv_bytes=30,
            net_sent_bytes=40,
            top_process="pcinsight.exe",
            top_process_percent=1.5,
        )


def _store(db_path: Path, timestamp: datetime) -> int:
    sample = MetricSample(
        timestamp=timestamp,
        cpu_percent=1.0,
        memory_percent=2.0,
        memory_used_bytes=3,
    )
    conn = db.connect(db_path)
    try:
        return repository.save_snapshot(conn, sample)
    finally:
        conn.close()


def test_sample_collects_and_stores_one_snapshot(db_path: Path) -> None:
    sampler = MetricsSampler(FakePlatform(), db_path, Settings())

    result = sampler.sample()

    assert result.status is CollectorStatus.OK
    assert _count(db_path) == 1
    history = sampler.history()
    assert len(history) == 1
    assert history[0].cpu_percent == 4.0
    assert history[0].memory_used_bytes == 1024
    assert history[0].top_process == "pcinsight.exe"


def test_sample_returns_failed_and_stores_nothing(db_path: Path) -> None:
    sampler = MetricsSampler(FakePlatform(error=PlatformError("denied")), db_path, Settings())

    result = sampler.sample()

    assert result.status is CollectorStatus.FAILED
    assert result.message == "denied"
    assert _count(db_path) == 0


def test_sample_stores_nothing_when_the_platform_is_unsupported(
    db_path: Path,
) -> None:
    sampler = MetricsSampler(
        FakePlatform(error=NotImplementedError("not supported")), db_path, Settings()
    )

    result = sampler.sample()

    assert result.status is CollectorStatus.SKIPPED
    assert result.message == "not supported"
    assert _count(db_path) == 0


def test_sample_stores_nothing_when_the_sample_is_partial(
    db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    partial = CollectorResult.partial(
        "metrics", data=MetricSample(datetime.now(UTC), 1.0, 2.0, 3), message="slow"
    )
    monkeypatch.setattr(sampler_module.metrics, "collect", lambda _platform: partial)
    sampler = MetricsSampler(FakePlatform(), db_path, Settings())

    result = sampler.sample()

    assert result is partial
    assert result.data is not None
    assert _count(db_path) == 0


def test_sample_stores_nothing_when_the_result_carries_no_sample(
    db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        sampler_module.metrics,
        "collect",
        lambda _platform: CollectorResult.success("metrics", data="nope"),
    )
    sampler = MetricsSampler(FakePlatform(), db_path, Settings())

    result = sampler.sample()

    assert result.status is CollectorStatus.OK
    assert _count(db_path) == 0


def test_sample_keeps_the_sample_when_storage_fails(
    db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(*_args: object, **_kwargs: object) -> int:
        raise StorageError("disk full")

    monkeypatch.setattr(repository, "save_snapshot", _boom)
    sampler = MetricsSampler(FakePlatform(), db_path, Settings())

    result = sampler.sample()

    assert result.status is CollectorStatus.PARTIAL
    assert isinstance(result.data, MetricSample)
    assert result.data.cpu_percent == 4.0
    assert "disk full" in result.message


def test_history_returns_samples_oldest_first(db_path: Path) -> None:
    first = _ago(hours=2)
    second = _ago(hours=1)
    third = _ago(minutes=1)
    for timestamp in (third, first, second):
        _store(db_path, timestamp)

    history = MetricsSampler(FakePlatform(), db_path, Settings()).history()

    assert [sample.timestamp for sample in history] == [first, second, third]


def test_history_applies_the_limit_to_the_newest_samples(db_path: Path) -> None:
    first = _ago(hours=2)
    second = _ago(hours=1)
    third = _ago(minutes=1)
    for timestamp in (first, second, third):
        _store(db_path, timestamp)

    history = MetricsSampler(FakePlatform(), db_path, Settings()).history(limit=2)

    assert [sample.timestamp for sample in history] == [second, third]


def test_history_limit_zero_returns_nothing(db_path: Path) -> None:
    _store(db_path, _ago(minutes=1))

    assert MetricsSampler(FakePlatform(), db_path, Settings()).history(limit=0) == []


def test_history_since_returns_only_newer_samples(db_path: Path) -> None:
    first = _ago(hours=2)
    second = _ago(hours=1)
    third = _ago(minutes=1)
    for timestamp in (first, second, third):
        _store(db_path, timestamp)

    history = MetricsSampler(FakePlatform(), db_path, Settings()).history(since=second)

    assert [sample.timestamp for sample in history] == [second, third]


def test_prune_deletes_samples_outside_the_retention_window(db_path: Path) -> None:
    old = _ago(days=40)
    recent = _ago(days=1)
    for timestamp in (old, recent):
        _store(db_path, timestamp)
    sampler = MetricsSampler(FakePlatform(), db_path, Settings(history_retention_days=30))

    removed = sampler.prune()

    assert removed == 1
    assert [sample.timestamp for sample in sampler.history()] == [recent]


def test_prune_is_disabled_for_non_positive_retention(db_path: Path) -> None:
    _store(db_path, _ago(days=400))
    sampler = MetricsSampler(FakePlatform(), db_path, Settings(history_retention_days=0))

    assert sampler.prune() == 0
    assert _count(db_path) == 1


def test_prune_never_raises_when_storage_fails(
    db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(*_args: object, **_kwargs: object) -> int:
        raise StorageError("database is locked")

    monkeypatch.setattr(repository, "prune_snapshots", _boom)
    sampler = MetricsSampler(FakePlatform(), db_path, Settings())

    assert sampler.prune() == 0


def test_prune_keeps_the_history_when_it_fails(
    db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recent = _ago(days=1)
    _store(db_path, recent)

    def _boom(*_args: object, **_kwargs: object) -> int:
        raise StorageError("database is locked")

    monkeypatch.setattr(repository, "prune_snapshots", _boom)
    sampler = MetricsSampler(FakePlatform(), db_path, Settings())

    assert sampler.prune() == 0
    assert [sample.timestamp for sample in sampler.history()] == [recent]


def test_sampler_reuses_the_settings_it_was_built_with(
    db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[int] = []

    def _prune(_conn: sqlite3.Connection, retention_days: int) -> int:
        seen.append(retention_days)
        return 0

    monkeypatch.setattr(repository, "prune_snapshots", _prune)
    sampler = MetricsSampler(
        FakePlatform(), db_path, Settings(history_retention_days=7)
    )

    sampler.prune()

    assert seen == [7]


def test_sample_stores_snapshot_from_worker_thread(db_path: Path) -> None:
    """Real scenario: sample() called on a worker thread, snapshot saved to a file database."""
    platform = FakePlatform()
    sampler = MetricsSampler(platform, db_path, Settings())

    error_holder: list[Exception] = []
    result_holder: list[CollectorResult] = []

    def _run_on_worker() -> None:
        try:
            result_holder.append(sampler.sample())
        except Exception as exc:  # pragma: no cover - defensive
            error_holder.append(exc)

    thread = threading.Thread(target=_run_on_worker)
    thread.start()
    thread.join(10)

    assert not error_holder, f"worker thread raised: {error_holder}"
    assert len(result_holder) == 1
    assert result_holder[0].status is CollectorStatus.OK
    assert _count(db_path) == 1

    history = sampler.history()
    assert len(history) == 1
    assert history[0].cpu_percent == 4.0
