# App / ReSource / Icon / Media Icons

## Project Overview

SVG set used in image/video/camera editors.

## Annotated Directory Structure

- Open/capture/analysis icons for images.
- Play/pause/stop/skip icons for video.
- Photo/video camera icons for live capture and recording.

## Core Algorithms & Implementation

- SVG files are static vector data; Qt handles rasterization by DPI/size.
- Assets are resolved through feature-relative paths and have fallbacks when missing.

## Data Flow

1. Editors initialize icon paths.
2. QPushButton receives `QIcon`.
3. Click signals enter the ViewModel/media pipeline.

