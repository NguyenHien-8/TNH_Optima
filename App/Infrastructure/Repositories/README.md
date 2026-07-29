# App / Infrastructure / Repositories

## Project Overview

Repositories isolate SQLite from ViewModels and provide key-value persistence for application configuration and session state.

## Annotated Directory Structure

- `ConfigRepository.py` — camera index and hardware configuration.
- `SessionRepository.py` — projects, opened items/editors, and expanded paths as JSON.
- `StoragePath.py` — per-user database paths, separated into Development and Production.
- `__init__.py` — package marker.

## Core Algorithms & Implementation

- Each operation uses its own connection with a finite timeout.
- Folders and schemas are created lazily on the first read/write, so constructors do not block UI startup.
- Context managers guarantee commit on success, rollback on error, and handle closure.
- Empty keys are rejected; JSON is Unicode-encoded; numeric configuration values have safe fallbacks.
- `save_hardware_config` writes related fields in a single transaction.

## Data Flow

1. When running from source, repositories use `%LOCALAPPDATA%/TNH Optima Development/Data`.
2. When running the PyInstaller executable, repositories use `%LOCALAPPDATA%/TNH Optima/Data`.
3. Legacy databases in the source tree or bundle are not copied into Production.
4. ViewModel/SessionManager calls repository APIs.
5. SQLite returns plain data; parsing and fallback happen before data enters managers.
