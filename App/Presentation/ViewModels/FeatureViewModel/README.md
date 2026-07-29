# App / Presentation / ViewModels / FeatureViewModel

## Project Overview

State and logic for ImageEditor, FileEditor camera/media, and DropletAnalysis.

## Annotated Directory Structure

- `ImageEditorViewModel.py` — asynchronous image decode/save and worker lifecycle.
- `VideoEditorViewModel.py` — video-source validation, captured-image writing, and worker lifecycle management.
- `FileEditorViewModel.py` — camera frames, motor queue, capture/record, storage target, and media notifications.
- `SidebarViewModel.py` — concurrency-limited media-scan queue, duplicate-refresh coalescing, and asynchronous shutdown.
- `DropletAnalysisViewModel.py` — QImage->NumPy, normalization, baseline, edge detection, fitting, downsampling, and background export.
- `__init__.py` — package marker.

## Core Algorithms & Implementation

- Motor commands are queued; emergency stop has high priority.
- Image capture and video stop run in `FunctionWorker`.
- `media_created(project, item, type, full_path)` emits only after the file has been written successfully.
- The storage target cannot change while recording.
- ViewModels track workers, emit `close_ready` after all tasks finish, and avoid destroying running QThreads.

## Data Flow

1. `FileEditor` emits capture/record/motor events.
2. `FileEditorViewModel` calls managers inside workers.
3. Successful media work -> `media_created` -> `ProjectSidebar.notify_media_created`.
4. Image worker returns `QImage` -> View creates `QPixmap` and renders with Qt; Droplet worker returns presentation data -> View draws a Matplotlib overlay.
5. Video Play -> `VideoEditorViewModel` validates the source in a worker -> View initializes Qt Multimedia on demand.
6. Sidebar watcher -> `SidebarViewModel` background scan -> View renders in batches.
7. Close request -> cooperative interruption/stop -> `close_ready`.
