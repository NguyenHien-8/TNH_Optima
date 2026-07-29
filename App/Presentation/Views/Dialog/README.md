# App / Presentation / Views / Dialog

## Project Overview

QDialogs for camera/hardware configuration, motor control, and save/delete confirmation.

## Annotated Directory Structure

- `ConfigCameraDialog.py` — camera list, preview, and apply/revert.
- `ConfigHardwareDialog.py` — port scanning, baud/query period, and connect.
- `MotorControlDialog.py` — up/down/stop command queue.
- `DeleteResourcesDialog.py` — choose workspace removal or disk deletion.
- `SaveResourcesDialog.py` — Save/Don't Save/Cancel.
- `__init__.py` — package marker.

## Core Algorithms & Implementation

- Hardware port scan and connect run in `FunctionWorker`; buttons are disabled during the operation.
- Motor commands run sequentially in a worker; Stop is moved to the front of the queue.
- Dialogs reject close while related workers are still active to avoid premature QThread destruction.
- Camera preview uses the asynchronous lifecycle of `CameraManager`.
- Confirmation dialogs return only a decision and do not perform destructive work themselves.

## Data Flow

1. Menu/MainView lazy-imports and opens the dialog with the appropriate manager.
2. The dialog validates input and hands blocking work to a worker.
3. Worker results update UI on the main thread.
4. Accept/reject returns coordination to MainView/ViewModel.
