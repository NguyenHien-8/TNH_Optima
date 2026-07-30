#########################################################################
# @file App/Presentation/Views/Widgets/FileEditorWorkspace/ImageEditor.py
# Author: TRAN NGUYEN HIEN
# Email: trannguyenhien29085@gmail.com
#########################################################################
import os

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QFileDialog, QMessageBox,
                             QGroupBox)
from PyQt6.QtCore import Qt, pyqtSlot, pyqtSignal, QSize, QTimer
from PyQt6.QtGui import QImage, QPixmap, QIcon

from App.Infrastructure.Helpers.ResourceHelper import apply_stylesheet, resource_path
from App.Presentation.Views.Widgets.FileEditorWorkspace.ImageCanvas import (
    ImageCanvas,
)


class ImageEditor(QWidget):
    sig_open_video = pyqtSignal(str, str)
    close_ready = pyqtSignal()

    def __init__(self, view_model, parent=None):
        super().__init__(parent)
        self.view_model = view_model
        self.current_pixmap = None
        self._close_when_idle = False
        self._pending_image_path = None
        self._pending_image_remember_directory = False

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("ImageEditor")

        self.setup_ui()
        self.connect_view_model_signals()
        self.connect_ui_signals()
        self.load_style()

        # Store list of Droplet Analysis windows opened from this editor
        self.droplet_windows = []
        if hasattr(self.view_model, "workers_idle"):
            self.view_model.workers_idle.connect(self._maybe_emit_close_ready)

    def load_style(self):
        apply_stylesheet(self, "ImageEditorStyles.qss")

    def setup_ui(self):
        # Use QVBoxLayout: canvas on top, control panel below
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)

        self.canvas = ImageCanvas(self)
        main_layout.addWidget(self.canvas, stretch=3)

        # Control panel at the bottom
        control_panel = QWidget()
        control_panel.setObjectName("ControlPanel")
        control_layout = QVBoxLayout(control_panel)
        control_layout.setContentsMargins(5, 5, 5, 5)
        control_layout.setSpacing(10)

        # --- MERGED CONTROL: Create a single GroupBox for Tools ---
        tools_group = QGroupBox("Image Controls")
        tools_layout = QHBoxLayout(tools_group)
        tools_layout.setContentsMargins(10, 5, 10, 5)
        tools_layout.setSpacing(15)

        # Base icon path
        icon_base_path = resource_path(os.path.join("App", "ReSource", "Icon", "Media"))

        # 1. Open Image button
        self.btn_open = QPushButton()
        self.btn_open.setObjectName("MediaBtn")
        self.btn_open.setToolTip("Open File")
        self.btn_open.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open.setFixedSize(50, 50)

        icon_open_path = os.path.join(icon_base_path, "open_image.svg")
        if os.path.exists(icon_open_path):
            self.btn_open.setIcon(QIcon(icon_open_path))
            self.btn_open.setIconSize(QSize(30, 30))

        tools_layout.addWidget(self.btn_open)

        # 2. Capture Image button
        self.btn_capture = QPushButton()
        self.btn_capture.setObjectName("MediaBtn")
        self.btn_capture.setToolTip("Capture Image")
        self.btn_capture.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_capture.setFixedSize(50, 50)

        icon_capture_path = os.path.join(icon_base_path, "photo_camera.svg")
        if os.path.exists(icon_capture_path):
            self.btn_capture.setIcon(QIcon(icon_capture_path))
            self.btn_capture.setIconSize(QSize(30, 30))

        tools_layout.addWidget(self.btn_capture)

        # 3. Calibration button (open Droplet Analysis)
        self.btn_calibration = QPushButton()
        self.btn_calibration.setObjectName("MediaBtn")
        self.btn_calibration.setToolTip("Open Droplet Analysis")
        self.btn_calibration.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_calibration.setFixedSize(50, 50)
        icon_calib_path = os.path.join(icon_base_path, "analysis.svg")
        if os.path.exists(icon_calib_path):
            self.btn_calibration.setIcon(QIcon(icon_calib_path))
            self.btn_calibration.setIconSize(QSize(30, 30))
        tools_layout.addWidget(self.btn_calibration)

        # Small separator line (keep for aesthetics, but aspect ratio is no longer needed)
        line = QWidget()
        line.setFixedWidth(1)
        line.setFixedHeight(30)
        line.setStyleSheet("background-color: #555555;")
        # tools_layout.addWidget(line)  # Uncomment if a line is desired

        # Push components to the left
        tools_layout.addStretch()

        # Add GroupBox to the main control panel layout
        control_layout.addWidget(tools_group)

        # Add stretch to control_layout to push GroupBox to the top
        control_layout.addStretch()

        main_layout.addWidget(control_panel, stretch=0)

    def connect_view_model_signals(self):
        self.view_model.image_loaded.connect(self.on_image_loaded)
        self.view_model.error_occurred.connect(self.on_error)
        self.view_model.analysis_components_ready.connect(
            self._open_droplet_analysis
        )

    def connect_ui_signals(self):
        self.btn_open.clicked.connect(self.on_open_clicked)
        self.btn_capture.clicked.connect(self.on_capture_clicked)
        self.btn_calibration.clicked.connect(self.on_calibration_clicked)

    def draw_image(self):
        self.canvas.set_pixmap(self.current_pixmap)

    def reset_zoom(self):
        self.canvas.reset_view()

    def set_image_source(self, file_path, remember_directory=False):
        """Decode the source only when this editor becomes visible."""
        self._pending_image_path = file_path
        self._pending_image_remember_directory = remember_directory
        QTimer.singleShot(0, self._load_pending_image)

    def _load_pending_image(self):
        if not self.isVisible() or not self._pending_image_path:
            return
        file_path = self._pending_image_path
        remember_directory = self._pending_image_remember_directory
        self._pending_image_path = None
        self._pending_image_remember_directory = False
        self.view_model.load_image(
            file_path,
            remember_directory=remember_directory,
        )

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._load_pending_image)

    @pyqtSlot()
    def on_open_clicked(self):
        initial_directory = self.view_model.get_dialog_directory(
            self.view_model.OPEN_DIRECTORY,
            self.property("full_path")
        )
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Image/Video", initial_directory,
            "All Supported (*.png *.jpg *.jpeg *.bmp *.gif *.mp4 *.avi *.mov *.mkv *.flv);;"
            "Images (*.png *.jpg *.jpeg *.bmp *.gif);;Videos (*.mp4 *.avi *.mov *.mkv *.flv)"
        )
        if file_path:
            ext = os.path.splitext(file_path)[1].lower()
            video_exts = ['.mp4', '.avi', '.mov', '.mkv', '.flv']
            if ext in video_exts:
                # Emit signal requesting to open video
                self.view_model.remember_media_path(
                    file_path,
                    self.view_model.OPEN_DIRECTORY,
                )
                self.sig_open_video.emit(self.property("project_name"), file_path)
            else:
                self._pending_image_path = None
                self.view_model.load_image(file_path)

    @pyqtSlot()
    def on_capture_clicked(self):
        """Handle capture button click: show save dialog and save current image."""
        if self.current_pixmap is None or self.current_pixmap.isNull():
            QMessageBox.warning(self, "No Image", "No image available to capture/save.")
            return

        initial_directory = self.view_model.get_dialog_directory(
            self.view_model.CAPTURE_DIRECTORY,
            self.property("full_path")
        )
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Captured Image", initial_directory,
            "Images (*.png *.jpg *.jpeg *.bmp)"
        )

        if file_path:
            self.view_model.save_image(
                file_path,
                self.current_pixmap.toImage(),
            )

    @pyqtSlot()
    def on_calibration_clicked(self):
        """
        Open a new Droplet Analysis Window with the current image.
        """
        if self.current_pixmap is None or self.current_pixmap.isNull():
            QMessageBox.warning(
                self,
                "No Image",
                "No image to analyze. Please open an image first."
            )
            return

        self.btn_calibration.setEnabled(False)
        self.btn_calibration.setToolTip("Loading analysis components...")
        self.view_model.prepare_analysis_components()

    @pyqtSlot()
    def _open_droplet_analysis(self):
        self.btn_calibration.setEnabled(True)
        self.btn_calibration.setToolTip("Open Droplet Analysis")
        if self.current_pixmap is None or self.current_pixmap.isNull():
            return

        try:
            from App.Presentation.Views.Widgets.DropletAnalysisWindow import DropletAnalysisWindow
            from App.Presentation.ViewModels.FeatureViewModel.DropletAnalysisViewModel import DropletAnalysisViewModel

            droplet_view_model = DropletAnalysisViewModel()
            source_image_path = getattr(
                self.view_model, "current_image_path", None
            ) or self.property("full_path")
            if not isinstance(source_image_path, str):
                source_image_path = None
            project_name = self.property("project_name") or getattr(
                self.view_model, "project_name", None
            )
            item_name = getattr(self.view_model, "item_name", None)
            droplet_window = DropletAnalysisWindow(
                droplet_view_model,
                self.current_pixmap,
                parent=self.window(),
                source_image_path=source_image_path,
                project_name=project_name,
                item_name=item_name,
            )
            self.droplet_windows.append(droplet_window)
            droplet_window.show()
            droplet_window.destroyed.connect(
                lambda: self._on_droplet_window_closed(droplet_window)
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Cannot open Droplet Analysis Window:\n{str(e)}"
            )

    @pyqtSlot(str)
    def on_error(self, message):
        self.btn_calibration.setEnabled(True)
        self.btn_calibration.setToolTip("Open Droplet Analysis")
        QMessageBox.warning(self, "Image Error", message)

    def _on_droplet_window_closed(self, window):
        if window in self.droplet_windows:
            self.droplet_windows.remove(window)
        self._maybe_emit_close_ready()

    @pyqtSlot(QImage)
    def on_image_loaded(self, image):
        self.current_pixmap = QPixmap.fromImage(image)
        self.draw_image()

    def load_image_from_file(self, file_path):
        """Public method to load image, used by drag and drop."""
        self.set_image_source(file_path, remember_directory=True)

    def closeEvent(self, event):
        """Close all Droplet Analysis windows when this editor closes."""
        for window in self.droplet_windows[:]:
            if window and window.isVisible():
                window.close()

        view_model_busy = (
            hasattr(self.view_model, "has_running_workers")
            and self.view_model.has_running_workers()
        )
        child_busy = any(
            window is not None and window.isVisible()
            for window in self.droplet_windows
        )
        if view_model_busy or child_busy:
            self._close_when_idle = True
            if hasattr(self.view_model, "request_shutdown"):
                self.view_model.request_shutdown()
            event.ignore()
            return

        self.droplet_windows.clear()
        self.canvas.clear()
        self.current_pixmap = None
        if hasattr(self.view_model, "close"):
            self.view_model.close()
        super().closeEvent(event)

    def _maybe_emit_close_ready(self):
        if not self._close_when_idle:
            return
        view_model_busy = (
            hasattr(self.view_model, "has_running_workers")
            and self.view_model.has_running_workers()
        )
        child_busy = any(
            window is not None and window.isVisible()
            for window in self.droplet_windows
        )
        if not view_model_busy and not child_busy:
            self._close_when_idle = False
            QTimer.singleShot(0, self.close_ready.emit)
