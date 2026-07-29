# App / ReSource / Icon / DropletAnalysisWindow Icons

## Project Overview

SVG set for tools in the contact-angle measurement window.

## Annotated Directory Structure

- `actualsize.svg` — reset zoom.
- `baseline.svg` — select baseline.
- `autodetectedge.svg` — automatically detect edges.
- `point.svg` — add/manage measurement points.

## Core Algorithms & Implementation

- SVG files are static vector data; Qt handles rasterization by DPI/size.
- Assets are resolved through feature-relative paths and have fallbacks when missing.

## Data Flow

1. Toolbar creates `QIcon` objects from SVG files.
2. User clicks an action -> DropletAnalysisWindow updates interaction state.
3. Results are drawn with Matplotlib; assets are not modified.

