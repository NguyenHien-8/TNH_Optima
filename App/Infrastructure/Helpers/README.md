# App / Infrastructure / Helpers

## Project Overview

Shared helpers for locating resources and normalizing ownership/taskbar behavior for secondary windows.

## Annotated Directory Structure

- `ResourceHelper.py` — detects the project/bundle root, builds resource paths, and loads QSS centrally.
- `WindowOwnershipHelper.py` — taskbar identity, logical-owner resolution, and secondary-window registration with MainView.
- `__init__.py` — package marker.

## Core Algorithms & Implementation

- `base_path()` is cached and checks `sys.frozen`/`sys._MEIPASS`; when running from source, it walks from the helper to the correct project root without depending on the current working directory.
- `resource_path()`, `app_resource_path()`, `icon_path()`, and `stylesheet_path()` create semantic absolute paths.
- `load_stylesheet()` caches each QSS file; `apply_stylesheet()` applies styles consistently to widgets and avoids repeated file reads.
- `initialize_taskbar_identity()` sets AppUserModelID before the first UI is created so MainView, File Editor, and Droplet Analysis share the same taskbar group.
- `configure_secondary_window()` creates the native handle before first show, registers the window with MainView, and idempotently applies `WS_EX_APPWINDOW`/removes `WS_EX_TOOLWINDOW` on Windows; it does not assign a transient parent, so each window keeps an independent minimized state.
- Win32 APIs are wrapped defensively: handles are validated, HRESULT/last-error is checked, errors are logged, and safe fallback is used; other platforms still use MainView registration/coordination.

## Data Flow

1. A View requests a QSS/icon path.
2. The helper chooses the project root or `_MEIPASS`, then loads QSS/icons from `App/ReSource`.
3. The View opens the file or creates a `QIcon` from the normalized path.
4. A secondary window resolves the MainView logical owner -> registers for coordinated minimize -> enables grouped taskbar thumbnails -> reapplies idempotently in `showEvent`.
