#########################################################################
# @file App/Presentation/Views/Widgets/FileEditorWorkspace/ImageEditor.py
# Author: TRAN NGUYEN HIEN
# Email: trannguyenhien29085@gmail.com
#########################################################################
import os
import numpy as np

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QFileDialog, QSizePolicy, QMessageBox,
                             QGroupBox)
from PyQt6.QtCore import Qt, pyqtSlot, pyqtSignal, QSize, QTimer
from PyQt6.QtGui import QImage, QPixmap, QIcon, QPainter

import matplotlib
matplotlib.use('Qt5Agg')
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from App.Infrastructure.Helpers.ResourceHelper import apply_stylesheet, resource_path


class ImageEditor(QWidget):
    sig_open_video = pyqtSignal(str, str)
    close_ready = pyqtSignal()

    def __init__(self, view_model, parent=None):
        super().__init__(parent)
        self.view_model = view_model
        self.current_pixmap = None
        self._close_when_idle = False

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("ImageEditor")

        # [CHANGE] Variables for zoom/pan
        self.default_xlim = (0.0, 5.0)
        self.default_ylim = (0.0, 3.0)
        self.xlim = self.default_xlim
        self.ylim = self.default_ylim
        self.x_bound = (0.0, 5.0)
        self.y_bound = (0.0, 3.0)

        self.is_panning = False
        self.pan_start_x = 0.0
        self.pan_start_y = 0.0

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

        # Replace QLabel with FigureCanvas
        self.figure = Figure(figsize=(7, 5), dpi=100)
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setParent(self)
        self.canvas.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
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

        # Connect Matplotlib events for zoom/pan
        self._mpl_connection_ids = [
            self.canvas.mpl_connect('scroll_event', self.on_scroll),
            self.canvas.mpl_connect('button_press_event', self.on_mouse_press),
            self.canvas.mpl_connect('button_release_event', self.on_mouse_release),
            self.canvas.mpl_connect('motion_notify_event', self.on_mouse_move),
        ]

        self.ax = None  # will be created when drawing the image

    def connect_view_model_signals(self):
        self.view_model.image_loaded.connect(self.on_image_loaded)

    def connect_ui_signals(self):
        self.btn_open.clicked.connect(self.on_open_clicked)
        self.btn_capture.clicked.connect(self.on_capture_clicked)
        self.btn_calibration.clicked.connect(self.on_calibration_clicked)

    # Function to convert QPixmap to numpy array (RGB)
    def pixmap_to_array(self, pixmap):
        """Convert QPixmap to a numpy array (H, W, 3) of type uint8."""
        image = pixmap.toImage().convertToFormat(QImage.Format.Format_RGB888)
        ptr = image.bits()
        ptr.setsize(image.sizeInBytes())
        rows = np.frombuffer(ptr, dtype=np.uint8).reshape(
            image.height(), image.bytesPerLine()
        )
        return rows[:, : image.width() * 3].reshape(
            image.height(), image.width(), 3
        ).copy()

    # Draw the image onto the canvas
    def draw_image(self):
        if self.current_pixmap is None:
            return
        try:
            img_array = self.pixmap_to_array(self.current_pixmap)
            self.figure.clear()
            self.ax = self.figure.add_subplot(111)
            # Display image with extent [0,5] for x and [0,3] for y
            # Replace aspect='auto' with aspect='equal' to preserve aspect ratio
            self.ax.imshow(img_array, extent=[0, 5, 0, 3], origin='upper', aspect='equal')
            self.ax.set_xlim(self.xlim)
            self.ax.set_ylim(self.ylim)
            self.ax.set_xlabel('x [mm]', fontsize=11)
            self.ax.set_ylabel('y [mm]', fontsize=11)
            self.figure.tight_layout()
            self.canvas.draw_idle()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Cannot display image:\n{str(e)}")

    # Mouse event handlers for panning
    def on_mouse_press(self, event):
        if event.button == 3 and event.inaxes:  # Right mouse button
            self.is_panning = True
            self.pan_start_x = event.xdata
            self.pan_start_y = event.ydata
            self.canvas.setCursor(Qt.CursorShape.ClosedHandCursor)

    def on_mouse_release(self, event):
        if event.button == 3:
            self.is_panning = False
            self.canvas.setCursor(Qt.CursorShape.ArrowCursor)

    def on_mouse_move(self, event):
        if self.is_panning and event.inaxes and self.ax is not None:
            dx = event.xdata - self.pan_start_x
            dy = event.ydata - self.pan_start_y

            cur_xlim = self.ax.get_xlim()
            cur_ylim = self.ax.get_ylim()

            new_xmin = cur_xlim[0] - dx
            new_xmax = cur_xlim[1] - dx
            new_ymin = cur_ylim[0] - dy
            new_ymax = cur_ylim[1] - dy

            # Clamp within bounds
            if new_xmin < self.x_bound[0]:
                offset = self.x_bound[0] - new_xmin
                new_xmin += offset
                new_xmax += offset
            elif new_xmax > self.x_bound[1]:
                offset = self.x_bound[1] - new_xmax
                new_xmin += offset
                new_xmax += offset

            if new_ymin < self.y_bound[0]:
                offset = self.y_bound[0] - new_ymin
                new_ymin += offset
                new_ymax += offset
            elif new_ymax > self.y_bound[1]:
                offset = self.y_bound[1] - new_ymax
                new_ymin += offset
                new_ymax += offset

            self.xlim = (new_xmin, new_xmax)
            self.ylim = (new_ymin, new_ymax)
            self.ax.set_xlim(self.xlim)
            self.ax.set_ylim(self.ylim)
            self.canvas.draw_idle()

    # Zoom handling with scroll wheel
    def on_scroll(self, event):
        if event.inaxes is None or self.ax is None:
            return
        scale_factor = 1.2 if event.button == 'up' else 1/1.2  # up = zoom in

        xdata, ydata = event.xdata, event.ydata
        xmin, xmax = self.xlim
        ymin, ymax = self.ylim

        new_xmin = xdata - (xdata - xmin) * scale_factor
        new_xmax = xdata + (xmax - xdata) * scale_factor
        new_ymin = ydata - (ydata - ymin) * scale_factor
        new_ymax = ydata + (ymax - ydata) * scale_factor

        new_xmin, new_xmax, new_ymin, new_ymax = self._clamp_limits(
            new_xmin, new_xmax, new_ymin, new_ymax)

        self.xlim = (new_xmin, new_xmax)
        self.ylim = (new_ymin, new_ymax)
        self.ax.set_xlim(self.xlim)
        self.ax.set_ylim(self.ylim)
        self.canvas.draw_idle()

    def _clamp_limits(self, xmin, xmax, ymin, ymax):
        """Ensure limits are within bounds and have a minimum width."""
        xmin = max(self.x_bound[0], xmin)
        xmax = min(self.x_bound[1], xmax)
        ymin = max(self.y_bound[0], ymin)
        ymax = min(self.y_bound[1], ymax)

        min_range = 0.1
        if xmax - xmin < min_range:
            center = (xmin + xmax) / 2
            xmin = center - min_range / 2
            xmax = center + min_range / 2
            xmin = max(self.x_bound[0], xmin)
            xmax = min(self.x_bound[1], xmax)

        if ymax - ymin < min_range:
            center = (ymin + ymax) / 2
            ymin = center - min_range / 2
            ymax = center + min_range / 2
            ymin = max(self.y_bound[0], ymin)
            ymax = min(self.y_bound[1], ymax)

        return xmin, xmax, ymin, ymax

    def reset_zoom(self):
        """Reset zoom to default (full image)."""
        self.xlim = self.default_xlim
        self.ylim = self.default_ylim
        if self.ax is not None:
            self.ax.set_xlim(self.xlim)
            self.ax.set_ylim(self.ylim)
            self.canvas.draw_idle()

    @pyqtSlot()
    def on_open_clicked(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Image/Video", "",
            "All Supported (*.png *.jpg *.jpeg *.bmp *.gif *.mp4 *.avi *.mov *.mkv *.flv);;"
            "Images (*.png *.jpg *.jpeg *.bmp *.gif);;Videos (*.mp4 *.avi *.mov *.mkv *.flv)"
        )
        if file_path:
            ext = os.path.splitext(file_path)[1].lower()
            video_exts = ['.mp4', '.avi', '.mov', '.mkv', '.flv']
            if ext in video_exts:
                # Emit signal requesting to open video
                self.sig_open_video.emit(self.property("project_name"), file_path)
            else:
                self.view_model.load_image(file_path)

    @pyqtSlot()
    def on_capture_clicked(self):
        """Handle capture button click: show save dialog and save current image."""
        if self.current_pixmap is None or self.current_pixmap.isNull():
            QMessageBox.warning(self, "No Image", "No image available to capture/save.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Captured Image", "",
            "Images (*.png *.jpg *.jpeg *.bmp)"
        )

        if file_path:
            self.view_model.save_image(file_path)

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

    def _on_droplet_window_closed(self, window):
        if window in self.droplet_windows:
            self.droplet_windows.remove(window)
        self._maybe_emit_close_ready()

    @pyqtSlot(QPixmap)
    def on_image_loaded(self, pixmap):
        self.current_pixmap = pixmap
        # Draw the image on the canvas instead of QLabel
        self.draw_image()
        # Reset zoom to default when loading a new image
        self.reset_zoom()

    def resizeEvent(self, event):
        """Adjust figure layout when the window is resized to avoid label clipping."""
        super().resizeEvent(event)
        if self.current_pixmap is not None:
            # Update tight_layout to display margins and labels correctly
            self.figure.tight_layout()
            self.canvas.draw_idle()

    def load_image_from_file(self, file_path):
        """Public method to load image, used by drag and drop."""
        self.view_model.load_image(file_path)

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
        for connection_id in self._mpl_connection_ids:
            self.canvas.mpl_disconnect(connection_id)
        self._mpl_connection_ids.clear()
        self.figure.clear()
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
