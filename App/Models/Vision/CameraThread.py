########################################################
# @file App/Models/Vision/CameraThread.py
# Author: TRAN NGUYEN HIEN
# Email: trannguyenhien29085@gmail.com
########################################################
import sys
from PyQt6.QtCore import QThread, pyqtSignal, QMutex, QWaitCondition
from PyQt6.QtGui import QImage

class CameraThread(QThread):
    change_pixmap_signal = pyqtSignal(QImage)
    error_signal = pyqtSignal(str)
    fps_signal = pyqtSignal(float)

    def __init__(self, camera_index=0, resolution=(640, 480)):
        super().__init__()
        self.camera_index = camera_index
        self.resolution = resolution
        self._is_running = True
        self._is_paused = False
        self.mutex = QMutex()
        self.wait_condition = QWaitCondition()
        self.fps = 30.0 
        self._latest_frame = None
        self._frame_signal_pending = False

    def stop_camera(self):
        self.mutex.lock()
        try:
            self._is_running = False
            self.wait_condition.wakeAll()
        finally:
            self.mutex.unlock()
        self.requestInterruption()

    def set_paused(self, state: bool):
        self.mutex.lock()
        try:
            self._is_paused = state
            if not state:
                self.wait_condition.wakeAll()
        finally:
            self.mutex.unlock()

    def take_latest_frame(self):
        """Return the newest frame and allow at most one more queued signal."""
        self.mutex.lock()
        try:
            image = self._latest_frame
            self._latest_frame = None
            self._frame_signal_pending = False
            return image
        finally:
            self.mutex.unlock()

    def _publish_frame(self, image):
        """Coalesce frames so Qt's GUI event queue cannot grow unbounded."""
        self.mutex.lock()
        try:
            self._latest_frame = image
            should_emit = not self._frame_signal_pending
            if should_emit:
                self._frame_signal_pending = True
        finally:
            self.mutex.unlock()
        if should_emit:
            # The receiver takes _latest_frame rather than relying on this
            # argument, which may already have been superseded.
            self.change_pixmap_signal.emit(image)

    def run(self):
        cap = None
        try:
            # OpenCV is intentionally imported in the worker, not on the UI startup path.
            import cv2

            if sys.platform.startswith("win"):
                cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
            else:
                cap = cv2.VideoCapture(self.camera_index)

            width, height = self.resolution
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

            if not cap.isOpened():
                self.error_signal.emit(f"Failed to open camera {self.camera_index}")
                return

            fps = cap.get(cv2.CAP_PROP_FPS)
            if fps is None or fps <= 0:
                fps = 30.0
            self.fps = fps
            self.fps_signal.emit(self.fps)

            while not self.isInterruptionRequested():
                self.mutex.lock()
                is_running = self._is_running
                is_paused = self._is_paused
                if is_paused and is_running:
                    self.wait_condition.wait(self.mutex, 250)
                self.mutex.unlock()

                if not is_running:
                    break
                if is_paused:
                    continue

                ret, cv_img = cap.read()
                if not ret:
                    if not self.isInterruptionRequested():
                        self.error_signal.emit(
                            f"Lost signal from Camera {self.camera_index}"
                        )
                    break

                rgb_image = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb_image.shape
                bytes_per_line = ch * w
                image = QImage(
                    rgb_image.data,
                    w,
                    h,
                    bytes_per_line,
                    QImage.Format.Format_RGB888,
                ).copy()
                self._publish_frame(image)
        except Exception as exc:
            if not self.isInterruptionRequested():
                self.error_signal.emit(
                    f"Camera {self.camera_index} failed: {type(exc).__name__}: {exc}"
                )
        finally:
            if cap is not None:
                cap.release()
