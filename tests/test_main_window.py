"""Main window: navigation, theme, background collection and shutdown."""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QLabel  # noqa: E402

from pcinsight.config import AppPaths, Settings  # noqa: E402
from pcinsight.context import AppContext  # noqa: E402
from pcinsight.models import Capabilities, CollectorResult, CollectorStatus, MetricSample  # noqa: E402
from pcinsight.ui.main_window import MainWindow  # noqa: E402
from pcinsight.ui.tasks import TaskCancelled  # noqa: E402


class FakeSystemInfoService:
    def __init__(self, result: CollectorResult) -> None:
        self._result = result
        self.calls = 0

    def collect(self) -> CollectorResult:
        self.calls += 1
        return self._result


class FakeSamplerService:
    def __init__(self, result: CollectorResult) -> None:
        self._result = result
        self.calls = 0
        self._history = []

    @property
    def history(self) -> list:
        return self._history

    @property
    def latest(self):
        return self._result.data if self._result.ok else None

    class _FakeSampler:
        def __init__(self, outer):
            self.outer = outer

        def sample(self) -> CollectorResult:
            self.outer.calls += 1
            return self.outer._result

    @property
    def _sampler(self):
        return self._FakeSampler(self)


class _BrokenService:
    """A service that raises, which a real collector never does."""

    def collect(self) -> CollectorResult:
        raise RuntimeError("boom")


class BlockingSamplerService:
    """Blocks inside the worker thread until the test releases it."""

    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()
        self.calls = 0

    @property
    def history(self) -> list:
        return []

    @property
    def latest(self):
        return None

    class _FakeSampler:
        def __init__(self, outer):
            self.outer = outer

        def sample(self) -> CollectorResult:
            self.outer.calls += 1
            self.outer.started.set()
            self.outer.release.wait(5)
            return CollectorResult.success(
                "metrics", data=_sample(), duration_ms=1
            )

    @property
    def _sampler(self):
        return self._FakeSampler(self)


def _sample() -> MetricSample:
    return MetricSample(
        timestamp=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
        cpu_percent=7.5,
        memory_percent=33.0,
        memory_used_bytes=1024,
    )


def _context(
    tmp_path: Path,
    *,
    system_info: CollectorResult | None = None,
    sampler_service: object | None = None,
    limitations: list[str] | None = None,
    services: dict[str, object] | None = None,
) -> AppContext:
    paths = AppPaths(
        data_dir=tmp_path,
        database=tmp_path / "pcinsight.db",
        logs_dir=tmp_path / "logs",
        log_file=tmp_path / "logs" / "pcinsight.log",
        cache_dir=tmp_path / "cache",
    )
    context = AppContext(
        paths=paths,
        settings=Settings(),
        capabilities=Capabilities(
            platform="windows",
            is_administrator=False,
            os_release="Windows 11",
            limitations=limitations or [],
        ),
        connection=sqlite3.connect(":memory:"),
    )
    if system_info is not None:
        context.services["system_info"] = FakeSystemInfoService(system_info)
    if sampler_service is not None:
        context.services["sampler_service"] = sampler_service
    if services:
        context.services.update(services)
    return context


def _ok_info(**overrides: object) -> CollectorResult:
    from pcinsight.models import DiskInfo, SystemInfo

    values: dict[str, object] = {
        "os_name": "Windows",
        "os_version": "11",
        "cpu_name": "Test CPU",
        "cpu_logical_cores": 8,
        "cpu_physical_cores": 4,
        "cpu_base_mhz": 3000.0,
        "ram_total_bytes": 16 * 1024**3,
        "motherboard": "Test Board",
        "bios_vendor": "Test BIOS",
        "bios_version": "1.0",
        "gpus": [],
        "disks": [DiskInfo("C:", "System", "NTFS", 100, 40, 60)],
        "limitations": [],
    }
    values.update(overrides)
    return CollectorResult.success("system_info", data=SystemInfo(**values), duration_ms=6000)  # type: ignore[arg-type]


def _drain(qt_app) -> None:
    for _ in range(20):
        qt_app.processEvents()


def test_window_shows_shell_and_navigation(qt_app, tmp_path: Path) -> None:
    window = MainWindow(_context(tmp_path))
    window.show()
    _drain(qt_app)

    assert window.windowTitle().startswith("PC Insight")
    assert window.isVisible()
    assert window._overview_button.text() == "Overview"
    assert window._overview_button.isChecked()
    window.close()


def test_window_shows_the_limited_mode_notice(qt_app, tmp_path: Path) -> None:
    window = MainWindow(_context(tmp_path, limitations=["Limited mode"]))
    window.show()
    _drain(qt_app)

    assert window._notice.isVisibleTo(window)
    assert "Limited mode" in window._notice.text()
    window.close()


def test_window_hides_the_notice_without_limitations(qt_app, tmp_path: Path) -> None:
    window = MainWindow(_context(tmp_path))
    window.show()
    _drain(qt_app)

    assert not window._notice.isVisibleTo(window)
    window.close()


def test_refresh_runs_both_services_and_renders_the_result(qt_app, tmp_path: Path) -> None:
    sampler = FakeSamplerService(CollectorResult.success("metrics", data=_sample(), duration_ms=40))
    window = MainWindow(_context(tmp_path, system_info=_ok_info(), sampler_service=sampler))
    window.show()
    _drain(qt_app)

    window.refresh()
    assert window._refresh_button.isEnabled() is False
    assert window.task_runner.wait_for_done(5000)
    _drain(qt_app)

    assert sampler.calls == 1
    assert "Updated in" in window._status.text()
    labels = [label.text() for label in window.findChildren(QLabel)]
    assert any("Test CPU" in text for text in labels)
    window.close()


