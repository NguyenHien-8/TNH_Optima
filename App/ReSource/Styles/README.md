# App / ReSource / Styles

## Project Overview

QSS stylesheets separate presentation styling from Python logic.

## Annotated Directory Structure

- `MainViewStyles.qss`, `MenuBarStyles.qss`, `EditorWorkspaceStyles.qss` — main shell.
- `FileEditorStyles.qss`, `ImageEditorStyles.qss`, `VideoEditorStyles.qss`, `DropletAnalysisStyles.qss` — editors and analysis window.
- `CameraDialogStyles.qss`, `HardwareDialogStyles.qss`, `MotorControlDialog.qss`, `DelSaveDialogStyles.qss` — dialogs.
- `__init__.py` — package marker.

## Core Algorithms & Implementation

- Qt selectors rely on widget class, objectName, and dynamic properties.
- Each View calls `apply_stylesheet()` to load UTF-8 through the resource path; missing files only warn and use default styling.

## Data Flow

1. Widget initializes -> resolves QSS path -> reads text -> `setStyleSheet()`.
2. Dynamic properties, such as preview state, are repolished to update the UI.
