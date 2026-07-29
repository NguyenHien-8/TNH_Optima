# App / Models

## Project Overview

The domain layer manages projects/sessions, cameras, serial hardware, media, and geometry analysis. Models do not manipulate widgets directly.

## Annotated Directory Structure

- `Analysis/` — baseline, contour, circle/ellipse fitting, and contact-angle geometry.
- `Controllers/` — serial connector and hardware facade.
- `MediaUtils/` — PNG capture and MP4 recording.
- `Vision/` — camera scanning, capture thread, lifecycle, and frame dispatcher.
- `ProjectManager.py` — Project/Item/media CRUD with path validation.
- `SessionManager.py` — session-state snapshot/restore, including Project/Item order in the SideBar.
- `CamHardwareManager.py` — camera/hardware configuration backend.
- `ControlPanelManager.py` — motor-command validation and packet construction.

## Core Algorithms & Implementation

- A valid Project has a `config.json` marker; a valid Item has `Image/` and `Video/`.
- Filesystem operations are serialized with a model lock and run in workers.
- Camera/serial/media operations use a single owner, finite timeouts, and cooperative cancellation.
- Names/paths are normalized, checked for containment, and protected against `..` escapes or invalid characters.
- `sidebar_order` stores Project order by path and Item order per Project; the getter returns a deep copy and the setter filters invalid session data.

## Data Flow

1. A ViewModel sends a validated request into the Model.
2. The Model performs filesystem, device, or algorithm work in the appropriate worker.
3. Plain tuples/objects are returned to the ViewModel.
4. The ViewModel emits status, error, or resource-change signals to the View.
5. On close, SideBar snapshots order -> SessionManager saves JSON to SQLite; on restart, the restore worker applies saved ranks before emitting tree-build signals.
