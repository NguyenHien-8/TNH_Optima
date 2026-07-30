# App / Presentation / Views / Widgets

## Project Overview

Reusable widgets for the project tree, editor tabs, status display, and droplet analysis.

## Annotated Directory Structure

- `SideBar.py` — Project/Item/Image/Video tree, drag-drop reordering, explicit media updates, and filesystem watcher.
- `EditorWorkspace.py` — tab container, drag/drop, and close contract.
- `DropletAnalysisWindow.py` — point interaction, drag-select Measure Point, fitting, overlay, and export.
- `StatusBar.py` — camera/serial status.
- `FileEditorWorkspace/` — camera, image/video editors, and control widgets.
- `MenuBar/` — menu actions, shortcuts, and sidebar toggle.

## Core Algorithms & Implementation

- SideBar lazy-scans media in workers and inserts results in batches of 200 items.
- At most two media scanners run concurrently; remaining requests stay queued so large projects do not create too many `QThread` instances.
- `Image/Video` nodes are scanned in the background as soon as an Item appears: nodes with media use `ShowIndicator`, empty nodes use `DontShowIndicatorWhenChildless`.
- The custom branch renderer considers both loaded children and `ChildIndicatorPolicy`, so arrows appear before the first click.
- `notify_media_created` validates the full path, prevents duplicates, inserts in order, and expands the correct Project/Item/Image|Video node.
- If the watcher reports changes while a scanner is running, the refresh is added to a pending set and rerun after `finished`.
- The watcher still handles file creation/deletion from external applications.
- Internal drag-and-drop uses MIME `application/x-tnh-optima-sidebar-node`; Projects reorder only at top level, Items reorder only within the same Project. Drops into another Project or onto wrong-level Image/Video/file nodes are rejected to avoid accidental filesystem changes.
- Reorder uses `takeTopLevelItem`/`takeChild` and reinserts the same object, so selection, expanded state, media cache, and watcher do not need to be rebuilt.
- Widgets with workers emit `close_ready` to avoid deleting a running QThread.
- Droplet Auto Detect requires the user to define a baseline before running. The worker passes immutable copies of coefficients and two baseline anchors into the model to isolate substrate/reflection, bound the search region, reject top-connected needles, require two-sided baseline contact, and keep only the droplet-edge arc above the baseline.
- The two baseline points define a line segment and are not assumed to be droplet contacts. They pin a contact endpoint only when already close to the detected interface; otherwise the model extrapolates the contact from the local side.
- A permissive adaptive mask localizes the complete outer rim without Otsu shrinkage. Its baseline-segment ROI includes a generous margin so droplets above 90° retain their physical overhang. Outward-normal gradient search on the source image then moves the contour to the strongest dark-to-light optical interface with subpixel interpolation.
- Persistent contrast is measured across a deeper band on both sides of the refined contour. The trusted run containing the apex has a thick dark interior and bright exterior; thin arrows, text, and substrate branches do not, so they are pruned before a short contact bridge is refined and baseline tails are trimmed again.
- Returned edge points are sampled uniformly by refined arc length; the UI updates the overlay only after the worker completes and reports proactively when no baseline exists or no valid edge is found.
- `Save Analysis Results` opens Save As at the last successful directory,
  captures the GUI-owned Matplotlib canvas, and crops original-image exports
  to the active axes rectangle before handing the immutable `QImage` and
  selected path to the save worker. The directory is persisted in SQLite only
  after the PNG write succeeds; saved images contain the 5 x 3 image/overlay
  region without baked figure padding and fill ImageEditor's matching
  viewport.
- Measure Point selection separates click and drag with a small pixel threshold: clicking empty space adds a point, dragging empty space draws a rectangle, and points inside the rectangle render black and are stored in `selected_measurement_indices`.
- The right-click context menu in Measure Point opens only with a valid selection; `Delete` removes the selected indices, clears rectangle/selection, and rerenders remaining points. The `Delete Measure Point` button still deletes all points when there is no selection.
- `Config Label` is a non-modal toggle available after droplet analysis. It supports free two-axis dragging for angle labels, vertically controlled tangent-aligned arrow length, and live controls for angle font size, baseline line width, and arrow line width. All three sizes persist through `QSettings`; the matching angle arc and baseline guide resize with arrow length, configuration handles are excluded from saved images, and the compact reset-icon restores only label/arrow geometry without overwriting saved sizes.
- `DropletAnalysisWindow` is an independent top-level window: MainView is only the logical owner used for minimize coordination, while Win32 taskbar style lets Windows create a separate thumbnail in the same TNH Optima group instead of a minimized desktop caption.
- `WA_DeleteOnClose` ensures hidden analysis objects are not retained; the
  source image path remains available for the suggested export filename
  without coupling result storage to QObject ownership.

## Data Flow

1. Project signals create Item -> enqueue background scans for `Image` and `Video`.
2. Scan result -> cache filenames + update branch indicator, without creating children while the node is closed.
3. Click to expand node -> render from cache immediately; large lists are inserted in batches.
4. Successful capture/record -> explicit `media_created` -> update SideBar immediately.
5. External filesystem change -> watcher -> background rescan -> indicator/tree update.
6. Drag Project/Item -> validate node kind + parent boundary -> compute before/after index -> move the existing tree item.
7. Double click/drag-drop file -> MainView opens the matching editor.
8. Droplet baseline coefficients + anchors -> Auto Detect worker -> liquid-cap contour + validated contacts -> valid edge points -> UI thread draws overlay.
9. Measure Point drag-select -> selected indices -> right-click `Delete` -> remove selected points -> redraw measurement overlay.
10. Config Label -> drag labels or vertically control tangent-aligned arrow length -> synchronize the arc/guide -> persist the adjusted overlay after exiting configuration.
11. ImageEditor opens Droplet Analysis -> passes source path + MainView logical owner -> helper registers window/taskbar style -> grouped preview; close emits `destroyed` to remove it from the window list.
