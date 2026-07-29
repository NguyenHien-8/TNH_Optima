# App / Models / Controllers

## Project Overview

The controller layer owns the single serial connection and exposes a thread-safe hardware API to the rest of the application.

## Annotated Directory Structure

- `HardwareConnector.py` — serial singleton, port scanning, connect/disconnect, and writes.
- `HardwareManager.py` — QObject facade, current configuration, and status signals.
- `__init__.py` — package marker.

## Core Algorithms & Implementation

- The singleton is protected by a lock; the serial handle is replaced/closed with clear ownership.
- Each connect request has a generation token: disconnect or a new connect cancels stale connect results.
- Retry applies only to port access errors and runs in a worker without holding the lock during sleep/open.
- Read/write timeouts are finite; port, baud, and payload are validated proactively.

## Data Flow

1. Dialog/MainViewModel sends connect or scan work into `FunctionWorker`.
2. `HardwareManager` calls `HardwareConnector`.
3. The connector returns `(success, message)` and the manager emits `connection_status_changed`.
4. Motor commands flow from ViewModel -> `ControlPanelManager` -> `HardwareManager` -> serial.
