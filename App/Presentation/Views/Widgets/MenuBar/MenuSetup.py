############################################################
# @file App/Presentation/Views/Widgets/MenuBar/MenuSetup.py
# Author: TRAN NGUYEN HIEN
# Email: trannguyenhien29085@gmail.com
############################################################
from PyQt6.QtWidgets import QMenu, QStyle
from PyQt6.QtGui import QAction

class MenuSetup(QMenu):
    def __init__(self, parent_window):
        super().__init__("Setup", parent_window)
        self.parent_window = parent_window 
        self.setup_actions()

    def setup_actions(self):
        style = self.style()

        # Hardware Connection
        act_hardware = QAction(style.standardIcon(QStyle.StandardPixmap.SP_ComputerIcon), "Hardware Configuration", self)
        act_hardware.triggered.connect(self.on_hardware)
        self.addAction(act_hardware)

        # Camera Connection
        act_camera = QAction(style.standardIcon(QStyle.StandardPixmap.SP_DriveDVDIcon), "Camera Connection", self)
        act_camera.triggered.connect(self.on_camera)
        self.addAction(act_camera)

    def on_hardware(self):
        from App.Presentation.Views.Dialog.ConfigHardwareDialog import ConfigHardwareDialog

        # Lấy hardware_manager từ view_model của MainView
        view_model = (
            self.parent_window.view_model.create_hardware_config_view_model()
        )
        dialog = ConfigHardwareDialog(view_model, self.parent_window)
        dialog.exec()

    def on_camera(self):
        from App.Presentation.Views.Dialog.ConfigCameraDialog import ConfigCameraDialog

        # Lấy camera_manager từ view_model của MainView
        view_model = (
            self.parent_window.view_model.create_camera_config_view_model()
        )
        dialog = ConfigCameraDialog(view_model, self.parent_window)
        dialog.exec()
