###########################################################
# @file App/Presentation/Views/Dialog/ConfigCameraDialog.py
# Author: TRAN NGUYEN HIEN
# Email: trannguyenhien29085@gmail.com
###########################################################
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QComboBox, QPushButton, QMessageBox, QFrame,
                             QSizePolicy, QStyle, QSpacerItem)
from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QImage, QPixmap, QPainter, QPainterPath

from App.Presentation.ViewModels.DialogViewModel.ConfigCameraViewModel import ConfigCameraViewModel
from App.Infrastructure.Helpers.ResourceHelper import apply_stylesheet

class ConfigCameraDialog(QDialog):
    def __init__(self, camera_view_model, parent=None, has_open_editors=False):
        super().__init__(parent)
        self.setWindowTitle("Camera Configuration")
        self.setFixedSize(430, 230)

        self.has_open_editors = has_open_editors
        self.view_model = (
            camera_view_model
            if isinstance(camera_view_model, ConfigCameraViewModel)
            else ConfigCameraViewModel(camera_view_model)
        )
        self._connect_view_model_signals()

        self.load_camera_dialog_style()
        self.setup_ui()
        self.view_model.scan_cameras()

    def load_camera_dialog_style(self):
        apply_stylesheet(self, "CameraDialogStyles.qss")

    def _connect_view_model_signals(self):
        self.view_model.camera_list_updated.connect(self.update_camera_list)
        self.view_model.preview_frame_received.connect(self.update_preview)

    def setup_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(15, 15, 15, 10)
        main_layout.setSpacing(5)
        self.setLayout(main_layout)

        top_container = QHBoxLayout()
        left_layout = QVBoxLayout()

        lbl_title = QLabel("Camera:")
        left_layout.addWidget(lbl_title)

        # Row: ComboBox + Refresh
        combo_row = QHBoxLayout()
        combo_row.setSpacing(5)

        self.combo_cameras = QComboBox()
        self.combo_cameras.setPlaceholderText("Select Camera...")
        self.combo_cameras.setFixedHeight(28)
        self.combo_cameras.currentIndexChanged.connect(self.on_combo_changed)
        combo_row.addWidget(self.combo_cameras)

        self.btn_refresh = QPushButton()
        self.btn_refresh.setFixedSize(32, 32)
        self.btn_refresh.setToolTip("Refresh Camera List")
        self.btn_refresh.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload))
        self.btn_refresh.clicked.connect(self.on_click_refresh)
        combo_row.addWidget(self.btn_refresh)

        left_layout.addLayout(combo_row)
        left_layout.addStretch()

        # Row: Connect/Disconnect
        btn_control_row = QHBoxLayout()
        btn_control_row.setSpacing(5)

        self.btn_connect = QPushButton("Connect")
        self.btn_connect.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_connect.setFixedHeight(30)
        self.btn_connect.clicked.connect(self.on_click_connect_preview)
        btn_control_row.addWidget(self.btn_connect)

        self.btn_disconnect = QPushButton("Disconnect")
        self.btn_disconnect.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_disconnect.setFixedHeight(30)
        self.btn_disconnect.clicked.connect(self.on_click_disconnect)
        btn_control_row.addWidget(self.btn_disconnect)

        left_layout.addLayout(btn_control_row)
        top_container.addLayout(left_layout, stretch=4)

        # Preview Area
        preview_container = QVBoxLayout()
        preview_container.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lbl_preview = QLabel("Camera Previewer")
        self.lbl_preview.setObjectName("previewLabel") 
        self.lbl_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_preview.setFixedSize(180, 150)
        self.lbl_preview.setScaledContents(False)
        self.set_preview_state("disconnected") 

        preview_container.addWidget(self.lbl_preview)
        top_container.addLayout(preview_container, stretch=6)
        main_layout.addLayout(top_container)

        # Separation (Line)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Plain)
        line.setFixedHeight(2)
        line.setStyleSheet("border-top: 1px solid #7A7A7A;")
        main_layout.addWidget(line)
        main_layout.addSpacing(5)

        # Action Buttons
        action_layout = QHBoxLayout()
        action_layout.addSpacerItem(QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))

        self.btn_apply = QPushButton("Apply and Close")
        self.btn_apply.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_apply.clicked.connect(self.on_click_apply)
        action_layout.addWidget(self.btn_apply)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.clicked.connect(self.on_click_cancel)
        action_layout.addWidget(self.btn_cancel)

        main_layout.addLayout(action_layout)

    def set_preview_state(self, state: str):
        """Thay đổi trạng thái hiển thị của Preview Label bằng Property động"""
        self.lbl_preview.setProperty("state", state)
        self.lbl_preview.style().unpolish(self.lbl_preview)
        self.lbl_preview.style().polish(self.lbl_preview)

    def on_combo_changed(self, index):
        if index >= 0:
            self.view_model.set_selected_camera(self.combo_cameras.currentData())
        else:
            self.view_model.set_selected_camera(None)

    def on_click_refresh(self):
        self.combo_cameras.setPlaceholderText("Scanning...")
        self.view_model.scan_cameras()

    def on_click_connect_preview(self):
        cam_idx = self.view_model.get_selected_camera()
        if cam_idx is None:
            cam_idx = self.combo_cameras.currentData()
            self.view_model.set_selected_camera(cam_idx)

        if cam_idx is None or cam_idx == -1:
            QMessageBox.warning(self, "Warning", "Please select a camera device first!")
            return

        self.lbl_preview.setText("Connecting...")
        self.set_preview_state("connecting")
        self.view_model.connect_preview(cam_idx)

    def on_click_disconnect(self):
        self.view_model.stop_preview()
        self.lbl_preview.clear()
        self.lbl_preview.setText("Disconnected")
        self.set_preview_state("disconnected")

    @pyqtSlot(list)
    def update_camera_list(self, camera_list):
        current_idx = self.combo_cameras.currentData()
        self.combo_cameras.blockSignals(True)
        self.combo_cameras.clear()

        if not camera_list:
            self.combo_cameras.addItem("No cameras found", -1)
            self.combo_cameras.setEnabled(False)
            self.combo_cameras.blockSignals(False)
            return

        self.combo_cameras.setEnabled(True)
        for cam in camera_list:
            name = cam['name'] if isinstance(cam, dict) else f"Camera {cam}"
            idx = cam['index'] if isinstance(cam, dict) else cam
            self.combo_cameras.addItem(name, idx)

        # Restore previous position or original camera
        if current_idx is not None:
            idx = self.combo_cameras.findData(current_idx)
            if idx >= 0: self.combo_cameras.setCurrentIndex(idx)
        else:
            target_id = self.view_model.get_original_camera_id()
            if target_id is not None:
                idx = self.combo_cameras.findData(target_id)
                if idx >= 0: self.combo_cameras.setCurrentIndex(idx)

        self.combo_cameras.blockSignals(False)
        self.on_combo_changed(self.combo_cameras.currentIndex())

    @pyqtSlot(QImage)
    def update_preview(self, qt_img):
        if qt_img.isNull():
            return

        target_size = self.lbl_preview.size()
        
        # Scale the image while maintaining the aspect ratio.
        pixmap = QPixmap.fromImage(qt_img).scaled(
            target_size, 
            Qt.AspectRatioMode.KeepAspectRatio, 
            Qt.TransformationMode.SmoothTransformation
        )

        # Create a mask to round the corners of the camera frame.
        rounded = QPixmap(target_size)
        rounded.fill(Qt.GlobalColor.transparent)

        painter = QPainter(rounded)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        path = QPainterPath()
        path.addRoundedRect(0, 0, target_size.width(), target_size.height(), 4, 4)
        
        painter.setClipPath(path)
        # Center the scaled image within the label frame.
        x = (target_size.width() - pixmap.width()) // 2
        y = (target_size.height() - pixmap.height()) // 2
        painter.drawPixmap(x, y, pixmap)
        painter.end()

        self.lbl_preview.setPixmap(rounded)

    def on_click_apply(self):
        self.view_model.apply_changes(connect_now=self.has_open_editors)
        self.accept()

    def on_click_cancel(self):
        self.view_model.revert_changes()
        self.reject()

    def closeEvent(self, event):
        self.on_click_cancel()
