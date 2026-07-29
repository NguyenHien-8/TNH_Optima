# App / ReSource / Icon / MenuFile Icons

## Project Overview

SVG files for Project/Item and application lifecycle actions.

## Annotated Directory Structure

- New/open/save/delete/rename-related assets.
- `restart.svg` and `exit.svg` for process lifecycle.

## Core Algorithms & Implementation

- SVG files are static vector data; Qt handles rasterization by DPI/size.
- Assets are resolved through feature-relative paths and have fallbacks when missing.

## Data Flow

1. MenuFile creates `QAction`.
2. Action displays icon and shortcut.
3. MainView/ViewModel performs the domain operation.

