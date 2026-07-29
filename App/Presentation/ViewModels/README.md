# App / Presentation / ViewModels

## Project Overview

ViewModels connect Views to Models, manage workers, and emit UI signals with complete context.

## Annotated Directory Structure

- `MainViewModel.py` — composition root, project/file commands, session, camera, and hardware.
- `Workers.py` — callable worker, session restore, file loader, and media/file operations.
- `FeatureViewModel/` — image, file-camera/media, and droplet analysis.
- `DialogViewModel/` — adapters for configuration/confirmation dialogs.
- `__init__.py` — package marker.

## Core Algorithms & Implementation

- Session restore, project CRUD, file load/save, serial connect, and heavy tasks run in the background.
- Text save uses a temporary file, flush/fsync, and `os.replace`.
- Workers are tracked, requested to interrupt on close, and `deleteLater()` is called after `finished`.
- Delayed timers have parents and are cancelled during shutdown.
- The file loader is capped at 20 MB and rejects binary/non-UTF-8 data.
- Session restore orders Projects by normalized path rank and Items by case-insensitive saved rank; new nodes or nodes missing metadata are placed after them in stable name order.

## Data Flow

1. The View calls a handler or feature method.
2. The ViewModel creates the worker and keeps ownership.
3. A result signal calls back on the UI thread and updates the View.
4. `FileEditorViewModel.media_created` carries project, item, media type, and full path to SideBar.
5. Shutdown completes only after related workers have stopped.
6. MainView snapshots `sidebar_order` -> MainViewModel filters existing Projects -> SessionManager saves -> SessionRestoreWorker returns Projects/Items in the saved order.
