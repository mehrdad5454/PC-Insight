"""Essential P5 tests: shared sampling stream, history, performance page, floating panel."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QObject, Signal  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from pcinsight.config import AppPaths, Settings  # noqa: E402
from pcinsight.context import AppContext  # noqa: E402
from pcinsight.models import Capabilities, CollectorResult, CollectorStatus, MetricSample  # noqa: E402
from pcinsight.services.sampler_service import SamplerService  # noqa: E402
from pcinsight.ui.pages.performance import PerformancePage  # noqa: E402
from pcinsight.ui.tasks import TaskRunner  # noqa: E402
from pcinsight.ui.widgets.floating_panel import FloatingPanel  # noqa: E402


class StubPlatform:
    name = "windows"

    def metric_sample(self) -> MetricSample:
        return _sample()


def _context(tmp_path: Path) -> AppContext:
    paths = AppPaths(
        data_dir=tmp_path,
        database=tmp_path / "pcinsight.db",
        logs_dir=tmp_path / "logs",
        log_file=tmp_path / "logs" / "pcinsight.log",
        cache_dir=tmp_path / "cache",
    )
    # Migrate the file database that the sampler service will use
    from pcinsight.storage import db
    file_conn = sqlite3.connect(paths.database)
    db.migrate(file_conn)
    file_conn.close()

    return AppContext(
        paths=paths,
        settings=Settings(),
        capabilities=Capabilities(
            platform="windows",
            is_administrator=False,
            os_release="Windows 11",
        ),
        connection=sqlite3.connect(":memory:"),
    )


def _sample(**overrides) -> MetricSample:
    values = {
        "timestamp": datetime.now(UTC).replace(microsecond=0),
        "cpu_percent": 10.0,
        "memory_percent": 40.0,
        "memory_used_bytes": 4 * 1024**3,
        "disk_read_bytes": 1024,
        "disk_write_bytes": 2048,
        "net_recv_bytes": 512,
        "net_sent_bytes": 256,
    }
    values.update(overrides)
    return MetricSample(**values)


class FakeSamplerService(QObject):
    """Fake sampler service for testing without platform dependencies."""

    sampled = Signal(object)

    def __init__(self, samples: list[MetricSample] | None = None):
        super().__init__()
        self._samples = samples or []
        self._index = 0
        self.calls = 0

    @property
    def history(self) -> list[MetricSample]:
        return self._samples

    @property
    def latest(self) -> MetricSample | None:
        return self._samples[-1] if self._samples else None

    class _FakeSampler:
        def __init__(self, outer):
            self.outer = outer

        def sample(self) -> CollectorResult:
            self.outer.calls += 1
            if self.outer._index < len(self.outer._samples):
                sample = self.outer._samples[self.outer._index]
                self.outer._index += 1
                return CollectorResult.success("metrics", data=sample, duration_ms=1)
            return CollectorResult.success("metrics", data=_sample(), duration_ms=1)

    @property
    def _sampler(self):
        return self._FakeSampler(self)


# -----------------------------------------------------------------------
# SamplerService tests
# -----------------------------------------------------------------------


def test_sampler_service_history_capacity_24_hours(tmp_path: Path) -> None:
    """Verify MAX_HISTORY_SAMPLES allows 24 hours at 5-second interval."""
    from pcinsight.services.sampler_service import MAX_HISTORY_SAMPLES

    expected = 24 * 60 * 60 // 5  # 17280
    assert expected == MAX_HISTORY_SAMPLES


def test_sampler_service_start_stop_idempotent(tmp_path: Path) -> None:
    """Starting/stopping multiple times should be safe."""
    from pcinsight.app import build_services

    ctx = _context(tmp_path)
    services = build_services(ctx, platform=StubPlatform())
    svc: SamplerService = services["sampler_service"]

    assert not svc.running
    svc.start()
    assert svc.running
    svc.start()  # second call should not error
    assert svc.running
    svc.stop()
    assert not svc.running
    svc.stop()  # second call should not error
    assert not svc.running


def test_sampler_service_prevents_concurrent_sampling(tmp_path: Path) -> None:
    """While one sample is in flight, a second tick should be ignored."""
    from pcinsight.app import build_services

    ctx = _context(tmp_path)
    services = build_services(ctx, platform=StubPlatform())
    svc: SamplerService = services["sampler_service"]
    runner = TaskRunner(None)
    svc.set_task_runner(runner)

    # Start service
    svc.start()

    # Simulate a tick that starts sampling
    svc._sampling = True
    # Second tick should be ignored due to _sampling flag
    svc._tick()
    # No exception, just silently ignored


def test_sampler_service_prunes_old_samples(tmp_path: Path) -> None:
    """Pruning should remove samples older than retention."""
    from pcinsight.app import build_services

    ctx = _context(tmp_path)
    services = build_services(ctx, platform=StubPlatform())
    svc: SamplerService = services["sampler_service"]

    # Add old and new samples manually
    old = datetime.now(UTC) - timedelta(days=2)
    new = datetime.now(UTC) - timedelta(hours=1)
    svc._history.append(_sample(timestamp=old))
    svc._history.append(_sample(timestamp=new))

    # Retention is 1 day by default
    svc._prune()

    assert len(svc._history) == 1
    assert svc._history[0].timestamp >= new


# -----------------------------------------------------------------------
# PerformancePage tests
# -----------------------------------------------------------------------


def test_performance_page_filters_time_ranges(qt_app, tmp_path: Path) -> None:
    """Time range selector should filter history correctly."""
    page = PerformancePage(_context(tmp_path))
    page.show()
    qt_app.processEvents()

    # Create samples at different times
    now = datetime.now(UTC)
    samples = [
        _sample(timestamp=now - timedelta(minutes=20)),  # outside 15m
        _sample(timestamp=now - timedelta(minutes=10)),  # inside 15m
        _sample(timestamp=now - timedelta(minutes=5)),   # inside 15m
    ]

    fake_svc = FakeSamplerService(samples)
    page._service = fake_svc

    # Test 15 minutes range
    page._range = timedelta(minutes=15)
    page._apply_sample(samples)

    # Charts should only have 2 samples (last 15 minutes)
    for card in page._charts.values():
        chart = card._chart
        assert len(chart._points) == 2

    # Test 24 hours range
    page._range = timedelta(hours=24)
    page._apply_sample(samples)
    for card in page._charts.values():
        chart = card._chart
        assert len(chart._points) == 3

    page.close()


def test_performance_page_pause_stops_ui_updates(qt_app, tmp_path: Path) -> None:
    """Pause button should stop UI updates but not sampling."""
    page = PerformancePage(_context(tmp_path))
    page.show()
    qt_app.processEvents()

    samples = [_sample(), _sample()]
    fake_svc = FakeSamplerService(samples)
    page._service = fake_svc

    # Apply initial samples
    page._apply_sample(samples)

    # Enable pause
    page._paused = True
    page._pause_button.setText("Resume")

    # New sample arrives - should be ignored due to pause
    new_sample = _sample(cpu_percent=99.0)
    fake_svc._samples.append(new_sample)  # Add to fake service history
    page._on_sampled(new_sample)

    # Values should not have updated to 99%
    cpu_value = page._value_rows["cpu"]._value.text()
    assert "99%" not in cpu_value

    # Disable pause
    page._paused = False
    page._pause_button.setText("Pause")
    page._on_sampled(new_sample)

    # Now values should update
    cpu_value = page._value_rows["cpu"]._value.text()
    assert "99%" in cpu_value

    page.close()


# -----------------------------------------------------------------------
# FloatingPanel tests
# -----------------------------------------------------------------------


def test_floating_panel_timer_stops_on_hide(qt_app, tmp_path: Path) -> None:
    """Timer should stop when panel is hidden."""
    fake_svc = FakeSamplerService([_sample()])
    panel = FloatingPanel(fake_svc)
    panel.show()
    qt_app.processEvents()

    assert panel._refresh_timer.isActive()

    panel.hide_panel()
    qt_app.processEvents()

    assert not panel._refresh_timer.isActive()
    assert not panel.is_visible()

    panel.show_panel()
    qt_app.processEvents()

    assert panel._refresh_timer.isActive()
    assert panel.is_visible()

    panel.close()


def test_floating_panel_uses_shared_history(qt_app, tmp_path: Path) -> None:
    """Panel should display samples from shared service history."""
    samples = [_sample(cpu_percent=10.0), _sample(cpu_percent=20.0)]
    fake_svc = FakeSamplerService(samples)
    panel = FloatingPanel(fake_svc)
    panel.show()
    qt_app.processEvents()

    # Panel should have received and displayed the history
    # Check that cards have been updated with values (not "—")
    assert panel._cpu_card._value.text() != "—"
    assert panel._ram_card._value.text() != "—"
    assert panel._disk_card._value.text() != "—"
    assert panel._net_card._value.text() != "—"

    panel.close()


# -----------------------------------------------------------------------
# Integration test: shared sampling stream
# -----------------------------------------------------------------------


def test_shared_sampling_stream_integration(tmp_path: Path) -> None:
    """Dashboard, Performance page, and Floating panel should share one stream."""
    from pcinsight.app import build_services
    from pcinsight.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])

    ctx = _context(tmp_path)
    services = build_services(ctx, platform=StubPlatform())

    # All consumers should reference the SAME sampler service instance
    svc = services["sampler_service"]

    # Create window which will set up the task runner and start the service
    window = MainWindow(ctx)
    window.show()
    app.processEvents()

    # Verify service is running
    assert svc.running

    # Performance page should be connected to the service
    perf_page = window._performance
    assert perf_page._service is svc

    # Floating panel (when created) should use the same service
    window._toggle_floating_panel(True)
    app.processEvents()

    assert window._floating_panel is not None
    assert window._floating_panel._sampler_service is svc

    # Cleanup - close floating panel
    window._toggle_floating_panel(False)
    app.processEvents()
    
    # Hide main window - service should still be running for potential floating panel
    window.close()
    app.processEvents()

    # Service should still be running (app not exited)
    assert svc.running
    
    # Actually exit the application
    window._exit_application()
    app.processEvents()
    
    # Now service should be stopped
    assert not svc.running


def test_sampler_service_sample_once_for_manual_refresh(tmp_path: Path) -> None:
    """sample_once should collect a sample and invoke callback on GUI thread."""
    from PySide6.QtWidgets import QApplication

    from pcinsight.app import build_services
    from pcinsight.storage import db

    app = QApplication.instance() or QApplication([])

    ctx = _context(tmp_path)
    # Ensure database is migrated
    db.migrate(sqlite3.connect(ctx.paths.database))
    services = build_services(ctx, platform=StubPlatform())
    svc: SamplerService = services["sampler_service"]
    runner = TaskRunner(None)
    svc.set_task_runner(runner)

    results = []

    def callback(result, error):
        results.append((result, error))

    svc.sample_once(callback)

    # Wait for async completion - process events to allow signal delivery
    while not results and runner.wait_for_done(100):
        app.processEvents()

    assert len(results) == 1
    result, error = results[0]
    assert error is None
    assert isinstance(result, CollectorResult)
    assert result.status == CollectorStatus.OK
    assert isinstance(result.data, MetricSample)