"""Collector wrapper around Platform.metric_sample()."""

from __future__ import annotations

from datetime import UTC, datetime

from pcinsight.collectors import metrics
from pcinsight.errors import PlatformError
from pcinsight.models import CollectorStatus, MetricSample


def _sample() -> MetricSample:
    return MetricSample(
        timestamp=datetime.now(UTC),
        cpu_percent=12.5,
        memory_percent=40.0,
        memory_used_bytes=4096,
    )


class FakePlatform:
    name = "windows"

    def __init__(
        self,
        *,
        sample: MetricSample | None = None,
        error: Exception | None = None,
    ) -> None:
        self._sample = sample
        self._error = error

    def metric_sample(self) -> MetricSample:
        if self._error is not None:
            raise self._error
        if self._sample is None:
            raise PlatformError("no metric sample configured")
        return self._sample


def test_metrics_collector_success() -> None:
    sample = _sample()

    result = metrics.collect(FakePlatform(sample=sample))

    assert result.name == "metrics"
    assert result.status is CollectorStatus.OK
    assert result.data is sample
    assert result.message == ""
    assert result.duration_ms >= 0


def test_metrics_collector_failed() -> None:
    result = metrics.collect(FakePlatform(error=PlatformError("query failed")))

    assert result.name == "metrics"
    assert result.status is CollectorStatus.FAILED
    assert result.message == "query failed"
    assert result.data is None


def test_metrics_collector_skipped() -> None:
    result = metrics.collect(FakePlatform(error=NotImplementedError("not supported")))

    assert result.status is CollectorStatus.SKIPPED
    assert result.message == "not supported"


def test_metrics_collector_never_raises() -> None:
    result = metrics.collect(FakePlatform(error=RuntimeError("boom")))

    assert result.status is CollectorStatus.FAILED
    assert "boom" in result.message