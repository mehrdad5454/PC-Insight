"""Main application window.

P4 turns the P1 shell into the real application frame: a navigation rail, the
dashboard page, the limited-access notice and a status line. The window is also
the only place that starts background work: it submits the collectors to the
``TaskRunner`` and renders the results when they arrive on the GUI thread.
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QFont
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..config import APP_NAME, APP_VERSION
from ..context import AppContext
from ..models import CollectorResult, CollectorStatus, SystemInfo
from . import theme, widgets
from .pages.dashboard import DashboardPage
from .pages.performance import PerformancePage
from .tasks import TaskRunner
from .view_models import format_duration_ms

logger = logging.getLogger(__name__)

_STATUS_IDLE = "Ready"
_STATUS_COLLECTING = "Collecting system information and live metrics..."
_REFRESH_LABEL = "Refresh"
_REFRESHING_LABEL = "Refreshing..."


class MainWindow(QMainWindow):
    """Application frame: navigation, pages, status and background work."""

    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self._tasks = TaskRunner(self)
        self._closed = False
        self._generation = 0
        self._theme_name = context.settings.theme

        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.resize(1040, 680)

        central = QWidget(self)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_navigation())
        root.addWidget(self._build_content(), 1)
        self.setCentralWidget(central)

        self.apply_theme(self._theme_name)

        # Connect navigation buttons to page switching
        self._overview_button.clicked.connect(
            lambda: self._pages.setCurrentWidget(self._dashboard)
        )
        self._performance_button.clicked.connect(
            lambda: self._pages.setCurrentWidget(self._performance)
        )

        # Connect sampler service to task runner and start it
        sampler_service = self.context.sampler_service
        if sampler_service is not None:
            sampler_service.set_task_runner(self._tasks)
            sampler_service.start()

        # Floating panel (created lazily)
        self._floating_panel: widgets.FloatingPanel | None = None

    def _toggle_floating_panel(self, checked: bool) -> None:
        """Show or hide the floating desktop panel."""
        if self._floating_panel is None:
            sampler_service = self.context.sampler_service
            if sampler_service is None:
                self._float_button.setChecked(False)
                return
            self._floating_panel = widgets.FloatingPanel(sampler_service, self)
            self._floating_panel.visibility_changed.connect(self._on_floating_visibility_changed)
            # Position near the main window
            self._floating_panel.move(self.x() + self.width() + 20, self.y() + 50)
        if checked:
            self._floating_panel.show_panel()
        else:
            self._floating_panel.hide_panel()

    def _on_floating_visibility_changed(self, visible: bool) -> None:
        self._float_button.setChecked(visible)

    # ------------------------------------------------------------------ layout

    def _build_navigation(self) -> QWidget:
        rail = QFrame(self)
        rail.setObjectName("NavRail")
        rail.setFixedWidth(196)
        layout = QVBoxLayout(rail)
        layout.setContentsMargins(12, 18, 12, 16)
        layout.setSpacing(10)

        brand = QLabel(APP_NAME, rail)
        brand_font = QFont()
        brand_font.setPointSize(12)
        brand_font.setBold(True)
        brand.setFont(brand_font)
        layout.addWidget(brand)

        version = QLabel(f"Version {APP_VERSION}", rail)
        version.setObjectName("CardHint")
        layout.addWidget(version)
        layout.addSpacing(8)

        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        self._overview_button = QPushButton("Overview", rail)
        self._overview_button.setObjectName("NavButton")
        self._overview_button.setCheckable(True)
        self._overview_button.setChecked(True)
        self._nav_group.addButton(self._overview_button)
        layout.addWidget(self._overview_button)

        self._performance_button = QPushButton("Performance", rail)
        self._performance_button.setObjectName("NavButton")
        self._performance_button.setCheckable(True)
        self._nav_group.addButton(self._performance_button)
        layout.addWidget(self._performance_button)

        self._float_button = QPushButton("Floating Panel", rail)
        self._float_button.setObjectName("NavButton")
        self._float_button.setCheckable(True)
        self._float_button.clicked.connect(self._toggle_floating_panel)
        layout.addWidget(self._float_button)
        layout.addStretch(1)

        self._theme_button = QPushButton("Theme: " + self._theme_name, rail)
        self._theme_button.setObjectName("NavButton")
        self._theme_button.clicked.connect(self._cycle_theme)
        layout.addWidget(self._theme_button)
        return rail

    def _build_content(self) -> QWidget:
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._notice = widgets.notice(self._notice_text(), container)
        notice_row = QWidget(container)
        notice_layout = QVBoxLayout(notice_row)
        notice_layout.setContentsMargins(20, 14, 20, 0)
        notice_layout.addWidget(self._notice)
        layout.addWidget(notice_row)

        self._pages = QStackedWidget(container)
        self._dashboard = DashboardPage(self.context, self)
        self._pages.addWidget(self._dashboard)

        self._performance = PerformancePage(self.context, self)
        self._pages.addWidget(self._performance)

        layout.addWidget(self._pages, 1)

        layout.addWidget(self._build_status_bar(container))
        return container

    def _build_status_bar(self, parent: QWidget) -> QWidget:
        bar = QFrame(parent)
        bar.setObjectName("StatusBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(20, 10, 20, 12)
        layout.setSpacing(12)

        self._status = QLabel(_STATUS_IDLE, bar)
        self._status.setObjectName("CardHint")
        layout.addWidget(self._status, 1)

        self._refresh_button = QPushButton(_REFRESH_LABEL, bar)
        self._refresh_button.setObjectName("Action")
        self._refresh_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_button.clicked.connect(self.refresh)
        layout.addWidget(self._refresh_button)
        return bar

    def _notice_text(self) -> str:
        limitations = self.context.capabilities.limitations
        return " ".join(limitations) if limitations else ""

    # ------------------------------------------------------------------- theme

    def apply_theme(self, name: str) -> str:
        """Apply ``name`` to the window and return the theme actually applied.

        An unknown name falls back to the default theme, so a value that cannot
        be interpreted never leaves the window unstyled.
        """
        self._theme_name = name
        resolved = theme.theme_key(name, is_dark=self._system_prefers_dark())
        self.setStyleSheet(theme.style_sheet(resolved))
        self._theme_button.setText(f"Theme: {resolved}")
        return resolved

    def _system_prefers_dark(self) -> bool:
        app = QApplication.instance()
        if app is None:
            return False
        try:
            return app.styleHints().colorScheme() == Qt.ColorScheme.Dark
        except (AttributeError, RuntimeError):
            return False

    def _cycle_theme(self) -> None:
        """Step through the configured theme choices."""
        from ..config import THEMES

        try:
            index = THEMES.index(self._theme_name)
        except ValueError:
            index = -1
        self.apply_theme(THEMES[(index + 1) % len(THEMES)])

    # ---------------------------------------------------------------- refresh

    def refresh(self) -> None:
        """Collect system information and one metric sample in the background."""
        if self._closed:
            return
        if not self._has_required_services():
            self._status.setText("Metrics are unavailable in this session")
            return

        self._generation += 1
        generation = self._generation
        self._refresh_button.setEnabled(False)
        self._refresh_button.setText(_REFRESHING_LABEL)
        self._status.setText(_STATUS_COLLECTING)
        self._tasks.submit(
            self._collect,
            with_token=False,
            on_done=lambda results, error: self._on_collected(generation, results, error),
        )

    def _has_required_services(self) -> bool:
        services = self.context.services
        return "system_info" in services and "sampler_service" in services

    def _collect(self) -> dict[str, CollectorResult]:
        """Run both services; this executes on a worker thread.

        Each service is called on its own: one failing must not hide the other
        one's result, so a broken collector is reported as a failed
        ``CollectorResult`` and the healthy half still renders.
        """
        services = self.context.services
        results: dict[str, CollectorResult] = {}

        # System info collection
        try:
            results["system_info"] = services["system_info"].collect()
        except Exception as exc:
            logger.warning("system_info collection failed: %s", exc)
            message = str(exc).strip() or type(exc).__name__
            results["system_info"] = CollectorResult.failed("system_info", message)

        # Metrics collection via shared sampler service (uses same MetricsSampler instance)
        sampler_service = services.get("sampler_service")
        if sampler_service is not None:
            try:
                results["metrics"] = sampler_service._sampler.sample()
            except Exception as exc:
                logger.warning("metrics collection failed: %s", exc)
                message = str(exc).strip() or type(exc).__name__
                results["metrics"] = CollectorResult.failed("metrics", message)
        else:
            results["metrics"] = CollectorResult.failed("metrics", "sampler service not available")

        return results

    def _on_collected(
        self, generation: int, results: Any, error: Exception | None
    ) -> None:
        """Render a finished collection on the GUI thread."""
        if self._closed or generation != self._generation:
            logger.debug("ignoring a stale or post-close collection result")
            return

        self._refresh_button.setEnabled(True)
        self._refresh_button.setText(_REFRESH_LABEL)

        if error is not None or not isinstance(results, dict):
            logger.warning("collection failed: %s", error)
            self._status.setText(f"Refresh failed: {error}")
            return

        info_result = results.get("system_info")
        metrics_result = results.get("metrics")
        info = info_result.data if isinstance(info_result, CollectorResult) else None
        sample = metrics_result.data if isinstance(metrics_result, CollectorResult) else None

        self._dashboard.refresh(
            info if isinstance(info, SystemInfo) else None,
            sample if hasattr(sample, "cpu_percent") else None,
        )
        self._status.setText(self._status_text(info_result, metrics_result))

    def _status_text(
        self, info_result: CollectorResult | None, metrics_result: CollectorResult | None
    ) -> str:
        if not isinstance(info_result, CollectorResult) or not isinstance(
            metrics_result, CollectorResult
        ):
            return "Refresh failed: a service did not report a result"
        slowest = max(info_result.duration_ms, metrics_result.duration_ms)
        degraded = {
            CollectorStatus.FAILED,
            CollectorStatus.SKIPPED,
            CollectorStatus.PARTIAL,
        }
        problems = [
            f"{result.name}: {result.message}"
            for result in (info_result, metrics_result)
            if result.status in degraded
        ]
        if problems:
            timing = format_duration_ms(slowest)
            return f"Updated with limitations ({timing}) - " + "; ".join(problems)
        return f"Updated in {format_duration_ms(slowest)}"

    # ------------------------------------------------------------------ events

    @property
    def task_runner(self) -> TaskRunner:
        """Return the runner that pages use for background work."""
        return self._tasks

    def closeEvent(self, event: QCloseEvent) -> None:
        """Stop background work and ignore any result that arrives afterwards."""
        self._closed = True
        if self._floating_panel is not None:
            self._floating_panel.close()
        sampler_service = self.context.sampler_service
        if sampler_service is not None:
            sampler_service.stop()
        self._tasks.cancel_all()
        self._tasks.wait_for_done(3000)
        super().closeEvent(event)