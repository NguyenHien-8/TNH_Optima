# App / Presentation / Views / Widgets / MenuBar

## Project Overview

Main-window menus/actions, including shortcuts, icons, and calls into MainView's public API.

## Annotated Directory Structure

- `MenuFile.py` — Project/Item lifecycle, restart, and exit.
- `MenuSetup.py` — camera/hardware configuration.
- `MenuControl.py` — motor dialog and FileEditor control.
- `KeyboardShortcut.py` — shortcut constants.
- `ToggleSideBar.py` — sidebar action/icon.
- `MenuCalibration.py`, `MenuTool.py`, `MenuWindow.py`, `MenuHelp.py` — extension menus.
- `__init__.py` — package marker.

## Core Algorithms & Implementation

- Action helpers normalize `QAction`, icons, and `QKeySequence`.
- Heavy Config/Motor/FileEditor modules are imported in action handlers, not on the startup path.
- Menus only call MainView or open dialogs; domain work and I/O still go through ViewModels/workers.
- Restart uses Qt process APIs after requesting application quit.

## Data Flow

1. User selects a menu item or shortcut.
2. The action calls a MainView method.
3. MainView lazy-loads a dialog/feature if needed.
4. Dialog/ViewModel performs the domain operation and returns results by signal.
