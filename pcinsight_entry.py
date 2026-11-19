"""PyInstaller entry point for PC Insight."""

import sys
import os

# Add the project root to sys.path so pcinsight can be imported as a package
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pcinsight.app import main

if __name__ == '__main__':
    sys.exit(main())