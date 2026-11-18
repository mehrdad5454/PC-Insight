"""Runtime capability detection.

PC Insight always starts without administrator rights. This module reports the
privilege level of the current process. Whether a specific check is available is
decided by the collector that performs it and returned as a SKIPPED result, so
the UI never claims a limitation that has not been observed.
"""

from __future__ import annotations

from .models import Capabilities
from .platform import get_platform
from .platform.base import Platform

_LIMITED_MODE_NOTICE = (
    "Some diagnostics may be unavailable without administrator rights; "
    "each affected check reports its own status."
)


def detect(platform_impl: Platform | None = None) -> Capabilities:
    """Inspect the current process and return its privilege level."""
    plat = platform_impl or get_platform()

    try:
        is_admin = bool(plat.is_administrator())
    except Exception:
        is_admin = False

    try:
        os_release = plat.os_release()
    except Exception:
        os_release = ""

    limitations: list[str] = []
    if plat.name == "windows" and not is_admin:
        limitations.append(_LIMITED_MODE_NOTICE)

    return Capabilities(
        platform=plat.name,
        is_administrator=is_admin,
        os_release=os_release,
        limitations=limitations,
    )


def describe(caps: Capabilities) -> str:
    """Return a short, user-facing access description."""
    if caps.is_administrator:
        return "Administrator"
    return "Limited (no administrator rights)"