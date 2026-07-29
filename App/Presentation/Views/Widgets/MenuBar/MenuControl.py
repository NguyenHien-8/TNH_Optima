###############################################################
# @file App/Presentation/Views/Widgets/MenuBar/MenuControl.py
# Author: TRAN NGUYEN HIEN
# Email: trannguyenhien29085@gmail.com
###############################################################
import os
import sys
from PyQt6.QtWidgets import QMenu, QStyle, QMessageBox
from PyQt6.QtGui import QAction, QKeySequence, QIcon
from App.Infrastructure.Helpers.ResourceHelper import resource_path

class MenuControl(QMenu):
    def __init__(self, parent_window):
        super().__init__("Control", parent_window)
        self.parent_window = parent_window
        self.setup_actions()

    def setup_actions(self):
        style = self.style()
        icon_base_path = resource_path(os.path.join("App", "ReSource", "Icon", "MenuControl"))

        def get_icon(filename):
            path = os.path.join(icon_base_path, filename)
            if os.path.exists(path):
                return QIcon(path)
            return QIcon()
        
        def add(text, method, icon_filename, shortcut=None, target_menu=None):
            icon = get_icon(icon_filename)
            action = QAction(icon, text, self)
            if shortcut:
                action.setShortcut(QKeySequence(shortcut))
            action.triggered.connect(method)
            if target_menu:
                target_menu.addAction(action)
            else:
                self.addAction(action)
        
        add("Motor Control", self.on_motor_control, "filter.svg")
        add("Control Panel", self.on_open_file_editor, "control_panel.svg")

        # act_motor = QAction(
        #     style.standardIcon(QStyle.StandardPixmap.SP_MediaPlay),
        #     "Motor Control",
        #     self
        # )
        # act_motor.triggered.connect(self.on_motor_control)
        # self.addAction(act_motor)

        # act_file_editor = QAction(
        #     style.standardIcon(QStyle.StandardPixmap.SP_FileIcon),
        #     "Control Panel",
        #     self
        # )
        # act_file_editor.triggered.connect(self.on_open_file_editor)
        # self.addAction(act_file_editor)

    def on_motor_control(self):
        from App.Presentation.Views.Dialog.MotorControlDialog import MotorControlDialog

        view_model = (
            self.parent_window.view_model.create_motor_control_view_model()
        )
        dialog = MotorControlDialog(view_model, self.parent_window)
        dialog.exec()

    def on_open_file_editor(self):
        if hasattr(self.parent_window, "open_file_editor_from_menu"):
            self.parent_window.open_file_editor_from_menu()
        else:
            QMessageBox.warning(
                self.parent_window,
                "File Editor",
                "Main window does not support opening File Editor from menu."
            )
