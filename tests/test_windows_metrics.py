"""Windows metric sampling and the optional-counter fallbacks."""

from __future__ import annotations

import sys

import pytest

from pcinsight.errors import PlatformError
from pcinsight.platform import _windows_metrics as wm

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows-only adapter")


def _unavailable(*_args: object, **_kwargs: object) -> None:
    raise OSError("counters unavailable")


def test_collect_metric_sample_reports_real_counters() -> None:
    sample = wm.collect_metric_sample()

    assert 0.0 <= sample.cpu_percent <= 100.0
    assert 0.0 <= sample.memory_percent <= 100.0
    assert sample.memory_used_bytes > 0
    assert sample.disk_read_bytes >= 0
    assert sample.disk_write_bytes >= 0
    assert sample.net_recv_bytes >= 0
    assert sample.net_sent_bytes >= 0
    assert sample.top_process_percent >= 0.0
    assert sample.timestamp.tzinfo is not None


def test_collect_metric_sample_degrades_optional_counters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(wm.psutil, "disk_io_counters", _unavailable)
    monkeypatch.setattr(wm.psutil, "net_io_counters", _unavailable)

    sample = wm.collect_metric_sample()

    assert sample.disk_read_bytes == 0
    assert sample.disk_write_bytes == 0
    assert sample.net_recv_bytes == 0
    assert sample.net_sent_bytes == 0
    assert sample.cpu_percent >= 0.0


def test_collect_metric_sample_requires_cpu_and_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(wm.psutil, "cpu_percent", _unavailable)

    with pytest.raises(PlatformError):
        wm.collect_metric_sample()


class FakeProcess:
    def __init__(self, pid: int, name: str, percent: float) -> None:
        self.pid = pid
        self._name = name
        self._percent = percent

    def cpu_percent(self) -> float:
        return self._percent

    def name(self) -> str:
        return self._name


def test_sample_processes_skips_processes_that_vanish(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class VanishingProcess(FakeProcess):
        def cpu_percent(self) -> float:
            raise wm.psutil.NoSuchProcess(self.pid)

    doomed = VanishingProcess(1, "gone.exe", 50.0)
    alive = FakeProcess(2, "alive.exe", 3.0)
    monkeypatch.setattr(wm.psutil, "process_iter", lambda: iter([doomed, alive]))
    monkeypatch.setattr(wm, "_PROCESS_SAMPLE_DELAY_S", 0.0)

    assert wm._sample_processes() == ("alive.exe", 3.0)


def test_sample_processes_is_empty_when_no_process_survives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class VanishingProcess(FakeProcess):
        def cpu_percent(self) -> float:
            raise wm.psutil.NoSuchProcess(self.pid)

    only_idle = VanishingProcess(0, "System Idle Process", 99.0)
    monkeypatch.setattr(wm.psutil, "process_iter", lambda: iter([only_idle]))
    monkeypatch.setattr(wm, "_PROCESS_SAMPLE_DELAY_S", 0.0)

    assert wm._sample_processes() == ("", 0.0)


def test_non_negative_int_clamps_negative_counters() -> None:
    assert wm._non_negative_int(-5) == 0
    assert wm._non_negative_int(None) == 0
    assert wm._non_negative_int(7) == 7


def test_try_optional_returns_none_when_the_counter_fails() -> None:
    assert wm._try_optional(_unavailable, "broken counter") is None
    assert wm._try_optional(lambda: 5, "working counter") == 5


def test_sample_processes_skips_the_kernel_idle_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    idle = FakeProcess(0, "System Idle Process", 600.0)
    busy = FakeProcess(1234, "pcinsight.exe", 12.5)
    monkeypatch.setattr(wm.psutil, "process_iter", lambda: iter([idle, busy]))
    monkeypatch.setattr(wm, "_PROCESS_SAMPLE_DELAY_S", 0.0)

    assert wm._sample_processes() == ("pcinsight.exe", 12.5)


def test_sample_processes_reports_the_first_process_when_all_are_idle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = FakeProcess(100, "first.exe", 0.0)
    second = FakeProcess(200, "second.exe", 0.0)
    monkeypatch.setattr(wm.psutil, "process_iter", lambda: iter([first, second]))
    monkeypatch.setattr(wm, "_PROCESS_SAMPLE_DELAY_S", 0.0)

    assert wm._sample_processes() == ("first.exe", 0.0)