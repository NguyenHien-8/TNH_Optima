# App / Presentation / Views / Widgets / FileEditorWorkspace

## Project Overview

Các editor và control widget cho camera live, ảnh tĩnh, video đã lưu và điều khiển motor.

## Annotated Directory Structure

- `FileEditor.py` — camera preview cùng motor/media controls.
- `MotorControlEditor.py` — nhập height/speed và phát command.
- `MediaControlEditor.py` — capture/record/pause/resume/stop state.
- `ImageEditor.py` — lazy-load tab ảnh, nhận `QImage`, tạo `QPixmap`, save và mở droplet analysis.
- `ImageCanvas.py` — viewport `QPainter` nhẹ với trục 5 × 3 mm, zoom/pan không qua NumPy/Matplotlib.
- `VideoEditor.py` — multimedia stack khởi tạo lười, timeline, playback rate và capture frame.

## Core Algorithms & Implementation

- FileEditor chỉ phát UI event; `FileEditorViewModel` sở hữu media/control workflow.
- ImageEditor và VideoEditor theo dõi worker save/decode; close được hoãn đến `finished`.
- ImageEditor clear Qt canvas và đóng analysis windows con.
- VideoEditor chỉ tạo `QMediaPlayer`/`QVideoWidget` sau khi source được ViewModel xác thực; khi đóng, editor disconnect video sink, bỏ media source và clear frame.
- Capture từ live camera hoặc VideoEditor đều phát explicit media notification; file tạo từ nguồn ngoài vẫn do watcher đồng bộ.
- Droplet Auto Detect chỉ được kích hoạt sau khi có baseline; phân đoạn, lọc substrate tails, khôi phục contact endpoints và lấy mẫu điểm chạy trong analysis worker nên không chặn UI thread.
- ImageEditor resolve top-level MainView làm logical owner của Droplet Analysis và truyền `full_path` riêng làm save context. MainView chủ động điều phối minimize trong khi native window giữ trạng thái restore độc lập; Win32 taskbar style tạo thumbnail theo nhóm; đóng window xóa object và gỡ tham chiếu bằng signal `destroyed`.

## Data Flow

1. Camera dispatcher → `FileEditorViewModel` → `FileEditor` preview.
2. Capture → background PNG save → `media_created(Image)` → SideBar.
3. Record frames → recorder queue → MP4 finalize → `media_created(Video)` → SideBar.
4. VideoEditor capture frame → background PNG save → `media_created(Image)` → SideBar.
5. Sidebar image/video file → MainView → ImageEditor/VideoEditor.
6. ImageEditor → DropletAnalysisWindow → baseline coefficients/anchors + image → analysis worker → liquid-cap points cùng hai contact endpoints → rendered result.
7. DropletAnalysisWindow show → đăng ký với MainView + grouped taskbar thumbnail → MainView minimize kéo window xuống, còn click thumbnail mới restore riêng window đó.
