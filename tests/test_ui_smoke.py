"""GUI shell smoke test."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

pytest.importorskip("PySide6")


def test_main_window_shell(qt_app, tmp_path: Path) -> None:
    from pcinsight.config import AppPaths, Settings
    from pcinsight.context import AppContext
    from pcinsight.models import Capabilities
    from pcinsight.ui.main_window import MainWindow

    paths = AppPaths(
        data_dir=tmp_path,
        database=tmp_path / "pcinsight.db",
        logs_dir=tmp_path / "logs",
        log_file=tmp_path / "logs" / "pcinsight.log",
        cache_dir=tmp_path / "cache",
    )
    connection = sqlite3.connect(":memory:")
    context = AppContext(
        paths=paths,
        settings=Settings(),
        capabilities=Capabilities(
            platform="windows",
            is_administrator=False,
            os_release="Windows 11",
            limitations=["Some diagnostics may be unavailable without administrator rights"],
        ),
        connection=connection,
    )

    window = MainWindow(context)
    window.show()
    qt_app.processEvents()

    assert window.windowTitle().startswith("PC Insight")
    assert window.isVisible()

    window.close()
    connection.close()