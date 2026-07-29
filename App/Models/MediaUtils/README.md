# App / Models / MediaUtils

## Project Overview

Per-Item media services: save camera frames as PNG and record streams as MP4 without blocking the UI.

## Annotated Directory Structure

- `MediaManager.py` — unified image/video facade.
- `ImageCaptureManager.py` — creates `Image/` and saves lossless `QImage` files.
- `VideoRecorderManager.py` — state machine and recorder thread for `Video/`.
- `__init__.py` — package marker.

## Core Algorithms & Implementation

- Files use microsecond timestamps to avoid overwrite during rapid captures.
- The video state machine contains `IDLE`, `RECORDING`, and `PAUSED`.
- `VideoRecorderThread` uses `deque(maxlen=5)`, a mutex, and a wait condition; stale frames are dropped when the encoder falls behind.
- OpenCV/NumPy are imported inside the recorder thread; `VideoWriter` is always released in `finally`.
- Closing an editor only requests recorder stop; the wrapper thread is kept alive until `finished`.

## Data Flow

1. The camera dispatcher sends `QImage` frames to `FileEditorViewModel`.
2. Capture runs `QImage.save()` in a worker -> returns filename -> emits `media_created(Image)`.
3. Record copies frames into the queue -> recorder writes MP4 -> Stop runs in a worker and releases the writer.
4. A successful Stop returns filename -> emits `media_created(Video)` -> SideBar shows the file immediately.
