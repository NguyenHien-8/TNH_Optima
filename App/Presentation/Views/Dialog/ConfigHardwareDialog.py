##############################################################
# @file App/Presentation/Views/Dialog/ConfigHardwareDialog.py
# Author: TRAN NGUYEN HIEN
# Email: trannguyenhien29085@gmail.com
##############################################################
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QComboBox, QLineEdit, QPushButton, QStyle,
                             QFrame, QSpacerItem, QSizePolicy, QMessageBox)
from PyQt6.QtCore import Qt

from App.Presentation.ViewModels.DialogViewModel.ConfigHardwareViewModel import ConfigHardwareViewModel
from App.Infrastructure.Helpers.ResourceHelper import apply_stylesheet

class ConfigHardwareDialog(QDialog):
    @property
    def _workers(self):
        """Compatibility view; worker ownership remains in the ViewModel."""
        return self.view_model._workers

    def __init__(self, hardware_view_model, parent=None):
        super().__init__(parent)

        self.view_model = (
            hardware_view_model
            if isinstance(hardware_view_model, ConfigHardwareViewModel)
            else ConfigHardwareViewModel(hardware_view_model)
        )
        self._close_when_idle = False
        self._port_before_scan = ""

        self.input_height = 28
        self.input_min_width = 180
        self.port_width = 180
        self.baud_width = 150
        self.setWindowTitle("Hardware Configuration")
        self.setFixedWidth(300)

        self.load_hardware_dialog_style()   
        self.setup_ui()
        self.view_model.ports_scanned.connect(self._on_ports_scanned)
        self.view_model.connection_completed.connect(
            self._on_connection_finished
        )
        self.view_model.error_occurred.connect(self._on_worker_error)
        self.view_model.workers_idle.connect(self._on_workers_idle)
        self.load_current_settings()

    def load_hardware_dialog_style(self):
        apply_stylesheet(self, "HardwareDialogStyles.qss")

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 10)
        main_layout.setSpacing(8)

        # Row 1: Port
        row1_layout = QHBoxLayout()
        lbl_port = QLabel("Port:")
        lbl_port.setFixedWidth(40)
        self.combo_port = QComboBox()
        self.combo_port.setFixedHeight(self.input_height)
        self.combo_port.setFixedWidth(self.port_width)
        self.combo_port.setEditable(True)
        self.btn_refresh = QPushButton()
        self.btn_refresh.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload))
        self.btn_refresh.setFixedSize(self.input_height + 4, self.input_height + 4)
        self.btn_refresh.clicked.connect(self.refresh_ports)
        row1_layout.addWidget(lbl_port)
        row1_layout.addWidget(self.combo_port)
        row1_layout.addWidget(self.btn_refresh)
        row1_layout.addStretch()

        # Row 2: Baud
        row2_layout = QHBoxLayout()
        lbl_baud = QLabel("Baud:")
        lbl_baud.setFixedWidth(40)
        self.combo_baud = QComboBox()
        baud_rates = ["9600", "14400", "19200", "38400", "57600", "115200"]
        self.combo_baud.addItems(baud_rates)
        self.combo_baud.setFixedHeight(self.input_height)
        self.combo_baud.setMinimumWidth(self.input_min_width)
        self.combo_baud.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.combo_baud.setEditable(True)
        row2_layout.addWidget(lbl_baud)
        row2_layout.addWidget(self.combo_baud)
        row2_layout.addSpacerItem(QSpacerItem(self.input_height + 4, self.input_height + 4, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum))
        row2_layout.addStretch()

        # Row 3: Period
        row3_layout = QHBoxLayout()
        lbl_period = QLabel("Status Query Period:")
        lbl_period.setFixedWidth(130)
        self.txt_period = QLineEdit()
        self.txt_period.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        lbl_ms = QLabel("ms")
        lbl_ms.setStyleSheet("color: #555555;")
        row3_layout.addWidget(lbl_period)
        row3_layout.addWidget(self.txt_period)
        row3_layout.addWidget(lbl_ms)
        row3_layout.addSpacerItem(QSpacerItem(32, 0, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum))

        main_layout.addLayout(row1_layout)
        main_layout.addLayout(row2_layout)
        main_layout.addLayout(row3_layout)
        main_layout.addStretch()

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Plain)
        line.setFixedHeight(2)
        line.setStyleSheet("border-top: 1px solid #7A7A7A;")
        main_layout.addWidget(line)
        main_layout.addSpacing(5)

        row4_layout = QHBoxLayout()
        row4_layout.addSpacerItem(QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        self.btn_apply = QPushButton("Apply and Close")
        self.btn_apply.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_apply.clicked.connect(self.on_apply)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.clicked.connect(self.on_cancel)
        row4_layout.addWidget(self.btn_apply)
        row4_layout.addWidget(self.btn_cancel)
        main_layout.addLayout(row4_layout)

    def load_current_settings(self):
        self.refresh_ports()
        config = self.view_model.get_current_config()

        current_port = config.get("port", "")
        if current_port:
            self.combo_port.setEditText(str(current_port))
        baud_str = str(config.get("baud", 115200))
        self.combo_baud.setEditText(baud_str)
        self.txt_period.setText(str(config.get("query_period", "")))

    def refresh_ports(self):
        self._port_before_scan = self.combo_port.currentText()
        self.combo_port.clear()
        self.combo_port.setPlaceholderText("Scanning...")
        self.btn_refresh.setEnabled(False)
        self.view_model.scan_ports()

    def _on_ports_scanned(self, ports):
        self.combo_port.addItems(ports)
        if self._port_before_scan:
            self.combo_port.setEditText(self._port_before_scan)
        self.combo_port.setPlaceholderText("Select port...")
        self.btn_refresh.setEnabled(True)

    def _on_worker_error(self, message):
        self.btn_refresh.setEnabled(True)
        self.btn_apply.setEnabled(True)
        self.btn_cancel.setEnabled(True)
        QMessageBox.critical(self, "Hardware Error", message.splitlines()[0])

    def on_apply(self):
        try:
            baud_text = self.combo_baud.currentText().strip()
            if not baud_text:
                baud = 115200 # Default safe
            else:
                baud = int(baud_text)
        except ValueError:
            QMessageBox.warning(self, "Invalid Input", "Baud rate must be a number.")
            return

        port = self.combo_port.currentText().strip()
        if not port:
             QMessageBox.warning(self, "Warning", "Please select a serial port.")
             return

        period = self.txt_period.text().strip()
        self.btn_apply.setEnabled(False)
        self.btn_cancel.setEnabled(False)
        self.btn_apply.setText("Connecting...")
        self.view_model.apply_connection(
            port,
            baud,
            period,
        )

    def _on_connection_finished(self, port, result):
        self.btn_apply.setText("Apply and Close")
        self.btn_apply.setEnabled(True)
        self.btn_cancel.setEnabled(True)
        success, message = result
        if success:
            self.accept()
            return
        QMessageBox.critical(
            self,
            "Connection Failed",
            f"Could not connect to {port}.\n\nError Detail:\n{message}",
        )

    def on_cancel(self):
        if self.view_model.is_busy():
            return
        self.reject()

    def closeEvent(self, event):
        if not self.view_model.request_close():
            self._close_when_idle = True
            event.ignore()
            return
        super().closeEvent(event)

    def _on_workers_idle(self):
        self.btn_refresh.setEnabled(True)
        if self._close_when_idle:
            self._close_when_idle = False
            self.close()
