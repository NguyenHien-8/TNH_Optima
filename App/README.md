# App

## Project Overview

`App` là package chính của VCA Optima Release 1.1.1. Mã nguồn được tổ chức theo hướng MVVM: giao diện PyQt6 ở `Presentation`, nghiệp vụ và thiết bị ở `Models`, lưu trữ và xử lý lỗi ở `Infrastructure`, còn tài nguyên đóng gói nằm trong `ReSource`.

Ứng dụng ưu tiên UI responsive: I/O, camera, serial, ghi media và phân tích ảnh chạy ngoài UI thread; các feature nặng được lazy import sau khi cửa sổ chính đã hiển thị.

## Annotated Directory Structure

- `Presentation/` — Views, ViewModels, worker và signal/slot điều phối UI.
- `Models/` — project/session, camera, serial, media và thuật toán phân tích giọt.
- `Infrastructure/` — SQLite repositories, đường dẫn dữ liệu, resource/window helper và crash handler.
- `ReSource/` — QSS, SVG, ICO và splash screen.
- `__init__.py` — package marker.

## Core Algorithms & Implementation

- `FunctionWorker`, các worker chuyên biệt và Qt queued signals đưa tác vụ blocking ra khỏi UI thread.
- Camera, recorder, filesystem scanner và editor sử dụng cooperative shutdown; `finished` kết hợp `deleteLater()` để giải phóng đúng vòng đời.
- SideBar dò nội dung `Image/Video` bằng hàng đợi scanner nền giới hạn đồng thời; branch indicator phản ánh nội dung thật mà không cần click để kích hoạt lazy load. Thanh shimmer 3px ở mép trên dùng gradient animation thích ứng chiều rộng dock, chỉ repaint khi restore/mở Project, scan media hoặc editor đang load và dừng hoàn toàn khi idle/hidden.
- Video Editor dùng lazy playback: mở hoặc restore tab video chỉ lưu đường dẫn và dựng UI ở trạng thái Pause, chưa gọi `QMediaPlayer.setSource()` nên chưa cấp phát decoder. Source chỉ được nạp sau thao tác Play của người dùng.
- MainView loại bỏ tab trùng theo normalized full path trước khi tạo media editor và điều phối single-active-video: khi một video được Play, các Video Editor khác pause rồi giải phóng source/decoder nhưng giữ vị trí resume. Cơ chế này chặn burst decoder khi restore hoặc double-click nhiều MP4 nặng.
- SideBar hỗ trợ kéo-thả sắp xếp Project và Item: MIME nội bộ phân loại node, chỉ cho phép Project đổi vị trí ở root và Item đổi vị trí trong cùng Project; thứ tự path-stable được lưu trong session.
- Droplet Auto Detect dùng baseline làm ràng buộc hình học: mask bỏ substrate/reflection, cắt contour tails có clearance thấp, kiểm tra hai baseline anchors làm contact hints và lấy mẫu liquid-cap arc đều theo arc length.
- Droplet Measure Point hỗ trợ drag-select bằng selection rectangle: point được chọn được render màu đen, menu chuột phải chỉ hiện `Delete` khi có selection hợp lệ, và xóa theo index đã chọn trước khi dựng lại overlay.
- `WindowOwnershipHelper` chuẩn hóa secondary-window policy: `MainView` là logical owner/điều phối viên nhưng cửa sổ phụ không dùng native transient parent, còn Win32 `WS_EX_APPWINDOW` giữ thumbnail riêng trong cùng nhóm taskbar. Runtime và shortcut installer dùng chung AppUserModelID `TNH.Optima`.
- File Editor và Droplet Analysis là các top-level window độc lập được đăng ký với MainView; Analysis window có `WA_DeleteOnClose` để giải phóng instance đã đóng. ImageEditor truyền source path tách biệt với owner nên lưu kết quả phân tích vẫn đúng Item.
- OpenCV, NumPy, Matplotlib và các editor nặng chỉ được import khi feature tương ứng được mở.
- File text được ghi nguyên tử; SQLite dùng context manager; đường dẫn và tên tài nguyên được kiểm tra trước thao tác phá hủy.
- `CrashHandler` ghi rotating log, cài exception hook cho main/background thread và bật `faulthandler`.

## Data Flow

1. `main.py` cài crash handler, tạo Qt shell và lazy-load `MainViewModel`/`MainView`.
2. View phát sự kiện → ViewModel kiểm tra đầu vào → Model hoặc worker thực hiện nghiệp vụ.
3. Worker trả kết quả bằng signal về UI thread.
4. Capture/record thành công phát `media_created` → SideBar cập nhật ngay; `QFileSystemWatcher` vẫn đồng bộ thay đổi từ bên ngoài.
5. Media scan nền cập nhật cache và `ChildIndicatorPolicy`; khi người dùng mở node, danh sách cache được render ngay.
6. Double-click/restore MP4 → tạo tab Pause không source → user Play → pause và release decoder của video khác → lazy `setSource()` cho video hiện tại → phát từ vị trí resume.
7. Giữ chuột trái Project/Item → kéo tới vị trí hợp lệ → tree di chuyển nguyên node → khi đóng lưu `sidebar_order` → restore worker dựng lại đúng thứ tự.
8. Trong Droplet Analysis, baseline coefficients/anchors + image đi qua worker → liquid-cap contour + contact endpoints → ellipse/circle fit → overlay và contact angles.
9. Trong chế độ Measure Point, click vùng trống thêm point, drag vùng trống tạo selection rectangle, chuột phải selection → `Delete` → rebuild overlay từ danh sách point còn lại.
10. Startup đặt process AppUserModelID → mở File Editor/Droplet Analysis → đăng ký với MainView → áp dụng taskbar style → Windows gom thumbnail dưới một biểu tượng TNH Optima.
11. MainView chuyển sang minimized → chủ động minimize các secondary window đã đăng ký; restore MainView chỉ khôi phục MainView → chọn thumbnail cửa sổ phụ mới khôi phục/activate đúng window đó.
12. Khi đóng, editor chờ worker hoàn tất theo tín hiệu, sau đó giải phóng camera, serial, multimedia, Matplotlib và lưu session.
