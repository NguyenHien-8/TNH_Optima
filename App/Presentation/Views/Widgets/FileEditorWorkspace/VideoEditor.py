##########################################################################
# @file App/Presentation/Views/Widgets/FileEditorWorkspace/VideoEditor.py
# Author: TRAN NGUYEN HIEN
# Email: trannguyenhien29085@gmail.com
##########################################################################
import os
from datetime import datetime
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QFileDialog, QSlider, QLabel, QSizePolicy, QMessageBox,
                             QComboBox)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QUrl, QSize, QTimer
# Đã thêm QPainter, QFont, QColor, QPen vào imports
from PyQt6.QtGui import QIcon, QCloseEvent, QPixmap, QImage, QPainter, QFont, QColor, QPen
from PyQt6.QtMultimedia import QMediaPlayer, QVideoFrame
from PyQt6.QtMultimediaWidgets import QVideoWidget

from App.Infrastructure.Helpers.PathHelper import project_media_item_path
from App.Infrastructure.Helpers.ResourceHelper import apply_stylesheet, resource_path
from App.Presentation.ViewModels.Workers import FunctionWorker


class VideoEditor(QWidget):
    sig_open_video = pyqtSignal(str, str)  # project_name, file_path
    media_created = pyqtSignal(str, str, str, str)
    close_ready = pyqtSignal()
    media_load_started = pyqtSignal()
    media_load_finished = pyqtSignal()
    playback_requested = pyqtSignal()

    def __init__(
        self,
        file_path=None,
        project_name=None,
        parent=None,
        project_path=None,
    ):
        super().__init__(parent)
        self.project_name = project_name
        self.project_path = project_path
        self.file_path = file_path
        self.media_player = QMediaPlayer(self)
        self.video_widget = QVideoWidget(self)
        self.seeking = False
        self.current_frame = None  # Store the latest frame from video
        self._workers = set()
        self._close_when_idle = False
        self._media_load_pending = False
        self._loaded_file_path = None
        self._resume_position = 0

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("VideoEditor")

        self.setup_ui()
        self.connect_signals()
        self.load_style()

        # Get video sink from media player to receive frames (replaces QVideoProbe)
        self.video_sink = self.media_player.videoSink()
        self.video_sink.videoFrameChanged.connect(self.on_video_frame_probed)

        if file_path and os.path.exists(file_path):
            self.load_video(file_path)
        else:
            self._set_play_icon()

    def load_style(self):
        apply_stylesheet(self, "VideoEditorStyles.qss")

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- 1. Video Area ---
        video_container = QWidget()
        video_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        video_layout = QVBoxLayout(video_container)
        video_layout.setContentsMargins(0, 0, 0, 0)

        self.video_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        video_layout.addWidget(self.video_widget)

        main_layout.addWidget(video_container, stretch=1)

        # --- 2. Control Panel ---
        control_panel = QWidget()
        control_panel.setObjectName("ControlPanel")
        control_panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        panel_layout = QVBoxLayout(control_panel)
        panel_layout.setContentsMargins(15, 10, 15, 15)
        panel_layout.setSpacing(5)

        # Timeline Slider
        self.position_slider = QSlider(Qt.Orientation.Horizontal)
        self.position_slider.setRange(0, 0)
        self.position_slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.position_slider.setFixedHeight(20)
        panel_layout.addWidget(self.position_slider)

        # Buttons & Info Row
        btns_row_layout = QHBoxLayout()
        btns_row_layout.setSpacing(10)
        btns_row_layout.setContentsMargins(0, 5, 0, 0)

        # Left: Time Label
        self.label_time = QLabel("00:00:00 / 00:00:00")
        self.label_time.setObjectName("TimeLabel")
        self.label_time.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.label_time.setFixedWidth(150)
        btns_row_layout.addWidget(self.label_time)

        btns_row_layout.addStretch()

        icon_base = resource_path(os.path.join("App", "ReSource", "Icon", "Media"))

        # Open Button
        self.btn_open = self._create_button(icon_base, "open_video.svg", "Open Video")
        btns_row_layout.addWidget(self.btn_open)

        # Capture Button
        self.btn_capture = self._create_button(icon_base, "captureimage.svg", "Capture Image")
        btns_row_layout.addWidget(self.btn_capture)

        # Skip Back
        self.btn_skip_back = self._create_button(icon_base, "skipback.svg", "Skip back 10 seconds")
        btns_row_layout.addWidget(self.btn_skip_back)

        # Play/Pause
        self.btn_play = self._create_button(icon_base, "play_video.svg", "Play", size=48, icon_size=28)
        self.btn_play.setObjectName("PlayBtn")
        btns_row_layout.addWidget(self.btn_play)

        # Skip Forward
        self.btn_skip_forward = self._create_button(icon_base, "skipforward.svg", "Skip forward 30 seconds")
        btns_row_layout.addWidget(self.btn_skip_forward)

        btns_row_layout.addStretch()

        # Right: Speed Control
        self.speed_label = QLabel("Speed:")
        self.speed_label.setObjectName("SpeedLabel")
        btns_row_layout.addWidget(self.speed_label)

        self.speed_combo = QComboBox()
        self.speed_combo.addItems(["0.25x", "0.5x", "1.0x", "1.75x", "2.0x"])
        self.speed_combo.setItemData(0, 0.25)
        self.speed_combo.setItemData(1, 0.5)
        self.speed_combo.setItemData(2, 1.0)
        self.speed_combo.setItemData(3, 1.75)
        self.speed_combo.setItemData(4, 2.0)
        self.speed_combo.setCurrentIndex(2)
        self.speed_combo.setFixedWidth(70)
        self.speed_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        btns_row_layout.addWidget(self.speed_combo)

        panel_layout.addLayout(btns_row_layout)
        main_layout.addWidget(control_panel)

        self.media_player.setVideoOutput(self.video_widget)

    def _create_button(self, base_path, icon_name, tooltip, size=40, icon_size=20):
        btn = QPushButton()
        btn.setObjectName("MediaBtn")
        btn.setToolTip(tooltip)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedSize(size, size)

        icon_path = os.path.join(base_path, icon_name)
        if os.path.exists(icon_path):
            btn.setIcon(QIcon(icon_path))
            btn.setIconSize(QSize(icon_size, icon_size))
        else:
            # Fallback text
            if "play" in icon_name:
                btn.setText("▶")
            elif "pause" in icon_name:
                btn.setText("||")
            elif "back" in icon_name:
                btn.setText("<<")
            elif "forward" in icon_name:
                btn.setText(">>")
            elif "open" in icon_name:
                btn.setText("📂")
            elif "photo" in icon_name:
                btn.setText("📷")

        return btn

    def connect_signals(self):
        self.btn_open.clicked.connect(self.on_open_clicked)
        self.btn_capture.clicked.connect(self.capture_image)
        self.btn_skip_back.clicked.connect(self.skip_back)
        self.btn_play.clicked.connect(self.toggle_play)
        self.btn_skip_forward.clicked.connect(self.skip_forward)

        self.position_slider.sliderPressed.connect(self.on_slider_pressed)
        self.position_slider.sliderMoved.connect(self.media_player.setPosition)
        self.position_slider.sliderReleased.connect(self.on_slider_released)

        self.media_player.positionChanged.connect(self.update_position)
        self.media_player.durationChanged.connect(self.update_duration)
        self.media_player.playbackStateChanged.connect(self.update_play_button)
        self.media_player.mediaStatusChanged.connect(
            self._on_media_status_changed
        )
        self.speed_combo.currentIndexChanged.connect(self.on_speed_changed)

    @pyqtSlot(QVideoFrame)
    def on_video_frame_probed(self, frame):
        """Store the current frame as a QImage."""
        if frame.isValid():
            image = frame.toImage()
            if not image.isNull():
                self.current_frame = image

    def load_video(self, file_path):
        """Prepare a video tab without allocating a decoder or auto-playing."""
        self._release_media_source(preserve_position=False)
        self.file_path = file_path
        self._resume_position = 0
        self.current_frame = None
        self.position_slider.setRange(0, 0)
        self.position_slider.setValue(0)
        self.label_time.setText("00:00:00 / 00:00:00")
        self.speed_combo.setCurrentIndex(2)
        self._set_play_icon()

    def _ensure_media_source(self):
        if not self.file_path or not os.path.isfile(self.file_path):
            QMessageBox.warning(
                self,
                "No Video",
                "The selected video file is no longer available.",
            )
            return False

        normalized_file = os.path.normcase(os.path.abspath(self.file_path))
        normalized_loaded = (
            os.path.normcase(os.path.abspath(self._loaded_file_path))
            if self._loaded_file_path
            else None
        )
        if (
            normalized_loaded == normalized_file
            and not self.media_player.source().isEmpty()
        ):
            return True

        self._media_load_pending = True
        self.media_load_started.emit()
        self._loaded_file_path = self.file_path
        self.media_player.setSource(QUrl.fromLocalFile(self.file_path))
        rate = self.speed_combo.currentData()
        self.media_player.setPlaybackRate(rate if rate is not None else 1.0)
        return True

    def is_media_loading(self):
        return self._media_load_pending

    @pyqtSlot(QMediaPlayer.MediaStatus)
    def _on_media_status_changed(self, status):
        if not self._media_load_pending:
            return
        terminal_statuses = {
            QMediaPlayer.MediaStatus.LoadedMedia,
            QMediaPlayer.MediaStatus.BufferedMedia,
            QMediaPlayer.MediaStatus.EndOfMedia,
            QMediaPlayer.MediaStatus.InvalidMedia,
        }
        if status in terminal_statuses:
            if status == QMediaPlayer.MediaStatus.InvalidMedia:
                self._loaded_file_path = None
            elif self._resume_position > 0:
                self.media_player.setPosition(self._resume_position)
            self._media_load_pending = False
            self.media_load_finished.emit()

    def _set_pause_icon(self):
        icon_base = resource_path(os.path.join("App", "ReSource", "Icon", "Media"))
        icon_pause = os.path.join(icon_base, "pausevideo.svg")
        if os.path.exists(icon_pause):
            self.btn_play.setIcon(QIcon(icon_pause))
        else:
            self.btn_play.setText("||")
        self.btn_play.setToolTip("Pause")

    def _set_play_icon(self):
        icon_base = resource_path(os.path.join("App", "ReSource", "Icon", "Media"))
        icon_play = os.path.join(icon_base, "play_video.svg")
        if os.path.exists(icon_play):
            self.btn_play.setIcon(QIcon(icon_play))
        else:
            self.btn_play.setText("▶")
        self.btn_play.setToolTip("Play")

    @pyqtSlot()
    def on_open_clicked(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Video", "",
            "Videos (*.mp4 *.avi *.mov *.mkv *.flv)"
        )
        if file_path:
            self.sig_open_video.emit(self.project_name, file_path)

    @pyqtSlot()
    def capture_image(self):
        if not self.file_path or not os.path.exists(self.file_path):
            QMessageBox.warning(self, "No Video", "No video is currently open.")
            return

        item_path = None
        if self.project_name and self.project_path:
            item_path = project_media_item_path(
                self.file_path,
                "Video",
                self.project_path,
            )
        image_folder = (
            os.path.join(item_path, "Image") if item_path else None
        )

        if image_folder:
            try:
                os.makedirs(image_folder, exist_ok=True)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Cannot create Image folder: {str(e)}")
                return

        # Get frame from video sink if available
        pixmap = None
        if self.current_frame and not self.current_frame.isNull():
            pixmap = QPixmap.fromImage(self.current_frame)
        else:
            # Fallback: grab from video widget (might be empty)
            pixmap = self.video_widget.grab()
            
        if pixmap is None or pixmap.isNull():
            QMessageBox.warning(self, "Capture Failed", "Cannot capture image from video.")
            return

        # --- BEGIN MODIFICATION: DRAW TIMESTAMP ON IMAGE ---
        
        # 1. Tính toán thời gian (Time Calculation)
        current_ms = self.media_player.position()
        total_seconds = current_ms / 1000.0
        
        # Định dạng text theo kiểu "T= ..." 
        # Nếu dưới 60s hiển thị giây lẻ (VD: T= 15.2 s), nếu trên hiển thị phút (VD: T= 1:30 min)
        if total_seconds < 60:
            time_text = f"T= {total_seconds:.1f} s"
        else:
            minutes = int(total_seconds // 60)
            seconds = int(total_seconds % 60)
            time_text = f"T= {minutes}:{seconds:02d} min"

        # 2. Khởi tạo Painter để vẽ lên Pixmap
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 3. Cấu hình Font (Tự động scale theo chiều cao ảnh)
        # Font size xấp xỉ 1/25 chiều cao ảnh, tối thiểu là 20px
        font_size = max(20, pixmap.height() // 25)
        font = QFont("Arial", font_size, QFont.Weight.Bold)
        painter.setFont(font)

        # 4. Cấu hình màu bút (Màu xanh dương giống hình mẫu)
        # Mã màu Hex #0066cc (Strong Blue)
        pen = QPen(QColor("#0066cc"))
        painter.setPen(pen)

        # 5. Vẽ chữ (Góc trên bên phải)
        # Tạo padding (khoảng cách lề) dựa trên font size
        padding = font_size 
        
        # Vẽ text vào vùng hình chữ nhật đã trừ đi padding
        # AlignTop | AlignRight: Đặt ở góc trên phải
        draw_rect = pixmap.rect().adjusted(padding, padding, -padding, -padding)
        painter.drawText(draw_rect, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight, time_text)

        # Kết thúc vẽ
        painter.end()

        # --- END MODIFICATION ---

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"capture_{timestamp}.png"
        if image_folder:
            filepath = os.path.join(image_folder, filename)
        else:
            filepath, _ = QFileDialog.getSaveFileName(
                self,
                "Save Captured Image",
                filename,
                "PNG Images (*.png)",
            )
            if not filepath:
                return
            if not os.path.splitext(filepath)[1]:
                filepath += ".png"

        image = pixmap.toImage()
        worker = FunctionWorker(lambda: image.save(filepath, "PNG"))
        self._workers.add(worker)
        worker.result_ready.connect(
            lambda success: self._on_capture_saved(
                filepath,
                success,
                item_path,
            )
        )
        worker.error_occurred.connect(
            lambda message: QMessageBox.critical(self, "Save Error", message)
        )
        worker.finished.connect(lambda: self._finish_worker(worker))
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _on_capture_saved(self, filepath, success, project_item_path=None):
        if not success:
            QMessageBox.warning(self, "Save Failed", "Cannot save image file.")
            return
        if not self.project_name or not project_item_path:
            return
        item_name = os.path.basename(project_item_path)
        self.media_created.emit(
            self.project_name or "",
            item_name,
            "Image",
            filepath,
        )

    def _finish_worker(self, worker):
        self._workers.discard(worker)
        if self._close_when_idle and not any(
            item.isRunning() for item in self._workers
        ):
            self._close_when_idle = False
            QTimer.singleShot(0, self.close_ready.emit)

    @pyqtSlot()
    def skip_back(self):
        current = self.media_player.position()
        new_pos = max(0, current - 10000)
        self.media_player.setPosition(new_pos)

    @pyqtSlot()
    def skip_forward(self):
        current = self.media_player.position()
        duration = self.media_player.duration()
        new_pos = min(duration, current + 30000)
        self.media_player.setPosition(new_pos)

    @pyqtSlot()
    def toggle_play(self):
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.pause_playback()
            return

        self.playback_requested.emit()
        if self._ensure_media_source():
            self.media_player.play()

    def update_play_button(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._set_pause_icon()
        else:
            self._set_play_icon()

    def update_position(self, position):
        if not self.seeking:
            self.position_slider.setValue(position)
        self.update_time_label()

    def update_duration(self, duration):
        self.position_slider.setRange(0, duration)
        self.update_time_label()

    def update_time_label(self):
        pos = self.media_player.position()
        dur = self.media_player.duration()
        pos_str = self._format_time(pos // 1000)
        dur_str = self._format_time(dur // 1000) if dur > 0 else "00:00:00"
        self.label_time.setText(f"{pos_str} / {dur_str}")

    def _format_time(self, seconds):
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

    @pyqtSlot(int)
    def on_speed_changed(self, index):
        rate = self.speed_combo.itemData(index)
        if rate is not None:
            self.media_player.setPlaybackRate(rate)

    @pyqtSlot()
    def on_slider_pressed(self):
        self.seeking = True

    @pyqtSlot()
    def on_slider_released(self):
        self.media_player.setPosition(self.position_slider.value())
        self.seeking = False

    # --- New methods to support rename ---
    def _release_media_source(self, preserve_position):
        if preserve_position and not self.media_player.source().isEmpty():
            self._resume_position = max(0, self.media_player.position())
        elif not preserve_position:
            self._resume_position = 0
        if self._media_load_pending:
            self._media_load_pending = False
            self.media_load_finished.emit()
        self.media_player.stop()
        self.media_player.setSource(QUrl())
        self._loaded_file_path = None
        self.current_frame = None
        self._set_play_icon()

    def pause_playback(self, release_resources=False):
        """Pause playback, optionally releasing the decoder while retaining position."""
        if release_resources:
            self._release_media_source(preserve_position=True)
        else:
            self.media_player.pause()
            self._set_play_icon()

    def stop_playback(self):
        """Stop video playback, release its decoder and reset resume state."""
        self._release_media_source(preserve_position=False)

    def reload_video(self, new_path):
        """Point the editor at a renamed video and keep it paused/lazy."""
        self.load_video(new_path)

    def closeEvent(self, event: QCloseEvent):
        running_workers = [
            worker for worker in self._workers if worker.isRunning()
        ]
        if running_workers:
            self._close_when_idle = True
            for worker in running_workers:
                worker.requestInterruption()
            event.ignore()
            return
        try:
            self.video_sink.videoFrameChanged.disconnect(self.on_video_frame_probed)
        except (TypeError, RuntimeError):
            pass
        self.stop_playback()
        self.media_player.setVideoOutput(None)
        self.current_frame = None
        super().closeEvent(event)
