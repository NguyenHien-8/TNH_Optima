# App / ReSource / Icon / MenuControl Icons

## Project Overview

SVG files for Control actions.

## Annotated Directory Structure

- `control_panel.svg` — open standalone FileEditor.
- `filter.svg` — open Motor Control dialog.

## Core Algorithms & Implementation

- SVG files are static vector data; Qt handles rasterization by DPI/size.
- Assets are resolved through feature-relative paths and have fallbacks when missing.

## Data Flow

1. MenuControl resolve path.
2. Create `QAction` with an icon.
3. Action calls MainView/dialog.

