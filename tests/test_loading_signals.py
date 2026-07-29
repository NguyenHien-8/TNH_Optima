import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QObject
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtTest import QSignalSpy, QTest
from PyQt6.QtWidgets import QApplication

from App.Presentation.ViewModels.FeatureViewModel.ImageEditorViewModel import (
    ImageEditorViewModel,
)
from App.Presentation.ViewModels.MainViewModel import MainViewModel
from App.Presentation.ViewModels.Workers import FunctionWorker
from App.Presentation.Views.Widgets.FileEditorWorkspace.ImageCanvas import (
    ImageCanvas,
)
from App.Presentation.Views.Widgets.FileEditorWorkspace.ImageEditor import (
    ImageEditor,
)


class LoadingSignalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _wait_until(self, predicate, timeout_seconds=5):
        deadline = time.monotonic() + timeout_seconds
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            QTest.qWait(10)
        self.app.processEvents()
        self.assertTrue(predicate(), "Timed out waiting for loading lifecycle")

    def test_main_worker_emits_balanced_sidebar_loading_lifecycle(self):
        view_model = MainViewModel.__new__(MainViewModel)
        QObject.__init__(view_model)
        view_model.active_workers = []
        loading_events = QSignalSpy(view_model.sidebar_loading_changed)
        worker = FunctionWorker(lambda: "done")

        view_model.start_worker(worker, show_sidebar_loading=True)
        self._wait_until(lambda: len(loading_events) == 2)

        self.assertTrue(loading_events[0][1])
        self.assertFalse(loading_events[1][1])
        self.assertEqual(loading_events[0][0], loading_events[1][0])
        self.assertFalse(view_model.active_workers)

    def test_image_decode_emits_balanced_loading_lifecycle(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "image.png"
            image = QImage(32, 24, QImage.Format.Format_RGB32)
            self.assertTrue(image.save(str(image_path), "PNG"))

            view_model = ImageEditorViewModel()
            loading_events = QSignalSpy(view_model.loading_changed)
            image_loaded = QSignalSpy(view_model.image_loaded)

            view_model.load_image(str(image_path))
            self._wait_until(
                lambda: len(loading_events) == 2
                and len(image_loaded) == 1
            )

            self.assertTrue(loading_events[0][1])
            self.assertFalse(loading_events[1][1])
            self.assertEqual(loading_events[0][0], loading_events[1][0])
            self.assertFalse(view_model.has_running_workers())
            self.assertIsInstance(image_loaded[0][0], QImage)
            self.assertNotIsInstance(image_loaded[0][0], QPixmap)

    def test_new_image_request_cancels_stale_decode_result(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            slow_path = Path(temp_dir) / "slow.png"
            fast_path = Path(temp_dir) / "fast.png"
            slow_image = QImage(16, 16, QImage.Format.Format_RGB32)
            slow_image.fill(0xFFFF0000)
            fast_image = QImage(16, 16, QImage.Format.Format_RGB32)
            fast_image.fill(0xFF0000FF)
            self.assertTrue(slow_image.save(str(slow_path), "PNG"))
            self.assertTrue(fast_image.save(str(fast_path), "PNG"))

            view_model = ImageEditorViewModel()
            original_decode = view_model._decode_image
            loaded_images = []
            view_model.image_loaded.connect(
                lambda image: loaded_images.append(image.copy())
            )

            def delayed_decode(file_path):
                if file_path == str(slow_path):
                    time.sleep(0.15)
                return original_decode(file_path)

            with patch.object(
                view_model,
                "_decode_image",
                side_effect=delayed_decode,
            ):
                view_model.load_image(str(slow_path))
                view_model.load_image(str(fast_path))
                self._wait_until(
                    lambda: not view_model.has_running_workers()
                    and view_model.current_image_path == str(fast_path)
                )

            self.assertEqual(
                loaded_images[-1].pixelColor(0, 0),
                fast_image.pixelColor(0, 0),
            )

    def test_image_editor_renders_with_lightweight_qt_canvas(self):
        view_model = ImageEditorViewModel()
        editor = ImageEditor(view_model)
        image = QImage(320, 200, QImage.Format.Format_RGB32)
        image.fill(0xFF335577)

        editor.on_image_loaded(image)
        editor.resize(640, 480)
        editor.show()
        self.app.processEvents()

        self.assertIsInstance(editor.canvas, ImageCanvas)
        self.assertFalse(editor.canvas._pixmap.isNull())
        self.assertFalse(editor.grab().isNull())
        editor.close()

    def test_image_save_uses_view_data_in_background_worker(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "saved.png"
            image = QImage(80, 60, QImage.Format.Format_RGB32)
            image.fill(0xFF335577)
            view_model = ImageEditorViewModel()

            view_model.save_image(str(output_path), image)
            self._wait_until(
                lambda: output_path.is_file()
                and not view_model.has_running_workers()
            )

            saved_image = QImage(str(output_path))
            self.assertEqual(saved_image.size(), image.size())

    def test_hidden_image_tab_defers_decode_until_shown(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "deferred.png"
            image = QImage(64, 48, QImage.Format.Format_RGB32)
            image.fill(0xFF335577)
            self.assertTrue(image.save(str(image_path), "PNG"))

            view_model = ImageEditorViewModel()
            editor = ImageEditor(view_model)
            editor.set_image_source(str(image_path))
            self.app.processEvents()

            self.assertIsNone(view_model.current_image_path)
            self.assertFalse(view_model.has_running_workers())

            editor.show()
            self._wait_until(
                lambda: view_model.current_image_path == str(image_path)
                and not view_model.has_running_workers()
            )
            self.assertFalse(editor.current_pixmap.isNull())
            editor.close()


if __name__ == "__main__":
    unittest.main()
