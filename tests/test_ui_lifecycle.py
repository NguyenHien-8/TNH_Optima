import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from App.Infrastructure.Repositories.ConfigRepository import ConfigRepository
from App.Infrastructure.Repositories.SessionRepository import SessionRepository
from App.Models.Vision.CameraManager import CameraManager
from App.Presentation.ViewModels.DialogViewModel.ConfigCameraViewModel import (
    ConfigCameraViewModel,
)
from App.Presentation.ViewModels.FeatureViewModel.FileEditorViewModel import (
    FileEditorViewModel,
)
from App.Presentation.ViewModels.MainViewModel import MainViewModel
from App.Presentation.Views.Dialog.ConfigCameraDialog import ConfigCameraDialog
from App.Presentation.Views.MainView import MainView


class FakeCameraManager:
    def get_fps(self):
        return 20.0


class UiLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _wait_until(self, predicate, timeout_seconds=8):
        deadline = time.monotonic() + timeout_seconds
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            QTest.qWait(10)
        self.app.processEvents()
        self.assertTrue(predicate(), "Timed out waiting for Qt lifecycle")

    def test_main_window_startup_and_shutdown_leave_no_workers(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "ConfigStorage.db"
            session_path = root / "SessionData.db"
            with (
                patch(
                    "App.Presentation.ViewModels.MainViewModel."
                    "ConfigRepository",
                    return_value=ConfigRepository(str(config_path)),
                ),
                patch(
                    "App.Presentation.ViewModels.MainViewModel."
                    "SessionRepository",
                    return_value=SessionRepository(str(session_path)),
                ),
                patch(
                    "App.Models.ProjectManager.user_documents_path",
                    return_value=root,
                ),
            ):
                view_model = MainViewModel()
                window = MainView(view_model)
                window.show()
                self._wait_until(
                    lambda: not view_model.active_workers
                    and view_model._session_ui_timer is None
                )

                window.close()
                self._wait_until(lambda: not window.isVisible())

                self.assertFalse(view_model.active_workers)
                self.assertIsNone(view_model.camera_manager.current_thread)
                self.assertIsNone(view_model.camera_manager.scan_thread)
                self.assertTrue(view_model._shutdown_complete)
                window.deleteLater()
                self.app.processEvents()

    def test_video_recorder_starts_and_stops_without_orphan_thread(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            item_path = Path(temp_dir) / "Item"
            (item_path / "Image").mkdir(parents=True)
            (item_path / "Video").mkdir()
            session_path = item_path / "Item.session"
            view_model = FileEditorViewModel(
                "Project",
                session_path.name,
                "",
                str(session_path),
                FakeCameraManager(),
                object(),
            )
            image = QImage(64, 48, QImage.Format.Format_RGB32)
            image.fill(Qt.GlobalColor.blue)

            view_model.start_video()
            self._wait_until(view_model.media_manager.is_recording)
            for _ in range(8):
                view_model.receive_frame(image)
                self.app.processEvents()
                QTest.qWait(10)

            view_model.stop_video()
            self._wait_until(
                lambda: not view_model.media_manager.is_recording()
                and not view_model._workers
            )

            self.assertIsNone(
                view_model.media_manager.video_manager.video_thread
            )
            self.assertTrue(view_model.request_close())
            self.app.processEvents()

    def test_camera_dialog_accepts_only_after_save_worker_finishes(self):
        camera_manager = CameraManager()
        view_model = ConfigCameraViewModel(camera_manager)
        with (
            patch.object(view_model, "scan_cameras"),
            patch.object(
                view_model.backend,
                "save_selected_camera",
                return_value=None,
            ),
            patch.object(
                view_model.backend,
                "apply_runtime_changes",
            ),
        ):
            dialog = ConfigCameraDialog(view_model)
            dialog.show()
            dialog.on_click_apply()
            self._wait_until(lambda: not dialog.isVisible())

        self.assertFalse(view_model.is_busy())
        self.assertFalse(view_model._workers)
        dialog.deleteLater()
        self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
