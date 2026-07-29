# App

## Project Overview

`App` is the main package for VCA Optima Release 1.1.1. The source is organized around MVVM: PyQt6 UI in `Presentation`, domain and device logic in `Models`, persistence and error handling in `Infrastructure`, and bundled resources in `ReSource`.

The application prioritizes responsive UI: I/O, camera, serial, media writing, and image analysis run outside the UI thread; heavy features are lazy-imported after the main window has been shown.

## Annotated Directory Structure

- `Presentation/` — Views, ViewModels, workers, and signal/slot UI orchestration.
- `Models/` — projects/sessions, camera, serial, media, and droplet-analysis algorithms.
- `Infrastructure/` — SQLite repositories, data paths, resource/window helpers, and crash handler.
- `ReSource/` — QSS, SVG, ICO, and splash screen.
- `__init__.py` — package marker.

## Core Algorithms & Implementation

- `FunctionWorker`, specialized workers, and Qt queued signals move blocking tasks off the UI thread.
- Camera, recorder, filesystem scanner, and editor components use cooperative shutdown; `finished` is paired with `deleteLater()` for correct lifecycle cleanup.
- SideBar scans `Image/Video` content with a bounded background-scanner queue; branch indicators reflect real content without requiring a click to trigger lazy loading. The 3 px top shimmer uses a gradient animation adapted to dock width, repaints only while restoring/opening Projects, scanning media, or loading editors, and stops completely when idle/hidden.
- Video Editor uses lazy playback: opening or restoring a video tab stores only the path and builds UI in Pause state; `QMediaPlayer.setSource()` is not called, so no decoder is allocated. The source loads only after the user presses Play.
- MainView removes duplicate tabs by normalized full path before creating media editors and coordinates a single-active-video policy: when one video plays, other Video Editors pause and release their source/decoder while retaining resume position. This prevents decoder bursts during restore or rapid double-clicks on heavy MP4 files.
- SideBar supports drag-and-drop ordering for Projects and Items: internal MIME identifies the node kind, Projects can move only at root level, Items can move only within the same Project, and path-stable order is saved in the session.
- Droplet Auto Detect uses the baseline as a geometric constraint: it masks substrate/reflection, trims low-clearance contour tails, checks the two baseline anchors as contact hints, and samples the liquid-cap arc uniformly by arc length.
- Droplet Measure Point supports drag-select with a selection rectangle: selected points render black, the right-click menu shows `Delete` only for a valid selection, and deletion uses selected indices before rebuilding the overlay.
- `WindowOwnershipHelper` normalizes secondary-window policy: `MainView` is the logical owner/coordinator, secondary windows do not use a native transient parent, and Win32 `WS_EX_APPWINDOW` keeps separate thumbnails in the same taskbar group. Runtime and installer shortcuts share AppUserModelID `TNH.Optima`.
- File Editor and Droplet Analysis are independent top-level windows registered with MainView; the Analysis window uses `WA_DeleteOnClose` to release closed instances. ImageEditor passes the source path separately from ownership so analysis results still save to the correct Item.
- OpenCV, NumPy, Matplotlib, and heavy editors are imported only when their feature is opened.
- Text files are written atomically; SQLite uses context managers; paths and resource names are validated before destructive operations.
- New Projects that have not been `Save As` use a default path determined for the current Windows user: `PathHelper.user_documents_path()` calls `SHGetKnownFolderPath(FOLDERID_Documents)`, then appends `TNH Optima Projects/<ProjectName>`. On typical Windows configurations this resolves to `C:\Users\<WindowsUser>\Documents\TNH Optima Projects\<ProjectName>`; if Windows, domain policy, or OneDrive has moved Documents, the API returns the same Documents location Explorer uses. When the Windows API is unavailable, the algorithm falls back to `%USERPROFILE%\Documents` and then `Path.home()/Documents`. `ProjectManager` creates the root folder if needed, writes `config.json`, and keeps Project state as `TEMP` until `Save As`.
- `CrashHandler` writes rotating logs, installs exception hooks for main/background threads, and enables `faulthandler`.

## Data Flow

1. `main.py` installs the crash handler, creates the Qt shell, and lazy-loads `MainViewModel`/`MainView`.
2. View emits an event -> ViewModel validates input -> Model or worker performs the domain operation.
3. Worker returns results to the UI thread by signal.
4. Successful capture/record emits `media_created` -> SideBar updates immediately; `QFileSystemWatcher` still synchronizes external changes.
5. Background media scans update cache and `ChildIndicatorPolicy`; when the user expands a node, the cached list renders immediately.
6. Double-click/restore MP4 -> create a Pause tab without source -> user presses Play -> pause and release other video decoders -> lazy `setSource()` for the current video -> resume playback from the stored position.
7. Hold left mouse on Project/Item -> drag to a valid position -> tree moves the existing node -> on close save `sidebar_order` -> restore worker rebuilds the same order.
8. In Droplet Analysis, baseline coefficients/anchors + image go through a worker -> liquid-cap contour + contact endpoints -> ellipse/circle fit -> overlay and contact angles.
9. In Measure Point mode, click empty space to add a point, drag empty space to create a selection rectangle, right-click selection -> `Delete` -> rebuild the overlay from remaining points.
10. Startup sets process AppUserModelID -> open File Editor/Droplet Analysis -> register with MainView -> apply taskbar style -> Windows groups thumbnails under one TNH Optima icon.
11. MainView minimized -> actively minimizes registered secondary windows; restoring MainView restores only MainView -> selecting a secondary thumbnail restores/activates that specific window.
12. On close, editors wait for worker completion by signal, then release camera, serial, multimedia, Matplotlib, and save session.
13. Create Project without `specific_path` -> get Documents through the Windows Known Folder API -> safe fallback if needed -> create `TNH Optima Projects/<ProjectName>/config.json` -> register the current path as `TEMP`; `Save As` later copies the Project to the user-selected location and switches state to `SAVED`.
