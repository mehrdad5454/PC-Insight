"""Platform abstraction: operating-system specific code lives here only."""

from __future__ import annotations

import sys

from ..errors import PlatformError
from .base import Platform

_instance: Platform | None = None


def get_platform() -> Platform:
    """Return the platform adapter for the current operating system.

    Adding Linux or macOS support means adding an adapter module in this
    package and one branch here; no other module has to change.
    """
    global _instance
    if _instance is None:
        if sys.platform == "win32":
            from .windows import WindowsPlatform

            _instance = WindowsPlatform()
        else:
            raise PlatformError(
                f"platform {sys.platform!r} is not supported yet; "
                "add an adapter in pcinsight/platform/"
            )
    return _instance