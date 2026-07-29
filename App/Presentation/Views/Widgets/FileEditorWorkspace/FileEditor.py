########################################################################
# @file App/Presentation/Views/Widgets/FileEditorWorkspace/FileEditor.py
# Author: TRAN NGUYEN HIEN
# Email: trannguyenhien29085@gmail.com
########################################################################
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QMessageBox, QSizePolicy
from PyQt6.QtCore import Qt, pyqtSlot, QElapsedTimer
from PyQt6.QtGui import QImage, QPixmap

from App.Infrastructure.Helpers.ResourceHelper import apply_stylesheet
from App.Presentation.Views.Widgets.FileEditorWorkspace.MotorControlEditor import MotorControlEditor
from App.Presentation.Views.Widgets.FileEditorWorkspace.MediaControlEditor import MediaControlEditor

class FileEditor(QWidget):
    PREVIEW_UPDATE_INTERVAL_MS = 66

    def __init__(self, view_model, parent=None):
        super().__init__(parent)
        self.view_model = view_model
        self.current_frame = None
        self._preview_update_clock = QElapsedTimer()
        self._preview_update_clock.start()
        self._last_preview_update_ms = -self.PREVIEW_UPDATE_INTERVAL_MS

        self.motor_editor = MotorControlEditor()
        self.media_editor = MediaControlEditor()

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("FileEditor")

        self.setup_ui()
        self.connect_view_model_signals()
        self.connect_sub_widget_signals()
        self.load_file_editor_style()

    def load_file_editor_style(self):
        apply_stylesheet(self, "FileEditorStyles.qss")

    def setup_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)

        # Camera preview
        self.preview_container = QWidget()
        self.preview_container.setObjectName("PreviewContainer") 
        
        preview_layout = QVBoxLayout(self.preview_container)
        preview_layout.setContentsMargins(0, 0, 0, 0)

        self.lbl_camera = QLabel("Camera Offline")
        self.lbl_camera.setObjectName("CameraLabel") 
        self.lbl_camera.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_camera.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.lbl_camera.setMinimumSize(20, 240)
        self.lbl_camera.setScaledContents(True)

        preview_layout.addWidget(self.lbl_camera)
        main_layout.addWidget(self.preview_container, stretch=3)

        # Control panel
        self.control_panel = QWidget()
        control_layout = QVBoxLayout(self.control_panel)
        control_layout.setContentsMargins(5, 5, 5, 5)
        control_layout.setSpacing(10)

        control_layout.addWidget(self.motor_editor)
        control_layout.addWidget(self.media_editor)
        control_layout.addStretch()

        # FIX: Set stretch = 0 so control_panel does not expand when the window is resized
        main_layout.addWidget(self.control_panel, stretch=0)

    def connect_view_model_signals(self):
        self.view_model.frame_received.connect(self.on_frame_received)
        self.view_model.video_state_changed.connect(self.on_video_state_changed)
        self.view_model.recording_time_updated.connect(self.on_recording_time_updated)
        self.view_model.error_occurred.connect(self.on_error)

    def connect_sub_widget_signals(self):
        self.motor_editor.move_up_requested.connect(self.on_motor_move_up)
        self.motor_editor.move_down_requested.connect(self.on_motor_move_down)
        self.motor_editor.stop_requested.connect(self.on_motor_stop)

        self.media_editor.capture_requested.connect(self.on_media_capture)
        self.media_editor.record_requested.connect(self.on_media_record)
        self.media_editor.pause_requested.connect(self.on_media_pause)
        self.media_editor.resume_requested.connect(self.on_media_resume)
        self.media_editor.stop_video_requested.connect(self.on_media_stop_video)

    # --- ViewModel signal handlers ---
    @pyqtSlot(QImage)
    def on_frame_received(self, qimage):
        self.current_frame = qimage
        self.media_editor.update_frame(qimage)
        if self._should_update_preview():
            self.update_camera_display(qimage)

    def _should_update_preview(self):
        elapsed_ms = self._preview_update_clock.elapsed()
        if (
            elapsed_ms - self._last_preview_update_ms
            < self.PREVIEW_UPDATE_INTERVAL_MS
        ):
            return False
        self._last_preview_update_ms = elapsed_ms
        return True

    @pyqtSlot(str)
    def on_video_state_changed(self, state):
        self.media_editor.set_recording_state(state)

    @pyqtSlot(str)
    def on_recording_time_updated(self, time_str):
        self.media_editor.set_recording_time(time_str)

    @pyqtSlot(str)
    def on_error(self, message):
        QMessageBox.warning(self, "Notification", message)

    # --- Sub-widget signal handlers ---
    @pyqtSlot(str, str)
    def on_motor_move_up(self, height, speed):
        self.view_model.move_up(height, speed)

    @pyqtSlot(str, str)
    def on_motor_move_down(self, height, speed):
        self.view_model.move_down(height, speed)

    @pyqtSlot()
    def on_motor_stop(self):
        self.view_model.stop_motor()

    @pyqtSlot(QImage)
    def on_media_capture(self, qimage):
        self.view_model.capture_image(qimage)

    @pyqtSlot()
    def on_media_record(self):
        self.view_model.start_video()

    @pyqtSlot()
    def on_media_pause(self):
        self.view_model.pause_video()

    @pyqtSlot()
    def on_media_resume(self):
        self.view_model.resume_video()

    @pyqtSlot()
    def on_media_stop_video(self):
        self.view_model.stop_video()

    def update_camera_display(self, qimage):
        if qimage is None or qimage.isNull():
            return
        label_size = self.lbl_camera.size()
        if label_size.isEmpty():
            return
        pixmap = QPixmap.fromImage(qimage)
        scaled_pixmap = pixmap.scaled(
            label_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation
        )
        self.lbl_camera.setPixmap(scaled_pixmap)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.current_frame and not self.current_frame.isNull():
            self.update_camera_display(self.current_frame)

    def close_editor(self):
        self.view_model.close()
