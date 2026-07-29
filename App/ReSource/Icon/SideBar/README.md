# App / ReSource / Icon / SideBar Icons

## Project Overview

SVG files for media nodes and expand/collapse arrows in the project tree.

## Annotated Directory Structure

- `image_file.svg`, `video_file.svg`, `file_tnh.svg` — node types.
- `arrow_down.svg`, `arrow_next.svg` — expanded/collapsed states.

## Core Algorithms & Implementation

- SVG files are static vector data; Qt handles rasterization by DPI/size.
- Assets are resolved through feature-relative paths and have fallbacks when missing.

## Data Flow

1. Sidebar loads icons during initialization.
2. Filesystem data creates nodes with the correct icon.
3. The tree paints disclosure arrows based on expanded state.

