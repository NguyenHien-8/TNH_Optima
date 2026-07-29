# App / Infrastructure / Persistence

## Project Overview

This directory keeps only the package marker and contains no runtime database.
Databases in this directory are not migrated or packaged, which prevents test
data from being included in the installer.

## Annotated Directory Structure

- `__init__.py` — package marker.

## Core Algorithms & Implementation

- `StoragePath.persistent_database_path()` only computes the per-user path; it does not touch disk on the GUI thread.
- Repositories create folders and schemas lazily on the first I/O operation.
- Source and the PyInstaller executable use two different data namespaces.
- `TNH_Optima.spec` and `installer.iss` exclude `ConfigStorage.db` and
  `SessionData.db`, including SQLite sidecar files.
- `installer.iss` removes the two Production databases from Local App Data on
  uninstall; Development databases and logs are retained.
- A clean install removes database state left by an old uninstaller, while an
  in-place upgrade preserves the current session/config.
- Schemas and transactions are still managed by `ConfigRepository`/`SessionRepository`.
- Do not add new runtime databases to the source tree or installer.

## Data Flow

1. A repository requests the runtime database path.
2. `StoragePath` selects the Development area when running from source and the Production area when frozen.
3. SQLite creates an empty schema when the database does not exist.
4. Later reads/writes use the corresponding per-user database.
