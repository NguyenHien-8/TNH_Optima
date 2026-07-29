# App / ReSource / Icon

## Project Overview

Production icons are grouped by feature so menus/widgets load the correct assets.

## Annotated Directory Structure

- `app_icon.ico` — icon executable/window.
- `splash_screen.png` — splash startup.
- `Media/` — image/video/camera actions.
- `MenuFile/`, `MenuControl/` — menu actions.
- `DropletAnalysisWindow/` — measurement tools.
- `SideBar/` — file types and disclosure arrows.

## Core Algorithms & Implementation

- There is no runtime image processing beyond Qt scaling/drawing.
- Code always checks `os.path.exists`; when an icon is missing, some widgets use a standard icon or text fallback.

## Data Flow

1. View resolve feature icon directory.
2. `QIcon`/`QPixmap` loads SVG/PNG/ICO.
3. Qt renders to button, splash, or tree sizes.

