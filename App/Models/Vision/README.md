# App / Models / Vision

## Project Overview

Manages physical cameras, device scanning, and frame routing to the active feature.

## Annotated Directory Structure

- `CameraManager.py` — camera state machine, reference count, retry timer, and lifecycle.
- `CameraThread.py` — opens/captures/releases OpenCV cameras outside the UI thread.
- `HardwareCameraScan.py` — scans camera names/indices in a worker.
- `CameraFrameDispatcher.py` — routes frames to a valid ViewModel.
- `__init__.py` — package marker.

## Core Algorithms & Implementation

- Cameras are not scanned or connected in constructors; I/O starts only after first paint or when a feature acquires the camera.
- Camera switching uses a pending target and the `finished` signal; it does not call wait on the UI thread.
- Retry uses a cancellable single-shot `QTimer`.
- Threads check interruption, release `VideoCapture` in `finally`, and import OpenCV only in `run()`.
- The dispatcher checks for callable `receive_frame`; failing targets are disabled safely.

## Data Flow

1. Config/features request camera scan, preview, or acquisition.
2. `CameraManager` creates workers and receives `QImage` frames through queued signals.
3. `CameraFrameDispatcher` routes frames to `FileEditorViewModel`.
4. The ViewModel emits preview frames, captures stills, or sends frames to the video recorder.
