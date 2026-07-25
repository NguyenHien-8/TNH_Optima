import os
import tempfile
import time
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QObject
from PyQt6.QtGui import QImage
from PyQt6.QtTest import QSignalSpy, QTest
from PyQt6.QtWidgets import QApplication

from App.Presentation.ViewModels.FeatureViewModel.ImageEditorViewModel import (
    ImageEditorViewModel,
)
from App.Presentation.ViewModels.MainViewModel import MainViewModel
from App.Presentation.ViewModels.Workers import FunctionWorker


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


if __name__ == "__main__":
    unittest.main()
