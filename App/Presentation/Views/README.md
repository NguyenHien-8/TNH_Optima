# App / Presentation / Views

## Project Overview

Main window and high-level UI components responsible for assembling ViewModels, Sidebar, menus, dialogs, and editors.

## Annotated Directory Structure

- `MainView.py` — application shell, signal wiring, restore, and coordinated shutdown.
- `MenuBar.py` — high-level menu assembly.
- `Dialog/` — camera/hardware configuration and confirmation dialogs.
- `Widgets/` — Sidebar, workspace, editors, status, and analysis window.
- `__init__.py` — package marker.

## Core Algorithms & Implementation

- `camera_dispatcher` is initialized before any deferred callbacks and accepts only targets with `receive_frame`.
- Image/video editors are lazy-imported by extension.
- Large text is inserted into the editor in chunks through `QTimer`.
- SideBar initializes branch indicators from background scan results and does not require a user click before detecting media.
- MainView defers close when editors or workers are not yet safe, then continues automatically by signal.
- File Editor and Droplet Analysis use MainView as the logical owner while keeping independent native windows; the helper registers windows and synchronizes taskbar thumbnail policy before first show and whenever the native handle is shown again.

## Data Flow

1. `MainViewModel` emits project/item/file/session signals.
2. MainView connects signals to Sidebar and EditorWorkspace.
3. FileEditor/VideoEditor emits `media_created`; MainView connects this signal directly to Sidebar.
4. Sidebar selection changes FileEditor's storage target.
5. Open secondary window -> register with MainView + shared AppUserModelID/taskbar style -> grouped preview; MainView minimize also minimizes secondary windows, but restore opens only MainView.
6. Close event collects editor/expanded paths, then cleans up and saves the session.
