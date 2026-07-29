# App / Presentation / ViewModels / DialogViewModel

## Project Overview

Small ViewModels for camera, hardware, motor, and Save/Delete decisions, keeping dialogs independent from domain implementations.

## Annotated Directory Structure

- `ConfigCameraViewModel.py` — scan/select/preview/apply/revert camera.
- `ConfigHardwareViewModel.py` — port scanning, config loading, and connection apply.
- `MotorControlViewModel.py` — converts up/down/stop actions and emits state.
- `DeleteResourcesViewModel.py` — dialog data and delete-on-disk flag.
- `SaveResourcesViewModel.py` — state `SAVE`, `DONT_SAVE`, `CANCEL`.
- `__init__.py` — package marker.

## Core Algorithms & Implementation

- Camera dialog applies changes transaction-like: keep original ID, preview the selection, persist on apply, or revert on cancel.
- Motor ViewModel emits state before/after synchronous commands.
- Save/Delete ViewModels only hold decision state and do not edit the filesystem directly.

## Data Flow

1. Dialog updates the ViewModel.
2. ViewModel calls a backend/manager or stores the selected decision.
3. Dialog accepts/rejects; MainView performs the corresponding destructive/save action.

