<div align="center">

# PC Insight

**A Lightweight Windows System Monitor**

*Understand Your PC. Monitor Its Performance.*

![Windows](https://img.shields.io/badge/Windows-10%2F11-0078D6?logo=windows&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.11%E2%80%933.14-3776AB?logo=python&logoColor=white)
![PySide6](https://img.shields.io/badge/PySide6-6.12-41CD52?logo=qt&logoColor=white)
![License](https://img.shields.io/badge/License-TBD-lightgrey)
![Tests](https://img.shields.io/badge/Tests-170%20passing-brightgreen)
![Release](https://img.shields.io/badge/Release-v0.1.0-orange)

</div>

---

## Overview

**PC Insight** is a local-first, privacy-respecting desktop application for monitoring Windows 10/11 systems. It provides real-time visibility into your PC's hardware, resource usage, and performance metrics — all without sending any data outside your machine.

Built with Python and PySide6 (Qt for Python), PC Insight runs entirely on your computer. No telemetry, no cloud accounts, and no separate background service.

---

## Features

### 📊 Dashboard (Overview)
- **Hardware inventory**: CPU model, cores, base frequency, total memory, motherboard, BIOS
- **Live counters**: CPU %, memory usage, disk I/O, network throughput
- **Storage health**: Disk usage bars, free space, disk health status from Windows Storage (`Get-PhysicalDisk`), media type (SSD/HDD)
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

Application screenshots will be added in a future update. The current version
includes a Dashboard page, a Performance page with four live charts, and a
detachable Floating Panel.

---

## Architecture

PC Insight is organized into small layers, each with a single responsibility:

```
app.py / cli.py   → Composition root: builds services and starts the UI
ui/               → PySide6 widgets, pages, view models (presentation)
services/         → Application logic: sampling and system-info orchestration
collectors/       → Read-only data collectors (one per data source)
platform/         → OS adapters (PowerShell CIM queries, psutil, registry)
storage/          → SQLite connection, migrations, repositories
config.py         → Paths, constants and settings resolution
models.py         → Pure data contracts (dataclasses, enums) — no logic, no Qt
errors.py         → Exception hierarchy
```

**Design notes**:
- **Shared contracts first**: `models.py` holds the dataclasses and enums used
  across layers; it has no internal dependencies and no Qt imports.
- **OS code is isolated**: everything Windows-specific lives in `platform/`,
  behind the `Platform` interface, so the rest of the code talks to a contract
  rather than to Windows APIs.
- **Composition at the top**: `app.py` is the only place that builds and wires
  the platform, services, storage and UI together.
- **Fail-safe collectors**: a collector returns a `CollectorResult` with status
  `OK | PARTIAL | SKIPPED | FAILED` and never raises, so one failing data source
  cannot stop the application.
- **Background work**: long operations run on a `QThreadPool` through the
  cancellable `TaskRunner` in `ui/tasks.py`.

---

## Requirements

| Component | Version |
|-----------|---------|
| OS | Windows 10 (19041+) or Windows 11 |
| Python | 3.11 – 3.14 (developed and tested on 3.14) |

A virtual environment with the project dependencies and development tools takes
a few hundred megabytes of disk space.

**Optional**: The application always starts without administrator rights. Some
diagnostics (for example physical disk health) may be unavailable in this
limited mode; those fields then report as unavailable while the rest of the app
works normally.

---

## Quick Start (Windows Executable)

### Download
1. Go to the [Releases](https://github.com/mehrdad5454/PC-Insight/releases) page
2. Download `PCInsight.exe` from the latest release (v0.1.0+)
3. **Verify SHA256** (listed in release notes)
4. Run `PCInsight.exe` — no installation required

### Portable Mode
Place `PCInsight.exe` in any folder and run it with `--portable`:
```cmd
PCInsight.exe --portable
```
The application creates the `data` folder next to the executable automatically;
you do not need to create it yourself. The database and logs are stored under
`data\` instead of `%LOCALAPPDATA%\PCInsight`.

---

## Running from Source

```powershell
# 1. Clone
git clone https://github.com/mehrdad5454/PC-Insight.git
cd PC-Insight

# 2. Create a virtual environment with any supported Python (3.11–3.14)
py -3.11 -m venv .venv
#    Use the version you have installed, for example:
#    py -3.14 -m venv .venv

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
# All tests (170)
.venv\Scripts\python.exe -m pytest -v

# Lint
.venv\Scripts\python.exe -m ruff check .
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

- **Windows only**: Linux and macOS are not supported.
- **Administrator rights**: Some diagnostics (such as physical disk health) may be unavailable without elevation.
- **Single-file EXE startup**: Cold start is slower than running from source because PyInstaller extracts the bundle to a temporary folder first.
- **No installer**: Portable EXE only; no auto-update and no code signing.
- **No localization**: English UI only.
- **Python support**: Developed and tested on Python 3.14; the package declares support for Python 3.11–3.14.

---

## v0.1.0 Release Notes

### Implemented
- ✅ System information collection (CPU, memory, disks, GPU, motherboard, BIOS, OS)
- ✅ Live metric sampling (CPU, RAM, disk I/O, network, top process) at a 5-second interval
- ✅ SQLite persistence with automatic 24-hour rolling window (17,280 samples)
- ✅ Dashboard page: hardware inventory + live counters + storage + graphics
- ✅ Performance page: 4 sparklines, time-range selector, pause/resume
- ✅ Floating desktop panel: draggable, always-on-top, 4 mini sparklines
- ✅ Theme switching: Light / Dark / System
- ✅ Portable mode (`--portable`)
- ✅ Clean shutdown: timers stopped, DB connections closed, threads joined

### Future Development
The following are possible directions for future work. They are not implemented
in v0.1.0 and carry no delivery schedule or commitment:

- Deeper storage analysis and cleanup recommendations.
- Additional diagnostic checks and health findings.
- Exporting reports (CSV/HTML/JSON).

---

## License

**License: To Be Determined**

The project currently does not include a LICENSE file. The author will select an appropriate license (e.g., MIT, Apache-2.0, BSD-3-Clause) before the first stable release.

> **Third-party dependencies**: PC Insight depends on third-party packages,
> notably **PySide6** and **psutil**, which have their own license terms. If you
> plan to redistribute or use this project in a commercial context, review the
> official license terms of each dependency (see the PySide6 and psutil
> projects) and obtain your own legal advice. This README does not state or
> imply a conclusion about your obligations.

---

## Author

**Mehrdad** — [GitHub](https://github.com/mehrdad5454) · [LinkedIn](https://www.linkedin.com/in/mehrdad-haghi-955525383/)

Built as a portfolio project demonstrating layered application design,
Qt/PySide6, Windows system programming, and Python packaging.

---

## Acknowledgments

- [PySide6](https://wiki.qt.io/Qt_for_Python) — Qt for Python
- [psutil](https://github.com/giampaolo/psutil) — Cross-platform process & system utilities
- [PyInstaller](https://pyinstaller.org/) — Python application bundling
- [SQLite](https://sqlite.org/) — Embedded database engine