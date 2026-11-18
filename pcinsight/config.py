"""Paths, constants and user settings.

Nothing here performs I/O at import time. Paths are resolved through
:func:`resolve_paths` so portable mode and tests can redirect storage.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from . import __version__
from .errors import PlatformError
from .platform import get_platform

APP_NAME = "PC Insight"
APP_SLUG = "PCInsight"
APP_VERSION = __version__
DATA_DIR_NAME = "PCInsight"
DATABASE_NAME = "pcinsight.db"
LOG_FILE_NAME = "pcinsight.log"

THEMES = ("system", "light", "dark")
DEFAULT_THEME = "system"


def app_base_dir() -> Path:
    """Root folder used by portable mode.

    When frozen by PyInstaller this is the folder that contains the executable;
    during development it is the project root.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def data_dir_for(portable: bool) -> Path:
    """Resolve the writable data folder for the current mode and platform."""
    if portable:
        return app_base_dir() / "data"
    try:
        return get_platform().default_data_dir(DATA_DIR_NAME)
    except PlatformError:
        return Path.home() / ".local" / "share" / DATA_DIR_NAME


@dataclass(frozen=True, slots=True)
class AppPaths:
    """Every writable location used by the application."""

    data_dir: Path
    database: Path
    logs_dir: Path
    log_file: Path
    cache_dir: Path


def resolve_paths(portable: bool = False) -> AppPaths:
    """Build the full set of application paths for a run."""
    data = data_dir_for(portable)
    logs = data / "logs"
    return AppPaths(
        data_dir=data,
        database=data / DATABASE_NAME,
        logs_dir=logs,
        log_file=logs / LOG_FILE_NAME,
        cache_dir=data / "cache",
    )


@dataclass(slots=True)
class Settings:
    """User settings persisted in the local SQLite database."""

    theme: str = DEFAULT_THEME
    sampling_interval_s: float = 5.0
    history_retention_days: int = 1
    scan_time_budget_s: int = 90
    scan_max_depth: int = 12
    export_dir: str = ""