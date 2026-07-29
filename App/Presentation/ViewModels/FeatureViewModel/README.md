# App / Presentation / ViewModels / FeatureViewModel

## Project Overview

State và logic dành cho ImageEditor, FileEditor camera/media và DropletAnalysis.

## Annotated Directory Structure

- `ImageEditorViewModel.py` — decode/save ảnh bất đồng bộ và worker lifecycle.
- `VideoEditorViewModel.py` — kiểm tra source video, ghi ảnh capture và quản lý vòng đời worker.
- `FileEditorViewModel.py` — camera frame, motor queue, capture/record, storage target và media notification.
- `SidebarViewModel.py` — hàng đợi scan media giới hạn concurrency, gộp refresh trùng và shutdown bất đồng bộ.
- `DropletAnalysisViewModel.py` — QImage→NumPy, normalization, baseline, edge detection, fit, downsample và export nền.
- `__init__.py` — package marker.

## Core Algorithms & Implementation

- Motor command được xếp hàng; emergency stop có độ ưu tiên cao.
- Capture image và stop video chạy trong `FunctionWorker`.
- `media_created(project, item, type, full_path)` chỉ phát sau khi file đã ghi thành công.
- Storage target không được đổi khi đang record.
- ViewModel theo dõi worker, phát `close_ready` khi mọi tác vụ đã kết thúc và tránh hủy QThread đang chạy.

## Data Flow

1. `FileEditor` phát capture/record/motor event.
2. `FileEditorViewModel` gọi manager trong worker.
3. Media thành công → `media_created` → `ProjectSidebar.notify_media_created`.
4. Image worker trả `QImage` → View tạo `QPixmap` và render bằng Qt; Droplet worker trả dữ liệu trình bày → View vẽ Matplotlib overlay.
5. Video Play → `VideoEditorViewModel` kiểm tra source trong worker → View khởi tạo Qt Multimedia theo nhu cầu.
6. Sidebar watcher → `SidebarViewModel` scan nền → View render theo batch.
7. Close request → cooperative interruption/stop → `close_ready`.
