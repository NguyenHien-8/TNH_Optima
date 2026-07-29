##############################################################
# @file App/Presentation/Views/Dialog/MotorControlDialog.py
# Author: TRAN NGUYEN HIEN
# Email: trannguyenhien29085@gmail.com
##############################################################
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QComboBox, QFrame, QMessageBox)
from PyQt6.QtCore import Qt

from App.Presentation.ViewModels.DialogViewModel.MotorControlViewModel import MotorControlViewModel
from App.Infrastructure.Helpers.ResourceHelper import apply_stylesheet

class MotorControlDialog(QDialog):
    @property
    def _command_queue(self):
        """Compatibility view; command ownership remains in the ViewModel."""
        return self.view_model._command_queue

    @property
    def _command_worker(self):
        return self.view_model._command_worker

    def __init__(self, motor_view_model, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Motor Control Panel")
        self.setFixedSize(320, 250)

        self.view_model = (
            motor_view_model
            if isinstance(motor_view_model, MotorControlViewModel)
            else MotorControlViewModel(motor_view_model)
        )
        self._close_when_idle = False
        self.view_model.command_completed.connect(self._show_result)
        self.view_model.workers_idle.connect(self._on_workers_idle)
        self.setup_ui()
        self.load_motor_dialog_style()

    def load_motor_dialog_style(self):
        apply_stylesheet(self, "MotorControlDialog.qss")

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 10, 10, 10)
        main_layout.setSpacing(10)

        content_layout = QHBoxLayout()
        content_layout.setSpacing(25)

        # Left column: Input
        input_layout = QVBoxLayout()
        input_layout.setSpacing(15)

        # Row Height
        row_height = QHBoxLayout()
        row_height.setSpacing(10)
        lbl_height = QLabel("Height:")
        lbl_height.setFixedWidth(60)
        lbl_height.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.combo_height = QComboBox()
        self.combo_height.setEditable(True)
        self.combo_height.addItems(["2", "5", "10", "20", "50"])
        self.combo_height.setFixedSize(120, 28)
        lbl_unit_mm = QLabel("mm")
        lbl_unit_mm.setFixedWidth(30)
        row_height.addWidget(lbl_height)
        row_height.addWidget(self.combo_height)
        row_height.addWidget(lbl_unit_mm)
        row_height.addStretch()
        input_layout.addLayout(row_height)

        # Row Speed
        row_speed = QHBoxLayout()
        row_speed.setSpacing(10)
        lbl_speed = QLabel("Speed:")
        lbl_speed.setFixedWidth(60)
        lbl_speed.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.combo_speed = QComboBox()
        self.combo_speed.setEditable(True)
        self.combo_speed.addItems(["Slow", "Medium", "Fast"])
        self.combo_speed.setFixedSize(120, 28)
        lbl_unit_rpm = QLabel("rpm")
        lbl_unit_rpm.setFixedWidth(30)
        row_speed.addWidget(lbl_speed)
        row_speed.addWidget(self.combo_speed)
        row_speed.addWidget(lbl_unit_rpm)
        row_speed.addStretch()
        input_layout.addLayout(row_speed)

        # Right column: Control buttons
        ctrl_layout = QVBoxLayout()
        ctrl_layout.setSpacing(8)
        ctrl_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.btn_up = QPushButton("▲")
        self.btn_up.setObjectName("DirectionBtn")
        self.btn_up.setFixedSize(50, 50)
        self.btn_up.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_up.setToolTip("Move Up")
        self.btn_up.clicked.connect(self.on_click_up)

        self.btn_stop = QPushButton("⊘")
        self.btn_stop.setObjectName("StopBtn")
        self.btn_stop.setFixedSize(50, 50)
        self.btn_stop.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_stop.setToolTip("Stop Motor")
        self.btn_stop.clicked.connect(self.on_click_stop)

        self.btn_down = QPushButton("▼")
        self.btn_down.setObjectName("DirectionBtn")
        self.btn_down.setFixedSize(50, 50)
        self.btn_down.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_down.setToolTip("Move Down")
        self.btn_down.clicked.connect(self.on_click_down)

        ctrl_layout.addWidget(self.btn_up)
        ctrl_layout.addWidget(self.btn_stop)
        ctrl_layout.addWidget(self.btn_down)

        content_layout.addLayout(input_layout, 2)
        content_layout.addLayout(ctrl_layout, 1)

        main_layout.addLayout(content_layout)
        main_layout.addSpacing(10)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Plain)
        line.setFixedHeight(2)
        line.setStyleSheet("border-top: 1px solid #7A7A7A;")
        main_layout.addWidget(line)
        main_layout.addSpacing(1)

        footer = QHBoxLayout()
        footer.addStretch()
        self.btn_close = QPushButton("Close")
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.clicked.connect(self.close)
        footer.addWidget(self.btn_close)
        main_layout.addLayout(footer)

    def _show_result(self, success, message):
        if not success:
            QMessageBox.warning(self, "Command Failed", message)

    def on_click_up(self):
        h = self.combo_height.currentText()
        s = self.combo_speed.currentText()
        self.view_model.move_up(h, s)

    def on_click_down(self):
        h = self.combo_height.currentText()
        s = self.combo_speed.currentText()
        self.view_model.move_down(h, s)

    def on_click_stop(self):
        self.view_model.stop()

    def closeEvent(self, event):
        if not self.view_model.request_close():
            self._close_when_idle = True
            event.ignore()
            return
        super().closeEvent(event)

    def _on_workers_idle(self):
        if self._close_when_idle:
            self._close_when_idle = False
            self.close()
