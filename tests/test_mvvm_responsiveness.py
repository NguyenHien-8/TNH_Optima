import inspect
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QObject, QThread, Qt, pyqtSignal
from PyQt6.QtGui import QImage
from PyQt6.QtTest import QSignalSpy, QTest
from PyQt6.QtWidgets import QApplication, QMainWindow

from App.Infrastructure.Helpers.WindowOwnershipHelper import (
    fit_window_to_available_screen,
)
from App.Models.Vision.CameraManager import CameraManager
from App.Models.Vision.CameraThread import CameraThread
from App.Presentation.ViewModels.DialogViewModel.ConfigCameraViewModel import (
    ConfigCameraViewModel,
)
from App.Presentation.ViewModels.FeatureViewModel.FileEditorViewModel import (
    FileEditorViewModel,
)
from App.Presentation.ViewModels.FeatureViewModel.DropletAnalysisViewModel import (
    DropletAnalysisViewModel,
)
from App.Presentation.Views.Widgets.FileEditorWorkspace.FileEditor import (
    FileEditor,
)


class FakeFileEditorViewModel(QObject):
    frame_received = pyqtSignal(QImage)
    video_state_changed = pyqtSignal(str)
    recording_time_updated = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def move_up(self, height, speed):
        return None

    def move_down(self, height, speed):
        return None

    def stop_motor(self):
        return None

    def capture_image(self, qimage):
        return None

    def start_video(self):
        return None

    def pause_video(self):
        return None

    def resume_video(self):
        return None

    def stop_video(self):
        return None

    def close(self):
        return True


class FakeCameraManager:
    def get_fps(self):
        return 30.0


class MvvmResponsivenessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.root = Path(__file__).resolve().parents[1]

    def _wait_until(self, predicate, timeout_seconds=5):
        deadline = time.monotonic() + timeout_seconds
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            QTest.qWait(10)
        self.app.processEvents()
        self.assertTrue(predicate(), "Timed out waiting for background work")

    def test_views_do_not_own_models_workers_or_thread_waits(self):
        views_root = self.root / "App" / "Presentation" / "Views"
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in views_root.rglob("*.py")
        )
        forbidden = (
            "from App.Models",
            "ViewModels.Workers import",
            "FunctionWorker(",
            ".wait(",
            "view_model.camera_manager",
            "view_model.hardware_manager",
            "view_model.control_panel_manager",
            "view_model.project_manager",
        )
        for token in forbidden:
            self.assertNotIn(token, source)

    def test_feature_windows_apply_available_screen_fitting(self):
        main_source = (
            self.root / "App" / "Presentation" / "Views" / "MainView.py"
        ).read_text(encoding="utf-8")
        droplet_source = (
            self.root
            / "App"
            / "Presentation"
            / "Views"
            / "Widgets"
            / "DropletAnalysisWindow.py"
        ).read_text(encoding="utf-8")
        self.assertIn("preferred_size=(1100, 720)", main_source)
        self.assertIn("preferred_size=(1100, 760)", droplet_source)
        self.assertIn("fit_window_to_available_screen(", main_source)
        self.assertIn("fit_window_to_available_screen(", droplet_source)

    def test_window_fit_stays_inside_available_geometry(self):
        window = QMainWindow()
        target = fit_window_to_available_screen(
            window,
            preferred_size=(100000, 100000),
            width_ratio=0.80,
            height_ratio=0.75,
            minimum_size=(320, 240),
        )
        self.assertIsNotNone(target)
        available = window.screen().availableGeometry()
        geometry = window.geometry()
        self.assertLessEqual(geometry.width(), int(available.width() * 0.80))
        self.assertLessEqual(geometry.height(), int(available.height() * 0.75))
        self.assertGreaterEqual(geometry.left(), available.left())
        self.assertGreaterEqual(geometry.top(), available.top())
        self.assertLessEqual(geometry.right(), available.right())
        self.assertLessEqual(geometry.bottom(), available.bottom())
        window.close()

    def test_droplet_model_work_runs_outside_gui_thread(self):
        view_model = DropletAnalysisViewModel()
        image = QImage(320, 240, QImage.Format.Format_Grayscale8)
        image.fill(Qt.GlobalColor.white)
        image_spy = QSignalSpy(view_model.image_loaded)
        analysis_spy = QSignalSpy(view_model.analysis_completed)
        self.assertTrue(view_model.load_image(image))
        self._wait_until(lambda: len(image_spy) == 1)
        self.assertTrue(view_model.perform_analysis())
        self._wait_until(lambda: len(analysis_spy) == 1)

        gui_thread_id = int(QThread.currentThreadId())
        worker_thread_ids = []
        original_compute = view_model._analysis_manager.compute_baseline

        def compute_baseline(*args, **kwargs):
            worker_thread_ids.append(int(QThread.currentThreadId()))
            return original_compute(*args, **kwargs)

        baseline_spy = QSignalSpy(view_model.baseline_completed)
        with patch.object(
            view_model._analysis_manager,
            "compute_baseline",
            side_effect=compute_baseline,
        ):
            view_model.compute_baseline(
                "Double Points",
                [(0.0, 0.25), (5.0, 0.25)],
            )
            self._wait_until(lambda: len(baseline_spy) == 1)

        self.assertTrue(worker_thread_ids)
        self.assertNotEqual(worker_thread_ids[0], gui_thread_id)
        self.assertTrue(view_model.request_close())

    def test_camera_preview_rendering_is_throttled_on_gui_thread(self):
        editor = FileEditor(FakeFileEditorViewModel())
        image = QImage(320, 240, QImage.Format.Format_RGB32)
        image.fill(Qt.GlobalColor.black)
        render_calls = []

        def record_preview_update(qimage):
            render_calls.append(qimage)

        editor.update_camera_display = record_preview_update
        for _ in range(5):
            editor.on_frame_received(image)

        self.assertEqual(len(render_calls), 1)
        self.assertIs(editor.current_frame, image)
        self.assertIs(editor.media_editor.current_frame, image)
        editor.close()

    def test_droplet_export_writes_in_view_model_worker(self):
        view_model = DropletAnalysisViewModel()
        image = QImage(64, 48, QImage.Format.Format_RGB32)
        image.fill(Qt.GlobalColor.white)
        saved_spy = QSignalSpy(view_model.save_completed)

        with tempfile.TemporaryDirectory() as temp_dir:
            item_path = Path(temp_dir) / "Item"
            item_path.mkdir()
            view_model.configure_storage_context(item_path=str(item_path))
            self.assertTrue(view_model.save_rendered_image(image))
            self._wait_until(lambda: len(saved_spy) == 1)
            saved_path = Path(saved_spy[0][0])
            self.assertEqual(saved_path.parent, item_path / "Image")
            self.assertTrue(saved_path.is_file())

        self.assertTrue(view_model.request_close())

    def test_camera_cleanup_is_non_blocking_by_default(self):
        default = inspect.signature(CameraManager.cleanup).parameters[
            "wait_ms"
        ].default
        self.assertEqual(default, 0)

    def test_camera_frames_are_coalesced_before_gui_delivery(self):
        worker = CameraThread()
        emitted = QSignalSpy(worker.change_pixmap_signal)
        first = QImage(2, 2, QImage.Format.Format_RGB32)
        first.fill(Qt.GlobalColor.red)
        latest = QImage(2, 2, QImage.Format.Format_RGB32)
        latest.fill(Qt.GlobalColor.blue)

        worker._publish_frame(first)
        for _ in range(10):
            worker._publish_frame(latest)

        self.assertEqual(len(emitted), 1)
        self.assertEqual(
            worker.take_latest_frame().pixelColor(0, 0),
            latest.pixelColor(0, 0),
        )
        worker._publish_frame(first)
        self.assertEqual(len(emitted), 2)

    def test_camera_configuration_save_runs_outside_gui_thread(self):
        camera_manager = CameraManager()
        view_model = ConfigCameraViewModel(camera_manager)
        gui_thread_id = int(QThread.currentThreadId())
        save_thread_ids = []

        def save_camera(camera_id):
            save_thread_ids.append(int(QThread.currentThreadId()))
            return camera_id

        with (
            patch.object(
                view_model.backend,
                "save_selected_camera",
                side_effect=save_camera,
            ),
            patch.object(
                view_model.backend,
                "apply_runtime_changes",
            ),
        ):
            idle = QSignalSpy(view_model.workers_idle)
            self.assertTrue(view_model.apply_changes())
            self._wait_until(lambda: len(idle) == 1)

        self.assertTrue(save_thread_ids)
        self.assertNotEqual(save_thread_ids[0], gui_thread_id)
        self.assertFalse(view_model.is_busy())

    def test_video_storage_preparation_runs_outside_gui_thread(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            item_path = Path(temp_dir) / "Item"
            item_path.mkdir()
            full_path = item_path / "Item.session"
            view_model = FileEditorViewModel(
                "Project",
                full_path.name,
                "",
                str(full_path),
                FakeCameraManager(),
                object(),
            )
            gui_thread_id = int(QThread.currentThreadId())
            preparation_thread_ids = []

            def prepare_video(fps):
                preparation_thread_ids.append(int(QThread.currentThreadId()))
                return False, "", "cancelled", None, None

            with patch.object(
                view_model.media_manager,
                "prepare_video",
                side_effect=prepare_video,
            ):
                view_model.start_video()
                self._wait_until(
                    lambda: not view_model._video_start_pending
                    and not view_model._workers
                )

            self.assertTrue(preparation_thread_ids)
            self.assertNotEqual(
                preparation_thread_ids[0],
                gui_thread_id,
            )
            self.assertTrue(view_model.request_close())


if __name__ == "__main__":
    unittest.main()
