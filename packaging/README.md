# Packaging (planned for P9)

No build artifact exists yet. This folder defines where packaging files will
live so P9 does not require a structural change.

Planned files:

| File | Purpose |
| --- | --- |
| `pcinsight.spec` | PyInstaller spec, `--onedir` mode, `pcinsight` entry point |
| `build.ps1` | Runs PyInstaller and writes `dist\PCInsight\` |
| `version.txt` | Product version shown by the build |

Planned build command (P9):

```powershell
.venv\Scripts\python.exe -m PyInstaller packaging\pcinsight.spec --noconfirm
```

Constraints for P9:

- `--onedir` (not `--onefile`) for startup speed.
- Bundle `pcinsight/storage/schema.sql` as package data.
- No installer, no auto-update, no code signing in the MVP.
- The application must run without administrator rights; the build must not
  embed an elevation manifest.