# App / ReSource

## Project Overview

UI resources are bundled with the executable. The directory keeps its current casing because code paths reference `App/ReSource`.

## Annotated Directory Structure

- `Styles/` — QSS by widget/dialog.
- `Icon/` — ICO, PNG, and SVG by feature.
- `__init__.py` — package marker.

## Core Algorithms & Implementation

- There are no domain algorithms here; QSS is applied through `setStyleSheet`, icons through `QIcon`.
- `ResourceHelper.resource_path()` lets the same path work in source and `_MEIPASS`.
- `TNH_Optima.spec` bundles the whole `App`, so resources are available in builds.

## Data Flow

1. A View requests a relative resource.
2. ResourceHelper returns an absolute path.
3. Qt loads style/icon/splash when creating widgets.

