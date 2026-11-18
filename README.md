<div align="center">

# PC Insight

**A Lightweight Windows System Monitor**

*Understand Your PC. Monitor Its Performance.*

![Windows](https://img.shields.io/badge/Windows-10%2F11-0078D6?logo=windows&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![PySide6](https://img.shields.io/badge/PySide6-6.12-41CD52?logo=qt&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-blue)
![Tests](https://img.shields.io/badge/Tests-170%20passing-brightgreen)
![Release](https://img.shields.io/badge/Release-v0.1.0-orange)

</div>

---

## Overview

**PC Insight** is a local-first, privacy-respecting desktop application for monitoring Windows 10/11 systems. It provides real-time visibility into your PC's hardware, resource usage, and performance metrics — all without sending any data outside your machine.

Built with Python and PySide6 (Qt for Python), PC Insight runs entirely on your computer. No telemetry, no cloud accounts, no background services.

---

## Features

### 📊 Dashboard (Overview)
- **Hardware inventory**: CPU model, cores, base frequency, total memory, motherboard, BIOS
- **Live counters**: CPU %, memory usage, disk I/O, network throughput
- **Storage health**: Disk usage bars, free space, SMART health status, media type (SSD/HDD)
- **Graphics**: GPU names and basic info
- **Top process**: Busiest user-space process with CPU percentage

### 📈 Performance Monitoring
- **Four live sparkline charts**: CPU load, Memory %, Disk activity (MB/s), Network (MB/s)
- **Time-range selector**: 15 minutes / 1 hour / 24 hours
- **Pause/Resume**: Stop live updates without closing the window
- **Current value readouts**: Numeric display alongside each chart

### 🖥️ Floating Desktop Panel
- **Always-on-top mini window**: Draggable, frameless, stays above other windows
- **Compact sparklines**: CPU, RAM, Disk, Network in a 280×220 panel
- **Context menu**: Toggle always-on-top, hide panel
- **Shared data source**: Consumes the same sampling stream as the Performance page

### 💾 24-Hour History & Persistence
- **SQLite database**: Local, portable, no external dependencies
- **Automatic retention**: Configurable history retention (default 24 hours at 5-second cadence = 17,280 samples)
- **Survives restarts**: Close and reopen — your history is preserved
- **Data directory**: `%LOCALAPPDATA%\PCInsight` (or `--portable` for folder-next-to-exe)

### 🎨 Theming
- **Light / Dark / System**: Three theme modes with instant switching
- **High-contrast cards**: Readable charts and text in both themes

---

## Screenshots

| Dashboard | Performance | Floating Panel |
|-----------|-------------|----------------|
| ![Dashboard](docs/screenshots/dashboard.png) | ![Performance](docs/screenshots/performance.png) | ![Floating Panel](docs/screenshots/floating-panel.png) |

> **Note**: Screenshots will be added after first release. The application includes a Dashboard page, Performance page with four live charts, and a detachable Floating Panel.

---

## Architecture

PC Insight follows a clean, layered architecture:

```
ui/              → PySide6 widgets, pages, view models (presentation only)
services/        → Application logic: sampling, system info, task running
collectors/      → Read-only data collectors (one per data source)
platform/        → OS adapters (Windows implementation via psutil, WMI, PowerShell)
storage/         → SQLite connection, migrations, repositories
models.py        → Pure data contracts (dataclasses, enums) — no logic, no Qt
config.py        → Paths, constants, settings resolution
app.py           → Composition root, entry point, CLI
```

**Key principles**:
- **One-way dependencies**: `ui → services → collectors → platform → storage → models`
- **No hidden I/O**: Configuration resolved lazily; database access explicit
- **Fail-safe collectors**: A failed collector never crashes the app; results are `OK | PARTIAL | SKIPPED | FAILED`
- **Background work**: All long operations run on `QThreadPool` via cancellable `TaskRunner`

---

## Requirements

| Component | Version |
|-----------|---------|
| OS | Windows 10 (19041+) or Windows 11 |
| Python | 3.11 – 3.14 (developed on 3.14) |
| Disk space | ~400 MB for venv + dependencies |
| RAM | ~80 MB runtime (plus history buffer) |

**Optional**: Administrator rights enable WMI disk health (SMART) and some CPU details. Without admin, those fields show "unavailable" but the app works normally.

---

## Quick Start (Windows Executable)

### Download
1. Go to the [Releases](https://github.com/mehrdad-dev/PC-Insight/releases) page
2. Download `PCInsight.exe` from the latest release (v0.1.0+)
3. **Verify SHA256** (listed in release notes)
4. Run `PCInsight.exe` — no installation required

### Portable Mode
Place `PCInsight.exe` in any folder. Create a `data` folder next to it, or run with `--portable`:
```cmd
PCInsight.exe --portable
```
Database and logs will be stored in `.\data\` instead of `%LOCALAPPDATA%\PCInsight`.

---

## Running from Source

```powershell
# 1. Clone
git clone https://github.com/mehrdad-dev/PC-Insight.git
cd PC-Insight

# 2. Create virtual environment (Python 3.11+)
py -3.11 -m venv .venv

# 3. Install in editable mode with dev dependencies
.venv\Scripts\python.exe -m pip install -e ".[dev]"

# 4. Run
.venv\Scripts\python.exe -m pcinsight
```

### CLI Flags
| Flag | Description |
|------|-------------|
| `--portable` | Store data in `./data` next to the script/executable |
| `--debug` | Enable debug logging to console and file |
| `--version` | Print version and exit |

---

## Development

### Run Tests
```powershell
# All tests (170+)
.venv\Scripts\python.exe -m pytest -v

# Lint
.venv\Scripts\python.exe -m ruff check .

# Type check (if configured)
# .venv\Scripts\python.exe -m mypy pcinsight
```

### Build Executable (PyInstaller)
```powershell
# Install PyInstaller
.venv\Scripts\python.exe -m pip install pyinstaller

# Build single-file EXE
.venv\Scripts\python.exe -m PyInstaller PCInsight.spec --clean

# Output: dist\PCInsight.exe (~46 MB)
```

---

## Project Structure

```
PC-Insight/
├─ pcinsight/              # Main package
│  ├─ __init__.py          # Version (0.1.0)
│  ├─ __main__.py          # python -m pcinsight entry
│  ├─ app.py               # Composition root, CLI, services wiring
│  ├─ cli.py               # PyInstaller-friendly entry point
│  ├─ config.py            # Paths, constants, Settings model
│  ├─ context.py           # AppContext (DI container for UI)
│  ├─ models.py            # Data contracts (MetricSample, SystemInfo, etc.)
│  ├─ capabilities.py      # Admin detection, OS version
│  ├─ logging_setup.py     # Rotating file + console logging
│  ├─ errors.py            # Exception hierarchy
│  ├─ platform/            # OS abstraction + Windows impl
│  ├─ collectors/          # Read-only collectors
│  ├─ services/            # SamplerService, SystemInfoService
│  ├─ storage/             # SQLite, migrations, repositories
│  └─ ui/                  # PySide6 application
│     ├─ main_window.py    # Navigation, pages, floating panel
│     ├─ pages/            # Dashboard, Performance
│     ├─ widgets/          # Cards, sparklines, floating panel
│     ├─ view_models.py    # Data → UI transformers
│     └─ tasks.py          # Cancellable QThreadPool wrapper
├─ tests/                  # 170 tests (pytest)
├─ packaging/              # Build plans
├─ PCInsight.spec          # PyInstaller spec (single-file, windowed)
├─ pyproject.toml          # Project metadata, deps, tool config
├─ .gitignore
└─ README.md
```

---

## Limitations & Known Issues

- **Windows only**: No Linux/macOS support planned for v0.x
- **Admin for full disk health**: SMART data requires elevation
- **Single-file EXE startup**: ~2–3 seconds cold start (PyInstaller extraction)
- **No installer**: Portable EXE only; no auto-update, no code signing
- **No localization**: English UI only
- **Python 3.14**: Current development target; 3.11–3.13 tested in CI

---

## v0.1.0 Release Notes

### Implemented (Phases P1–P5)
- ✅ System information collection (CPU, memory, disks, GPU, motherboard, BIOS, OS)
- ✅ Live metric sampling (CPU, RAM, disk I/O, network, top process) at 5-second interval
- ✅ SQLite persistence with automatic 24-hour rolling window (17,280 samples)
- ✅ Dashboard page: hardware inventory + live counters + storage + graphics
- ✅ Performance page: 4 sparklines, time-range selector, pause/resume
- ✅ Floating desktop panel: draggable, always-on-top, 4 mini sparklines
- ✅ Theme switching: Light / Dark / System
- ✅ Portable mode (`--portable`)
- ✅ Clean shutdown: timers stopped, DB connections closed, threads joined

### Not Yet Implemented (Planned)
- Storage scanning & cleanup recommendations (P6)
- Diagnostic rules & health checks (P7)
- Export reports (CSV/HTML/JSON) (P8)
- Installer, code signing, auto-update (P9)
- Linux/macOS support

---

## License

**License: To Be Determined**

The project currently does not include a LICENSE file. The author will select an appropriate license (e.g., MIT, Apache-2.0, BSD-3-Clause) before the first stable release.

> **Dependency licenses**: PySide6 (LGPL v3 / commercial), psutil (BSD-3-Clause). If you intend to use this in a commercial or proprietary context, review these licenses carefully.

---

## Author

**Mehrdad** — [GitHub](https://github.com/mehrdad-dev) • [LinkedIn](https://linkedin.com/in/mehrdad-dev)

Built as a portfolio project demonstrating clean architecture, Qt/PySide6, Windows system programming, and Python packaging.

---

## Acknowledgments

- [PySide6](https://wiki.qt.io/Qt_for_Python) — Qt for Python
- [psutil](https://github.com/giampaolo/psutil) — Cross-platform process & system utilities
- [PyInstaller](https://pyinstaller.org/) — Python application bundling
- [SQLite](https://sqlite.org/) — Embedded database engine