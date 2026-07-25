#############################################################################
# @file App/Presentation/ViewModels/FeatureViewModel/ImageEditorViewModel.py
# Author: TRAN NGUYEN HIEN
# Email: trannguyenhien29085@gmail.com
#############################################################################
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap
from App.Presentation.ViewModels.Workers import FunctionWorker

class ImageEditorViewModel(QObject):
    image_loaded = pyqtSignal(QPixmap)
    error_occurred = pyqtSignal(str)
    workers_idle = pyqtSignal()
    loading_changed = pyqtSignal(str, bool)

    def __init__(self, project_name=None, item_name=None):
        super().__init__()
        self.project_name = project_name
        self.item_name = item_name
        self.current_image_path = None
        self.current_pixmap = None
        self._workers = set()

    def load_image(self, file_path):
        if not isinstance(file_path, str) or not file_path:
            self.error_occurred.emit("Invalid image path.")
            return
        self._start_worker(
            lambda: QImage(file_path),
            lambda image: self._on_image_decoded(file_path, image),
            track_loading=True,
        )

    def _on_image_decoded(self, file_path, image):
        if image.isNull():
            self.error_occurred.emit(f"Cannot load image: {file_path}")
            return
        self.current_image_path = file_path
        self.current_pixmap = QPixmap.fromImage(image)
        self.image_loaded.emit(self.current_pixmap)

    def save_image(self, file_path):
        """Save the current pixmap to the given file path."""
        if self.current_pixmap and not self.current_pixmap.isNull():
            image = self.current_pixmap.toImage()

            def on_saved(success):
                if not success:
                    self.error_occurred.emit(f"Failed to save image to {file_path}")

            self._start_worker(lambda: image.save(file_path), on_saved)
        else:
            self.error_occurred.emit("No image loaded to save.")

    def _start_worker(self, function, callback, track_loading=False):
        worker = FunctionWorker(function)
        self._workers.add(worker)
        if track_loading:
            loading_token = f"image-worker:{id(worker)}"
            self.loading_changed.emit(loading_token, True)
            worker.finished.connect(
                lambda token=loading_token: self.loading_changed.emit(
                    token,
                    False,
                )
            )
        worker.result_ready.connect(callback)
        worker.error_occurred.connect(self.error_occurred)
        worker.finished.connect(lambda: self._finish_worker(worker))
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _finish_worker(self, worker):
        self._workers.discard(worker)
        if not any(item.isRunning() for item in self._workers):
            self.workers_idle.emit()

    def close(self):
        self.request_shutdown()

    def request_shutdown(self):
        for worker in list(self._workers):
            if worker.isRunning():
                worker.requestInterruption()

    def has_running_workers(self):
        return any(worker.isRunning() for worker in self._workers)
