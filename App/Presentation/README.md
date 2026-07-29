# App / Presentation

## Project Overview

PyQt6 presentation layer organized around MVVM, responsible for widgets, signals/slots, worker orchestration, and UI lifecycle.

## Annotated Directory Structure

- `ViewModels/` — state, validation, workers, and adapters to Models.
- `Views/` — MainView, dialogs, workspace, sidebar, and feature widgets.
- `__init__.py` — package marker.

## Core Algorithms & Implementation

- Views do not perform filesystem, serial, or heavy analysis work directly.
- Worker results return to the UI through Qt queued signals.
- Heavy editors are imported at point of use to reduce startup cost.
- Close events can be deferred while workers are running; `close_ready` resumes the operation after resources are safe.

## Data Flow

1. User events start in the View.
2. The ViewModel validates and calls a Model/worker.
3. Result signals update widgets on the UI thread.
4. Capture/record emits explicit media events instead of relying only on filesystem watchers.
5. Shutdown collects session state, stops workers/devices, and releases widgets in order.
