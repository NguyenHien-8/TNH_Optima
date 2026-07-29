########################################################
# @file App/Models/Vision/CameraManager.py
# Author: TRAN NGUYEN HIEN
# Email: trannguyenhien29085@gmail.com
########################################################
from PyQt6.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QImage


class CameraManager(QObject):
    frame_received_signal = pyqtSignal(QImage)
    preview_signal = pyqtSignal(QImage)
    camera_list_signal = pyqtSignal(list)
    error_occurred_signal = pyqtSignal(str)
    status_message_signal = pyqtSignal(str)
    fps_updated = pyqtSignal(float)
    shutdown_ready = pyqtSignal()

    MIN_WIDTH, MIN_HEIGHT = 480, 360
    MAX_WIDTH, MAX_HEIGHT = 960, 576
    DEFAULT_WIDTH, DEFAULT_HEIGHT = 640, 480
    MAX_RETRIES = 5

    def __init__(self):
        super().__init__()
        self.current_thread = None
        self.scan_thread = None
        self.active_camera_index = None
        self.resolution = (self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT)
        self.retry_count = 0
        self._preview_mode = False
        self.current_fps = 30.0
        self._ref_count = 0
        self._pending_camera_index = None
        self._shutting_down = False
        self.available_cameras = []

        self._retry_timer = QTimer(self)
        self._retry_timer.setSingleShot(True)
        self._retry_timer.timeout.connect(self._retry_camera)

    def set_preview_mode(self, is_preview: bool):
        self._preview_mode = bool(is_preview)

    def set_resolution(self, width, height):
        try:
            width, height = int(width), int(height)
        except (TypeError, ValueError):
            self.status_message_signal.emit("Resolution must contain integer values.")
            return
        if width < self.MIN_WIDTH or height < self.MIN_HEIGHT:
            self.status_message_signal.emit(
                f"Resolution too low. Min: {self.MIN_WIDTH}x{self.MIN_HEIGHT}"
            )
            return
        if width > self.MAX_WIDTH or height > self.MAX_HEIGHT:
            self.status_message_signal.emit(
                f"Resolution too high. Max: {self.MAX_WIDTH}x{self.MAX_HEIGHT}"
            )
            return
        self.resolution = (width, height)
        self.status_message_signal.emit(
            f"Resolution set to {width}x{height}. Restart camera to apply."
        )
        if self.active_camera_index is not None:
            self.change_camera(self.active_camera_index)

    def get_camera_name(self, cam_idx):
        for camera in self.available_cameras:
            if isinstance(camera, dict) and camera.get("index") == cam_idx:
                return camera.get("name", f"Camera {cam_idx}")
        return f"Camera {cam_idx}"

    def scan_cameras(self):
        if self._shutting_down:
            return
        if self.scan_thread is not None and self.scan_thread.isRunning():
            return

        # The worker imports OpenCV in run(), keeping it off the GUI startup path.
        from App.Models.Vision.HardwareCameraScan import HardwareCameraScan

        self.status_message_signal.emit("Scanning devices...")
        worker = HardwareCameraScan(skip_index=self.active_camera_index)
        self.scan_thread = worker
        worker.cameras_found_signal.connect(self._on_scan_finished)
        worker.error_signal.connect(self._on_scan_warning)
        worker.finished.connect(self._on_scan_thread_finished)
        worker.start()

    def change_camera(self, target_cam_idx):
        if target_cam_idx is None:
            self.stop_current_camera()
            self.status_message_signal.emit("Please select a Camera.")
            return
        if self._shutting_down:
            return

        if not self.available_cameras:
            self.scan_cameras()

        self.retry_count = 0
        self._retry_timer.stop()
        self._pending_camera_index = target_cam_idx
        self.status_message_signal.emit(f"Connecting Camera {target_cam_idx}...")

        if self.current_thread is not None and self.current_thread.isRunning():
            self._request_camera_stop()
        else:
            self._start_pending_camera()

    def stop_current_camera(self):
        self._pending_camera_index = None
        self._retry_timer.stop()
        self._request_camera_stop()

    def _request_camera_stop(self):
        worker = self.current_thread
        if worker is None:
            return
        try:
            worker.change_pixmap_signal.disconnect(self._on_frame_routed)
            worker.error_signal.disconnect(self._on_camera_error_internal)
            worker.fps_signal.disconnect(self._on_fps_updated)
        except (TypeError, RuntimeError):
            pass
        worker.stop_camera()

    def stop_scan(self):
        if self.scan_thread is not None and self.scan_thread.isRunning():
            self.scan_thread.requestInterruption()

    def cleanup(self, wait_ms=0):
        """Request cooperative shutdown without blocking the caller by default."""
        self._shutting_down = True
        self._retry_timer.stop()
        self.stop_current_camera()
        self.stop_scan()
        is_idle = not any(
            worker is not None and worker.isRunning()
            for worker in (self.current_thread, self.scan_thread)
        )
        if is_idle:
            self.shutdown_ready.emit()
        return is_idle

    def _emit_shutdown_ready_if_idle(self):
        if (
            self._shutting_down
            and self.current_thread is None
            and self.scan_thread is None
        ):
            self.shutdown_ready.emit()

    def _start_camera_thread(self, cam_idx):
        if self._shutting_down or cam_idx is None:
            return
        from App.Models.Vision.CameraThread import CameraThread

        worker = CameraThread(cam_idx, resolution=self.resolution)
        self.active_camera_index = cam_idx
        self.current_thread = worker
        worker.change_pixmap_signal.connect(self._on_frame_routed)
        worker.error_signal.connect(self._on_camera_error_internal)
        worker.fps_signal.connect(self._on_fps_updated)
        worker.finished.connect(self._on_camera_thread_finished)
        worker.start()

    def _start_pending_camera(self):
        target = self._pending_camera_index
        self._pending_camera_index = None
        if target is not None and not self._shutting_down:
            self._start_camera_thread(target)

    @pyqtSlot()
    def _on_camera_thread_finished(self):
        worker = self.sender()
        if worker is self.current_thread:
            self.current_thread = None
        if worker is not None:
            worker.deleteLater()
        self._start_pending_camera()
        self._emit_shutdown_ready_if_idle()

    @pyqtSlot(float)
    def _on_fps_updated(self, fps):
        self.current_fps = fps
        self.fps_updated.emit(fps)

    @pyqtSlot(list)
    def _on_scan_finished(self, cameras):
        valid_cameras = [
            camera
            for camera in cameras
            if isinstance(camera, dict) and isinstance(camera.get("index"), int)
        ]
        valid_cameras.sort(key=lambda camera: camera["index"])
        self.available_cameras = valid_cameras
        self.camera_list_signal.emit(valid_cameras)

        if self.active_camera_index is not None:
            found_indices = {camera["index"] for camera in valid_cameras}
            if self.active_camera_index not in found_indices:
                lost_idx = self.active_camera_index
                self.status_message_signal.emit(f"Camera {lost_idx} disconnected.")
                self.stop_current_camera()
                self.active_camera_index = None
                self.error_occurred_signal.emit(
                    f"Lost connection to Camera {lost_idx}"
                )

    @pyqtSlot(str)
    def _on_scan_warning(self, message):
        self.status_message_signal.emit(message)

    @pyqtSlot()
    def _on_scan_thread_finished(self):
        worker = self.sender()
        if worker is self.scan_thread:
            self.scan_thread = None
        if worker is not None:
            worker.deleteLater()
        self._emit_shutdown_ready_if_idle()

    @pyqtSlot(QImage)
    def _on_frame_routed(self, image):
        if self.retry_count > 0:
            self.retry_count = 0
        if self._preview_mode:
            self.preview_signal.emit(image)
        else:
            self.frame_received_signal.emit(image)

    @pyqtSlot(str)
    def _on_camera_error_internal(self, message):
        if self._shutting_down:
            return
        self.error_occurred_signal.emit(message)
        self.retry_count += 1

        if self.retry_count > self.MAX_RETRIES:
            self.status_message_signal.emit(
                "Max retries reached. Stopping camera reconnect."
            )
            self.stop_current_camera()
            self.active_camera_index = None
            return

        self.status_message_signal.emit(
            f"Retry attempt {self.retry_count}/{self.MAX_RETRIES}..."
        )
        self._pending_camera_index = None
        self._request_camera_stop()
        self._retry_timer.start(1000)

    @pyqtSlot()
    def _retry_camera(self):
        if self.active_camera_index is None or self._shutting_down:
            return
        self._pending_camera_index = self.active_camera_index
        if self.current_thread is None or not self.current_thread.isRunning():
            self._start_pending_camera()

    def get_fps(self):
        return self.current_fps

    def ensure_connected(self, cam_index=None):
        if cam_index is None:
            cam_index = self.active_camera_index
        if cam_index is None:
            self.status_message_signal.emit("No camera selected.")
            return
        if (
            self.current_thread is not None
            and self.current_thread.isRunning()
            and self.active_camera_index == cam_index
        ):
            return
        self.change_camera(cam_index)

    def acquire(self):
        self._ref_count += 1
        self.status_message_signal.emit(
            f"Camera acquired. Ref count: {self._ref_count}"
        )
        if self._ref_count == 1:
            self.ensure_connected()

    def release(self):
        if self._ref_count == 0:
            self.status_message_signal.emit(
                "Ignored an unmatched camera release request."
            )
            return
        self._ref_count -= 1
        self.status_message_signal.emit(
            f"Camera released. Ref count: {self._ref_count}"
        )
        if self._ref_count == 0:
            self.stop_current_camera()
