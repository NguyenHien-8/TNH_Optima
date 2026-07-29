########################################################
# @file App/Models/Vision/CameraFrameDispatcher.py
# Author: TRAN NGUYEN HIEN
# Email: trannguyenhien29085@gmail.com
########################################################
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QImage
from App.Infrastructure.CrashHandler import log_exception


class CameraFrameDispatcher(QObject):
    dispatch_error = pyqtSignal(str)

    def __init__(self, camera_manager):
        super().__init__()
        self._camera_manager = camera_manager
        self._active_view_model = None
        self._last_frame = None

        self._camera_manager.frame_received_signal.connect(self._on_camera_frame)

    @pyqtSlot(QImage)
    def _on_camera_frame(self, qimage: QImage):
        self._last_frame = qimage
        if self._active_view_model is not None:
            self._deliver_frame(self._active_view_model, qimage)

    def set_active_view_model(self, view_model):
        if view_model is not None and not callable(
            getattr(view_model, "receive_frame", None)
        ):
            self.dispatch_error.emit(
                "The active editor cannot receive camera frames."
            )
            view_model = None
        self._active_view_model = view_model
        if self._active_view_model is not None and self._last_frame is not None:
            self._deliver_frame(self._active_view_model, self._last_frame)

    def is_active_view_model(self, view_model):
        return self._active_view_model is view_model

    def _deliver_frame(self, view_model, image):
        try:
            view_model.receive_frame(image)
        except Exception as exc:
            log_exception("Camera frame delivery failed")
            self._active_view_model = None
            self.dispatch_error.emit(f"Camera frame dispatch stopped: {exc}")