def test_refresh_reports_a_degraded_collection(qt_app, tmp_path: Path) -> None:
    info = CollectorResult.partial("system_info", data=None, message="GPU unavailable")
    sampler = FakeSamplerService(CollectorResult.success("metrics", data=_sample()))
    window = MainWindow(_context(tmp_path, system_info=info, sampler_service=sampler))
    window.show()
    _drain(qt_app)

    window.refresh()
    window.task_runner.wait_for_done(5000)
    _drain(qt_app)

    assert "limitations" in window._status.text()
    assert "GPU unavailable" in window._status.text()
    window.close()


def test_refresh_reports_a_worker_failure(qt_app, tmp_path: Path) -> None:
    sampler = FakeSamplerService(CollectorResult.success("metrics", data=_sample()))
    window = MainWindow(
        _context(
            tmp_path,
            services={
                "system_info": _BrokenService(),
                "sampler_service": sampler,
            },
        )
    )
    window.show()
    _drain(qt_app)

    window.refresh()
    window.task_runner.wait_for_done(5000)
    _drain(qt_app)

    assert "limitations" in window._status.text()
    assert "system_info: boom" in window._status.text()
    assert window._refresh_button.isEnabled()
    window.close()


def test_one_failing_service_does_not_hide_the_other(qt_app, tmp_path: Path) -> None:
    window = MainWindow(
        _context(
            tmp_path,
            services={
                "system_info": _BrokenService(),
                "sampler_service": FakeSamplerService(
                    CollectorResult.success("metrics", data=_sample(), duration_ms=5)
                ),
            },
        )
    )
    window.show()
    _drain(qt_app)

    results = window._collect()

    assert results["system_info"].status is CollectorStatus.FAILED
    assert results["system_info"].message == "boom"
    assert results["metrics"].status is CollectorStatus.OK
    window.close()


def test_refresh_without_services_reports_unavailable(qt_app, tmp_path: Path) -> None:
    window = MainWindow(_context(tmp_path))
    window.show()
    _drain(qt_app)

    window.refresh()

    assert "unavailable" in window._status.text()
    window.close()


def test_stale_result_is_ignored(qt_app, tmp_path: Path) -> None:
    sampler = FakeSamplerService(CollectorResult.success("metrics", data=_sample()))
    window = MainWindow(_context(tmp_path, system_info=_ok_info(), sampler_service=sampler))
    window.show()
    _drain(qt_app)

    window._generation = 5
    window._on_collected(
        1,
        {"system_info": _ok_info(), "metrics": CollectorResult.success("metrics", data=_sample())},
        None,
    )

    assert window._status.text() == "Ready"
    window.close()


def test_result_after_close_is_ignored(qt_app, tmp_path: Path) -> None:
    sampler = FakeSamplerService(CollectorResult.success("metrics", data=_sample()))
    window = MainWindow(_context(tmp_path, system_info=_ok_info(), sampler_service=sampler))
    window.show()
    _drain(qt_app)

    window.close()
    window._on_collected(
        window._generation,
        {"system_info": _ok_info(), "metrics": CollectorResult.success("metrics", data=_sample())},
        None,
    )

    # Window should be hidden, not closed
    assert not window.isVisible()


def test_close_cancels_running_work(qt_app, tmp_path: Path) -> None:
    blocker = BlockingSamplerService()
    window = MainWindow(_context(tmp_path, system_info=_ok_info(), sampler_service=blocker))
    window.show()
    _drain(qt_app)

    window.refresh()
    assert blocker.started.wait(5)

    blocker.release.set()
    window.close()

    # Window should be hidden, not closed (app keeps running for floating panel)
    assert not window.isVisible()


def test_close_is_safe_without_any_work(qt_app, tmp_path: Path) -> None:
    window = MainWindow(_context(tmp_path))
    window.show()

    window.close()

    # Window should be hidden, not closed (app keeps running for floating panel)
    assert not window.isVisible()


def test_theme_switch_applies_and_reports_the_resolved_theme(qt_app, tmp_path: Path) -> None:
    window = MainWindow(_context(tmp_path))
    window.show()

    assert window.apply_theme("dark") == "dark"
    assert window.styleSheet() != ""
    assert window.apply_theme("neon") == "light"
    window.close()


def test_theme_cycles_through_the_configured_choices(qt_app, tmp_path: Path) -> None:
    window = MainWindow(_context(tmp_path))
    window.show()

    window.apply_theme("light")
    window._cycle_theme()

    assert window._theme_name == "dark"
    window.close()


def test_cancelled_task_is_reported(qt_app, tmp_path: Path) -> None:
    window = MainWindow(_context(tmp_path))
    window.show()

    window._on_collected(window._generation, None, TaskCancelled("cancelled"))

    assert "Refresh failed" in window._status.text()
    assert window._refresh_button.isEnabled()
    window.close()


def test_status_text_never_claims_success_for_a_missing_result(qt_app, tmp_path: Path) -> None:
    window = MainWindow(_context(tmp_path))

    text = window._status_text(None, None)

    assert "failed" in text
    assert CollectorStatus.OK.value not in text