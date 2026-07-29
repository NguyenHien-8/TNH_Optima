#############################################################################
# @file App/Presentation/ViewModels/FeatureViewModel/ImageEditorViewModel.py
# Author: TRAN NGUYEN HIEN
# Email: trannguyenhien29085@gmail.com
#############################################################################
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QImage, QImageReader
from App.Presentation.ViewModels.Workers import FunctionWorker

class ImageEditorViewModel(QObject):
    image_loaded = pyqtSignal(QImage)
    error_occurred = pyqtSignal(str)
    workers_idle = pyqtSignal()
    loading_changed = pyqtSignal(str, bool)

    def __init__(self, project_name=None, item_name=None):
        super().__init__()
        self.project_name = project_name
        self.item_name = item_name
        self.current_image_path = None
        self._workers = set()
        self._load_workers = set()
        self._load_generation = 0

    def load_image(self, file_path):
        if not isinstance(file_path, str) or not file_path:
            self.error_occurred.emit("Invalid image path.")
            return
        self._load_generation += 1
        generation = self._load_generation
        for worker in list(self._load_workers):
            if worker.isRunning():
                worker.requestInterruption()
        self._start_worker(
            lambda: self._decode_image(file_path),
            lambda image: self._on_image_decoded(
                generation,
                file_path,
                image,
            ),
            track_loading=True,
            is_image_load=True,
        )

    @staticmethod
    def _decode_image(file_path):
        reader = QImageReader(file_path)
        reader.setAutoTransform(True)
        return reader.read()

    def _on_image_decoded(self, generation, file_path, image):
        if generation != self._load_generation:
            return
        if image.isNull():
            self.error_occurred.emit(f"Cannot load image: {file_path}")
            return
        self.current_image_path = file_path
        self.image_loaded.emit(image)

    def save_image(self, file_path, image):
        """Save the current image to the given file path."""
        if isinstance(image, QImage) and not image.isNull():
            image = image.copy()

            def on_saved(success):
                if not success:
                    self.error_occurred.emit(f"Failed to save image to {file_path}")

            self._start_worker(lambda: image.save(file_path), on_saved)
        else:
            self.error_occurred.emit("No image loaded to save.")

    def _start_worker(
        self,
        function,
        callback,
        track_loading=False,
        is_image_load=False,
    ):
        worker = FunctionWorker(function)
        self._workers.add(worker)
        if is_image_load:
            self._load_workers.add(worker)
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
        self._load_workers.discard(worker)
        if not any(item.isRunning() for item in self._workers):
            self.workers_idle.emit()

    def close(self):
        self.request_shutdown()

    def request_shutdown(self):
        self._load_generation += 1
        for worker in list(self._workers):
            if worker.isRunning():
                worker.requestInterruption()

    def has_running_workers(self):
        return any(worker.isRunning() for worker in self._workers)
