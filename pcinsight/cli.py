"""PC Insight - Entry point for PyInstaller."""

from __future__ import annotations

import sys

from pcinsight.app import main

if __name__ == "__main__":
    sys.exit(main())