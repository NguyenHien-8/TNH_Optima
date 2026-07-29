########################################################
# @file App/Models/MediaUtils/VideoRecorderManager.py
# Author: TRAN NGUYEN HIEN
# Email: trannguyenhien29085@gmail.com
########################################################
import os
from collections import deque
from datetime import datetime
from enum import Enum

from PyQt6.QtCore import (
    QCoreApplication,
    QMutex,
    QThread,
    QWaitCondition,
    pyqtSignal,
)
from PyQt6.QtGui import QImage

from App.Infrastructure.CrashHandler import log_exception


class VideoState(Enum):
    IDLE = "idle"
    RECORDING = "recording"
    PAUSED = "paused"


class VideoRecorderThread(QThread):
    error_occurred = pyqtSignal(str)

    def __init__(self, save_path, fps=30.0, max_queue_size=5, parent=None):
        super().__init__(parent)
        self.save_path = save_path
        self.fps = fps
        self.mutex = QMutex()
        self.condition = QWaitCondition()
        self.running = True
        self.paused = False
        self.writer = None
        self.frame_queue = deque(maxlen=max_queue_size)

    def update_frame(self, qimage):
        """Copy and enqueue a frame without retaining a mutable GUI image."""
        if qimage is None or qimage.isNull():
            return
        frame_copy = qimage.copy()
        self.mutex.lock()
        try:
            if self.running:
                self.frame_queue.append(frame_copy)
                self.condition.wakeOne()
        finally:
            self.mutex.unlock()

    def pause(self):
        self.mutex.lock()
        try:
            self.paused = True
        finally:
            self.mutex.unlock()

    def resume(self):
        self.mutex.lock()
        try:
            self.paused = False
            self.condition.wakeAll()
        finally:
            self.mutex.unlock()

    def request_stop(self):
        self.mutex.lock()
        try:
            self.running = False
            self.frame_queue.clear()
            self.condition.wakeAll()
        finally:
            self.mutex.unlock()
        self.requestInterruption()

    def stop(self, timeout_ms=2000):
        """Stop synchronously; callers must invoke this outside the GUI thread."""
        self.request_stop()
        return self.wait(timeout_ms)

    def run(self):
        try:
            import cv2

            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            while not self.isInterruptionRequested():
                self.mutex.lock()
                try:
                    if not self.running:
                        break
                    if self.paused or not self.frame_queue:
                        self.condition.wait(self.mutex, 100)
                        continue

                    # Drop stale frames when encoding falls behind capture.
                    while len(self.frame_queue) > 1:
                        self.frame_queue.popleft()
                    qimage = self.frame_queue.popleft()
                finally:
                    self.mutex.unlock()

                frame_bgr = self._qimage_to_bgr_numpy(qimage)
                if frame_bgr is None:
                    continue

                if self.writer is None:
                    height, width = frame_bgr.shape[:2]
                    self.writer = cv2.VideoWriter(
                        self.save_path,
                        fourcc,
                        self.fps,
                        (width, height),
                    )
                    if not self.writer.isOpened():
                        raise OSError(
                            f"Cannot open video output: {self.save_path}"
                        )
                self.writer.write(frame_bgr)
        except Exception as exc:
            log_exception("Video recorder failed")
            self.error_occurred.emit(f"{type(exc).__name__}: {exc}")
        finally:
            if self.writer is not None:
                self.writer.release()
                self.writer = None

    @staticmethod
    def _qimage_to_bgr_numpy(qimage):
        if qimage is None or qimage.isNull():
            return None
        import cv2
        import numpy as np

        rgb_image = qimage.convertToFormat(QImage.Format.Format_RGB888)
        width = rgb_image.width()
        height = rgb_image.height()
        bytes_per_line = rgb_image.bytesPerLine()
        ptr = rgb_image.bits()
        ptr.setsize(height * bytes_per_line)
        rgb = np.frombuffer(ptr, dtype=np.uint8).reshape(
            height, bytes_per_line
        )[:, : width * 3].reshape(height, width, 3)
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


class FolderManager:
    @staticmethod
    def ensure_folder_exists(folder_path):
        try:
            os.makedirs(folder_path, exist_ok=True)
            return True, f"Folder ready: {folder_path}"
        except OSError as exc:
            return False, f"Cannot create folder: {exc}"


class VideoRecorderManager:
    def __init__(self, item_path):
        self.item_path = item_path
        self.video_folder = os.path.join(item_path, "Video")

        self.video_thread = None
        self.video_state = VideoState.IDLE
        self.current_video_path = None
        self._last_error = None

    def start_video(self, fps=20.0):
        if self.video_state != VideoState.IDLE:
            return False, "", "Video is already recording or paused"

        try:
            if not os.path.isdir(self.item_path):
                return False, "", "Item path is invalid or does not exist"

            success, message = FolderManager.ensure_folder_exists(
                self.video_folder
            )
            if not success:
                return False, "", message

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            filename = f"video_{timestamp}.mp4"
            self.current_video_path = os.path.join(
                self.video_folder, filename
            )
            self._last_error = None

            # QApplication owns the wrapper until deleteLater() runs, even when
            # an editor closes while the native recorder loop is winding down.
            worker = VideoRecorderThread(
                self.current_video_path,
                fps=fps,
                parent=QCoreApplication.instance(),
            )
            worker.error_occurred.connect(self._remember_error)
            self.video_thread = worker
            worker.start()
            self.video_state = VideoState.RECORDING
            return True, filename, f"Recording started: {filename}"
        except Exception as exc:
            self.video_state = VideoState.IDLE
            return False, "", f"Error starting video recording: {exc}"

    def _remember_error(self, message):
        self._last_error = message

    def pause_video(self):
        if self.video_state == VideoState.RECORDING and self.video_thread:
            self.video_thread.pause()
            self.video_state = VideoState.PAUSED
            return True
        return False

    def resume_video(self):
        if self.video_state == VideoState.PAUSED and self.video_thread:
            self.video_thread.resume()
            self.video_state = VideoState.RECORDING
            return True
        return False

    def stop_video(self):
        worker = self.video_thread
        if worker is None or self.video_state == VideoState.IDLE:
            return False, "", "No video is currently recording"

        try:
            if not worker.stop():
                return (
                    False,
                    "",
                    "Video recorder did not stop within 2 seconds",
                )
            worker.deleteLater()
            self.video_thread = None
            self.video_state = VideoState.IDLE

            if self._last_error:
                return False, "", self._last_error
            if self.current_video_path and os.path.isfile(
                self.current_video_path
            ):
                filename = os.path.basename(self.current_video_path)
                return (
                    True,
                    filename,
                    f"Video saved successfully: {filename}",
                )
            return False, "", "Video recording stopped but file not found"
        except Exception as exc:
            self.video_state = VideoState.IDLE
            return False, "", f"Error stopping video: {exc}"

    def get_video_state(self):
        return self.video_state.value

    def is_recording(self):
        return self.video_state != VideoState.IDLE

    def update_video_frame(self, qimage):
        if self.video_state == VideoState.RECORDING and self.video_thread:
            self.video_thread.update_frame(qimage)

    def close(self):
        """Request shutdown without waiting on the GUI thread."""
        worker = self.video_thread
        self.video_thread = None
        self.video_state = VideoState.IDLE
        if worker is None:
            return
        if worker.isRunning():
            worker.finished.connect(worker.deleteLater)
            worker.request_stop()
        else:
            worker.deleteLater()
