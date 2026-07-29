###############################################################################
# @file App/Presentation/ViewModels/DialogViewModel/ConfigCameraViewModel.py
# Author: TRAN NGUYEN HIEN
# Email: trannguyenhien29085@gmail.com
###############################################################################
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QImage
from App.Models.CamHardwareManager import CameraConfigBackend
from App.Presentation.ViewModels.Workers import FunctionWorker

class ConfigCameraViewModel(QObject):
    camera_list_updated = pyqtSignal(list)
    preview_frame_received = pyqtSignal(QImage)
    apply_completed = pyqtSignal()
    error_occurred = pyqtSignal(str)
    workers_idle = pyqtSignal()

    def __init__(self, camera_manager):
        super().__init__()
        self.backend = CameraConfigBackend(camera_manager)
        self._workers = set()
        self._connect_signals()

    def _connect_signals(self):
        self.backend.camera_manager.camera_list_signal.connect(self.camera_list_updated)
        self.backend.camera_manager.preview_signal.connect(self.preview_frame_received)

    def scan_cameras(self):
        self.backend.scan_cameras()

    def set_selected_camera(self, index):
        self.backend.set_selected_camera(index)

    def get_selected_camera(self):
        return self.backend.get_selected_camera()
    
    def get_original_camera_id(self):     
        return self.backend.original_camera_id

    def connect_preview(self, cam_idx):
        self.backend.connect_preview(cam_idx)

    def stop_preview(self):
        self.backend.stop_preview()

    def apply_changes(self, connect_now=False):
        if self.is_busy():
            return False
        selected_camera_id = self.backend.get_selected_camera()
        worker = FunctionWorker(
            self.backend.save_selected_camera,
            selected_camera_id,
        )
        self._workers.add(worker)
        worker.result_ready.connect(
            lambda _result: self._on_config_saved(connect_now)
        )
        worker.error_occurred.connect(self.error_occurred)
        worker.finished.connect(lambda: self._finish_worker(worker))
        worker.finished.connect(worker.deleteLater)
        worker.start()
        return True

    def _on_config_saved(self, connect_now):
        self.backend.apply_runtime_changes(connect_now)
        self.apply_completed.emit()

    def _finish_worker(self, worker):
        self._workers.discard(worker)
        if not self._workers:
            self.workers_idle.emit()

    def is_busy(self):
        return any(worker.isRunning() for worker in self._workers)

    def request_close(self):
        running_workers = [
            worker for worker in self._workers if worker.isRunning()
        ]
        for worker in running_workers:
            worker.requestInterruption()
        return not running_workers

    def revert_changes(self):
        self.backend.revert_changes()
