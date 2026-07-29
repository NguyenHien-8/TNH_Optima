# App / Presentation / Views / Widgets / FileEditorWorkspace

## Project Overview

Editors and control widgets for live camera, still images, saved videos, and motor control.

## Annotated Directory Structure

- `FileEditor.py` — camera preview with motor/media controls.
- `MotorControlEditor.py` — height/speed input and command emission.
- `MediaControlEditor.py` — capture/record/pause/resume/stop state.
- `ImageEditor.py` — lazy-load image tabs, receive `QImage`, create `QPixmap`, save, and open droplet analysis.
- `ImageCanvas.py` — lightweight `QPainter` viewport with 5 x 3 mm axes and zoom/pan without NumPy/Matplotlib.
- `VideoEditor.py` — lazily initialized multimedia stack, timeline, playback rate, and frame capture.

## Core Algorithms & Implementation

- FileEditor emits only UI events; `FileEditorViewModel` owns the media/control workflow.
- ImageEditor and VideoEditor track save/decode workers; close is deferred until `finished`.
- ImageEditor clears the Qt canvas and closes child analysis windows.
- VideoEditor creates `QMediaPlayer`/`QVideoWidget` only after the source is validated by the ViewModel; on close, it disconnects the video sink, clears the media source, and clears the frame.
- Captures from live camera or VideoEditor both emit explicit media notifications; files created externally are still synchronized by the watcher.
- Droplet Auto Detect is enabled only after a baseline exists; segmentation, substrate-tail filtering, contact-endpoint restoration, and point sampling run in an analysis worker so the UI thread is not blocked.
- ImageEditor resolves the top-level MainView as the logical owner of Droplet Analysis and passes `full_path` separately as save context. MainView actively coordinates minimize while the native window keeps independent restore state; Win32 taskbar style creates grouped thumbnails; closing the window deletes the object and clears references through the `destroyed` signal.

## Data Flow

1. Camera dispatcher → `FileEditorViewModel` → `FileEditor` preview.
2. Capture → background PNG save → `media_created(Image)` → SideBar.
3. Record frames → recorder queue → MP4 finalize → `media_created(Video)` → SideBar.
4. VideoEditor capture frame → background PNG save → `media_created(Image)` → SideBar.
5. Sidebar image/video file → MainView → ImageEditor/VideoEditor.
6. ImageEditor -> DropletAnalysisWindow -> baseline coefficients/anchors + image -> analysis worker -> liquid-cap points plus two contact endpoints -> rendered result.
7. DropletAnalysisWindow show -> register with MainView + grouped taskbar thumbnail -> MainView minimize pulls the window down, while clicking that thumbnail restores only that window.
