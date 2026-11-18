"""Configuration and path resolution."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from pcinsight import config


def test_defaults_are_valid() -> None:
    settings = config.Settings()
    assert settings.theme in config.THEMES
    assert settings.sampling_interval_s > 0
    assert settings.history_retention_days > 0
    assert settings.scan_time_budget_s > 0
    assert settings.scan_max_depth > 0


def test_portable_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "app_base_dir", lambda: tmp_path)

    paths = config.resolve_paths(portable=True)

    assert paths.data_dir == tmp_path / "data"
    assert paths.database == tmp_path / "data" / "pcinsight.db"
    assert paths.log_file == tmp_path / "data" / "logs" / "pcinsight.log"
    assert paths.cache_dir == tmp_path / "data" / "cache"


def test_resolve_paths_does_not_touch_disk(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "app_base_dir", lambda: tmp_path)

    paths = config.resolve_paths(portable=True)

    assert not paths.data_dir.exists()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows path layout")
def test_installed_paths_use_localappdata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\test\AppData\Local")

    paths = config.resolve_paths(portable=False)

    assert paths.data_dir == Path(r"C:\Users\test\AppData\Local") / config.DATA_DIR_NAME