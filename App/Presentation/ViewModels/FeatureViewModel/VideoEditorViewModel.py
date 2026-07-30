#############################################################################
# @file App/Presentation/ViewModels/FeatureViewModel/VideoEditorViewModel.py
# Author: TRAN NGUYEN HIEN
# Email: trannguyenhien29085@gmail.com
#############################################################################
import os

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QImage

from App.Presentation.ViewModels.RecentDirectoryState import (
    RecentDirectoryState,
)
from App.Presentation.ViewModels.Workers import FunctionWorker


class VideoEditorViewModel(QObject):
    """Validate video sources away from the GUI thread."""

    OPEN_DIRECTORY = "video_open"
    CAPTURE_DIRECTORY = "video_capture"
    _DIRECTORY_PURPOSES = frozenset(
        (OPEN_DIRECTORY, CAPTURE_DIRECTORY)
    )

    source_ready = pyqtSignal(str)
    source_error = pyqtSignal(str)
    capture_saved = pyqtSignal(str, object)
    capture_error = pyqtSignal(str)
    workers_idle = pyqtSignal()

    def __init__(
        self,
        file_path=None,
        parent=None,
        recent_directory_provider=None,
        recent_directory_recorder=None,
    ):
        super().__init__(parent)
        self.file_path = file_path
        self._recent_directory_state = RecentDirectoryState(
            self._DIRECTORY_PURPOSES,
            recent_directory_provider,
            recent_directory_recorder,
        )
        self._generation = 0
        self._workers = set()
        self._validation_workers = set()

    def set_video(self, file_path):
        self.cancel_pending()
        self.file_path = file_path

    def get_dialog_directory(self, purpose, fallback_path=None):
        """Return the independent Open Video or Capture Image directory."""
        return self._recent_directory_state.get(
            purpose,
            current_path=self.file_path,
            fallback_path=fallback_path,
        )

    def remember_media_path(self, path, purpose):
        """Remember a successful VideoEditor open or capture location."""
        self._recent_directory_state.remember(purpose, path)

    def cancel_pending(self):
        self._generation += 1
        for worker in list(self._validation_workers):
            if worker.isRunning():
                worker.requestInterruption()

    def validate_source(self):
        if any(worker.isRunning() for worker in self._validation_workers):
            return False

        generation = self._generation
        file_path = self.file_path
        worker = FunctionWorker(self._inspect_source, file_path)
        self._workers.add(worker)
        self._validation_workers.add(worker)
        worker.result_ready.connect(
            lambda result: self._on_source_inspected(generation, result)
        )
        worker.error_occurred.connect(self.source_error)
        worker.finished.connect(lambda: self._finish_worker(worker))
        worker.finished.connect(worker.deleteLater)
        worker.start()
        return True

    @staticmethod
    def _inspect_source(file_path):
        if not isinstance(file_path, str) or not file_path:
            return None
        normalized_path = os.path.abspath(file_path)
        if not os.path.isfile(normalized_path):
            return None
        # stat() forces potentially slow network/removable-drive metadata IO to
        # finish in this worker before Qt Multimedia receives the source.
        os.stat(normalized_path)
        return normalized_path

    def _on_source_inspected(self, generation, file_path):
        if generation != self._generation:
            return
        if file_path is None:
            self.source_error.emit(
                "The selected video file is no longer available."
            )
            return
        self.source_ready.emit(file_path)

    def save_capture(self, image, file_path, item_path=None, image_folder=None):
        if not isinstance(image, QImage) or image.isNull():
            self.capture_error.emit("Cannot capture image from video.")
            return False

        image_copy = image.copy()

        def save_image():
            if image_folder:
                os.makedirs(image_folder, exist_ok=True)
            if not image_copy.save(file_path, "PNG"):
                raise OSError(f"Cannot save image file to '{file_path}'")
            return file_path, item_path

        worker = FunctionWorker(save_image)
        self._workers.add(worker)
        worker.result_ready.connect(self._on_capture_saved)
        worker.error_occurred.connect(self.capture_error)
        worker.finished.connect(lambda: self._finish_worker(worker))
        worker.finished.connect(worker.deleteLater)
        worker.start()
        return True

    def _on_capture_saved(self, result):
        file_path, item_path = result
        self.remember_media_path(file_path, self.CAPTURE_DIRECTORY)
        self.capture_saved.emit(file_path, item_path)

    def _finish_worker(self, worker):
        self._workers.discard(worker)
        self._validation_workers.discard(worker)
        if not any(item.isRunning() for item in self._workers):
            self.workers_idle.emit()

    def request_shutdown(self):
        self.cancel_pending()
        for worker in list(self._workers):
            if worker.isRunning():
                worker.requestInterruption()

    def has_running_workers(self):
        return any(worker.isRunning() for worker in self._workers)

    def close(self):
        self.request_shutdown()
