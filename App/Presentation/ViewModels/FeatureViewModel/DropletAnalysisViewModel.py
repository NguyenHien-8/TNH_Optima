##################################################################################
# @file App/Presentation/ViewModels/FeatureViewModel/DropletAnalysisViewModel.py
# Author: TRAN NGUYEN HIEN
# Email: trannguyenhien29085@gmail.com
##################################################################################
import os
from datetime import datetime

import numpy as np

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QImage

from App.Models.Analysis.AnalysisManager import AnalysisManager
from App.Models.Analysis.DropletAnalysis import auto_detect_edge_points
from App.Presentation.ViewModels.Workers import FunctionWorker


class DropletAnalysisViewModel(QObject):
    """Own droplet-analysis state and every potentially blocking operation."""

    analysis_completed = pyqtSignal(object)
    baseline_completed = pyqtSignal(str, object)
    droplet_analysis_completed = pyqtSignal(str, object)
    edges_detected = pyqtSignal(object)
    error_occurred = pyqtSignal(str)
    operation_failed = pyqtSignal(str, str)
    image_loaded = pyqtSignal()
    image_data_ready = pyqtSignal()
    save_completed = pyqtSignal(str)
    workers_idle = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._analysis_manager = AnalysisManager()
        self._source_image_path = None
        self._item_path = None
        self._image_array = None
        self._display_image = None
        self._heatmap_data = None
        self.analysis_data = None
        self._workers = set()
        self._closing = False

    def configure_storage_context(self, source_image_path=None, item_path=None):
        self._source_image_path = (
            source_image_path
            if isinstance(source_image_path, str) and source_image_path.strip()
            else None
        )
        self._item_path = (
            item_path
            if isinstance(item_path, str) and item_path.strip()
            else None
        )

    def load_image(self, image):
        if not isinstance(image, QImage) or image.isNull():
            self.error_occurred.emit("Invalid image provided")
            return False

        image_copy = image.copy()
        self._start_worker(
            lambda: self._qimage_to_array(image_copy),
            self._on_image_array_ready,
            "load_image",
        )
        return True

    @staticmethod
    def _qimage_to_array(image):
        grayscale = image.convertToFormat(QImage.Format.Format_Grayscale8)
        ptr = grayscale.bits()
        ptr.setsize(grayscale.sizeInBytes())
        rows = np.frombuffer(ptr, dtype=np.uint8).reshape(
            grayscale.height(), grayscale.bytesPerLine()
        )
        return rows[:, : grayscale.width()].copy()

    @staticmethod
    def _downsample(image, maximum_dimension):
        height, width = image.shape
        stride = max(1, int(np.ceil(max(height, width) / maximum_dimension)))
        return image[::stride, ::stride]

    def _on_image_array_ready(self, image_array):
        self._image_array = image_array
        self._display_image = self._downsample(image_array, 1280)
        self.image_loaded.emit()
        self.image_data_ready.emit()

    def has_image(self):
        return self._image_array is not None

    def perform_analysis(self):
        if self._image_array is None:
            self.error_occurred.emit("No image data to analyze")
            return False

        image_array = self._image_array

        def analyze():
            image_float = image_array.astype(np.float32, copy=False)
            img_min = float(np.min(image_float))
            img_max = float(np.max(image_float))
            if img_max > img_min:
                normalized = (image_float - img_min) * (255.0 / (img_max - img_min))
            else:
                normalized = image_float.copy()

            heatmap = self._downsample(normalized, 480)
            heatmap_height, heatmap_width = heatmap.shape
            return {
                "normalized": heatmap,
                "heatmap_x": np.linspace(
                    0.0, 5.0, heatmap_width, dtype=np.float32
                ),
                "heatmap_y": np.linspace(
                    3.0, 0.0, heatmap_height, dtype=np.float32
                ),
                "min_value": img_min,
                "max_value": img_max,
                "mean_value": float(np.mean(image_float)),
                "std_value": float(np.std(image_float)),
                "height": image_array.shape[0],
                "width": image_array.shape[1],
            }

        self._start_worker(analyze, self._on_analysis_ready, "image_analysis")
        return True

    def _on_analysis_ready(self, analysis_data):
        self.analysis_data = analysis_data
        self._heatmap_data = (
            analysis_data["heatmap_x"],
            analysis_data["heatmap_y"],
            analysis_data["normalized"],
        )
        self.analysis_completed.emit(analysis_data)

    def get_original_display_data(self):
        return self._display_image

    def get_analysis_data(self):
        return self.analysis_data

    def get_heatmap_data(self):
        return self._heatmap_data

    def is_mirror_method_available(self):
        return self._analysis_manager.is_mirror_method_available()

    def compute_baseline(self, method, points):
        safe_points = [tuple(point) for point in points]
        image_array = self._image_array
        self._start_worker(
            lambda: self._analysis_manager.compute_baseline(
                method,
                points=safe_points,
                image=image_array,
            ),
            lambda result: self.baseline_completed.emit(method, result),
            "baseline",
        )
        return True

    def auto_detect_edges(
        self,
        num_points,
        baseline_coeffs,
        baseline_anchor_points=None,
    ):
        if self._image_array is None:
            self.error_occurred.emit("No image data to analyze")
            return False

        image_array = self._image_array
        safe_coeffs = tuple(baseline_coeffs)
        safe_anchors = (
            tuple(tuple(point) for point in baseline_anchor_points)
            if baseline_anchor_points is not None
            else None
        )
        self._start_worker(
            lambda: auto_detect_edge_points(
                image_array,
                int(num_points),
                physical_width=5.0,
                physical_height=3.0,
                baseline_coeffs=safe_coeffs,
                baseline_anchor_points=safe_anchors,
            ),
            self.edges_detected.emit,
            "edge_detection",
        )
        return True

    def analyze_droplet(self, method, baseline_coeffs, measurement_points):
        safe_coeffs = tuple(baseline_coeffs)
        safe_points = [tuple(point) for point in measurement_points]
        self._start_worker(
            lambda: self._analysis_manager.analyze_droplet(
                method,
                safe_coeffs,
                safe_points,
            ),
            lambda result: self.droplet_analysis_completed.emit(method, result),
            "droplet_analysis",
        )
        return True

    def save_rendered_image(self, image):
        if not isinstance(image, QImage) or image.isNull():
            self.operation_failed.emit("save", "Invalid rendered image")
            return False

        image_copy = image.copy()
        source_path = self._source_image_path
        item_path = self._item_path

        def save_image():
            save_dir, base_name = self._resolve_save_context(
                item_path,
                source_path,
            )
            if not save_dir:
                raise ValueError(
                    "Cannot determine the current item's Image folder automatically."
                )
            os.makedirs(save_dir, exist_ok=True)
            file_path = self._build_unique_save_path(save_dir, base_name)
            if not image_copy.save(file_path, "PNG"):
                raise OSError(f"Could not save image to '{file_path}'")
            return file_path

        self._start_worker(save_image, self.save_completed.emit, "save")
        return True

    @staticmethod
    def _resolve_save_context(item_path, source_path):
        normalized_item = (
            os.path.normpath(item_path)
            if isinstance(item_path, str) and item_path.strip()
            else None
        )
        normalized_source = (
            os.path.normpath(source_path)
            if isinstance(source_path, str) and source_path.strip()
            else None
        )

        if normalized_item:
            item_root = normalized_item
        elif normalized_source:
            media_dir = os.path.dirname(normalized_source)
            if os.path.basename(media_dir).casefold() in {"image", "video"}:
                item_root = os.path.dirname(media_dir)
            else:
                item_root = media_dir
        else:
            return None, "analysis_result"

        base_name = (
            os.path.splitext(os.path.basename(normalized_source))[0]
            if normalized_source
            else "analysis_result"
        )
        return os.path.join(item_root, "Image"), base_name

    @staticmethod
    def _build_unique_save_path(save_dir, base_name):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        candidate = os.path.join(save_dir, f"{base_name}_{timestamp}.png")
        index = 1
        while os.path.exists(candidate):
            candidate = os.path.join(
                save_dir,
                f"{base_name}_{timestamp}_{index}.png",
            )
            index += 1
        return candidate

    def _start_worker(self, function, callback, operation):
        worker = FunctionWorker(function)
        self._workers.add(worker)
        worker.result_ready.connect(callback)
        worker.error_occurred.connect(
            lambda message, name=operation: self._on_worker_error(name, message)
        )
        worker.finished.connect(lambda: self._finish_worker(worker))
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _on_worker_error(self, operation, message):
        self.operation_failed.emit(operation, message)
        self.error_occurred.emit(message)

    def _finish_worker(self, worker):
        self._workers.discard(worker)
        if not self._workers:
            self.workers_idle.emit()

    def request_close(self):
        self._closing = True
        running_workers = [worker for worker in self._workers if worker.isRunning()]
        for worker in running_workers:
            worker.requestInterruption()
        return not running_workers

    def close(self):
        return self.request_close()
