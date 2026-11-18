"""Exception hierarchy for PC Insight."""

from __future__ import annotations


class PCInsightError(Exception):
    """Base class for every error raised by PC Insight."""


class PlatformError(PCInsightError):
    """Raised when an operating-system operation cannot be performed."""


class StorageError(PCInsightError):
    """Raised when the local database cannot be opened, migrated or queried."""


class CollectorError(PCInsightError):
    """Raised when a collector cannot complete its work.

    Collectors normally report failures through ``CollectorResult`` instead of
    raising; this exception exists for unexpected programming errors.
    """