"""Application context passed to the UI and services."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Any

from .config import AppPaths, Settings
from .models import Capabilities


@dataclass(slots=True)
class AppContext:
    """Everything the UI and services need for one run.

    ``services`` stays empty until the first service exists; adding one does not
    change the constructor of the window.
    """

    paths: AppPaths
    settings: Settings
    capabilities: Capabilities
    connection: sqlite3.Connection
    services: dict[str, Any] = field(default_factory=dict)
    sampler_service: Any = None