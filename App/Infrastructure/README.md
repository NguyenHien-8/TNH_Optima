# App / Infrastructure

## Project Overview

The infrastructure layer provides shared persistence, resource location, and error handling. It contains no UI logic or project-domain behavior.

## Annotated Directory Structure

- `CrashHandler.py` — rotating logs, Python/thread exception hooks, and native fault logging.
- `Helpers/ResourceHelper.py` — resolves icon, QSS, and asset paths in source and PyInstaller builds.
- `Helpers/RecycleBinHelper.py` — moves files or folders to the Windows Recycle Bin; if native recycling fails, the original content is kept and there is no permanent-delete fallback.
- `Helpers/MediaHelper.py` — shared definitions for supported Image/Video extensions.
- `Helpers/WindowOwnershipHelper.py` — AppUserModelID, taskbar style, and secondary-window scale/centering against `availableGeometry()`.
- `Repositories/` — Config/Session SQLite repositories and `StoragePath`.
- `Persistence/` — package marker; runtime databases are not stored or bundled here.
- `__init__.py` — package marker.

## Core Algorithms & Implementation

- Logs are written under Local App Data and rotated to limit disk usage.
- Runtime databases live in a writable per-user folder; source uses a
  Development area separated from the PyInstaller executable's Production area.
- Legacy databases in the source tree or bundle are not migrated into Production.
- SQLite connections always commit/rollback/close through context managers.
- Logging or migration errors must not prevent the application from starting.
- The window helper is a no-op outside Windows; Shell/User32 errors are logged and fall back to default Qt behavior instead of crashing the application.

## Data Flow

1. `main.py` installs `CrashHandler` before importing the PyQt shell.
2. A repository requests its path from `StoragePath`, opens a short transaction, and closes the connection immediately.
3. ViewModels/Models read or write configuration and session data through repositories.
4. Unhandled exceptions are logged and displayed safely on the main thread.
5. Startup sets the taskbar identity before the first UI; secondary windows create native handles and taskbar styles before showing.
6. FileEditor/Droplet windows are bounded to the current screen work area so they do not overflow the display.
