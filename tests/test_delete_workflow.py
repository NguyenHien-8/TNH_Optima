import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QObject, QPoint, QThread
from PyQt6.QtTest import QSignalSpy, QTest
from PyQt6.QtWidgets import QApplication

from App.Infrastructure.Repositories.SessionRepository import SessionRepository
from App.Models.ProjectManager import ProjectManager
from App.Models.SessionManager import SessionManager
from App.Presentation.ViewModels.MainViewModel import MainViewModel
from App.Presentation.Views.Dialog.DeleteResourcesDialog import (
    DeleteResourcesDialog,
)
from App.Presentation.Views.Widgets.SideBar import ProjectSidebar


class DeleteWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _wait_until(self, predicate, timeout_seconds=5):
        deadline = time.monotonic() + timeout_seconds
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            QTest.qWait(10)
        self.app.processEvents()
        self.assertTrue(predicate(), "Timed out waiting for background work")

    def test_unchecked_media_delete_only_hides_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "Project"
            image_dir = project_path / "Item" / "Image"
            image_dir.mkdir(parents=True)
            file_path = image_dir / "kept.png"
            file_path.write_bytes(b"kept")

            view_model = MainViewModel.__new__(MainViewModel)
            QObject.__init__(view_model)
            view_model.project_manager = SimpleNamespace(
                current_projects={"Project": str(project_path)}
            )
            view_model.hidden_media_paths = set()
            removed = QSignalSpy(view_model.file_removed)

            view_model.handle_delete_file(
                "Project",
                "Item",
                "Image",
                file_path.name,
                False,
            )

            self.assertTrue(file_path.is_file())
            self.assertEqual(len(removed), 1)
            self.assertTrue(removed[0][4])
            self.assertIn(
                os.path.normcase(os.path.abspath(file_path)),
                view_model.hidden_media_paths,
            )

    def test_delete_dialog_content_remains_unchanged(self):
        dialog = DeleteResourcesDialog(
            None,
            "Delete Item",
            "Remove item 'Item' from the project 'Project'?",
            r"C:\Project\Item",
            show_checkbox=True,
        )

        self.assertEqual(dialog.windowTitle(), "Delete Item")
        self.assertEqual(
            dialog.chk_delete_disk.text(),
            "Delete project contents on disk (cannot be undone)",
        )
        self.assertEqual(dialog.btn_ok.text(), "OK")
        self.assertEqual(dialog.btn_cancel.text(), "Cancel")
        self.assertFalse(dialog.is_delete_disk_checked())
        dialog.close()

    def test_item_context_menu_emits_open_video_intent(self):
        class FakeMenu:
            def __init__(self, parent):
                self.actions = []

            def addAction(self, text):
                self.actions.append(text)
                return text

            def addSeparator(self):
                return None

            def exec(self, position):
                return "Open Video..."

        sidebar = ProjectSidebar()
        open_media = QSignalSpy(sidebar.sig_item_open_media)
        with patch(
            "App.Presentation.Views.Widgets.SideBar.QMenu",
            FakeMenu,
        ):
            sidebar._show_item_context_menu(
                "Project",
                "Item",
                QPoint(0, 0),
            )

        self.assertEqual(
            open_media[0],
            ["Project", "Item", "Video"],
        )
        sidebar.shutdown()
        sidebar.close()

    def test_hidden_media_is_filtered_from_background_scan(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            media_dir = Path(temp_dir)
            visible = media_dir / "visible.png"
            hidden = media_dir / "hidden.png"
            visible.write_bytes(b"visible")
            hidden.write_bytes(b"hidden")

            names = ProjectSidebar._scan_media_directory(
                str(media_dir),
                "Image",
                (os.path.normcase(hidden.name),),
            )

            self.assertEqual(names, [visible.name])

    def test_hidden_media_paths_round_trip_through_session(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = SessionRepository(
                str(Path(temp_dir) / "session.db")
            )
            original = SessionManager(repository)
            hidden_paths = [
                str(Path(temp_dir) / "Project" / "Item" / "Image" / "a.png"),
                str(Path(temp_dir) / "Project" / "Item" / "Video" / "b.mp4"),
            ]
            original.set_hidden_media_paths(hidden_paths)
            original.save_hidden_media_paths()

            restored = SessionManager(repository)
            restored.load_hidden_media_paths()

            self.assertEqual(restored.get_hidden_media_paths(), hidden_paths)

    def test_model_only_accepts_media_from_expected_item_folder(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project_path = root / "Project"
            image_dir = project_path / "Item" / "Image"
            video_dir = project_path / "Item" / "Video"
            image_dir.mkdir(parents=True)
            video_dir.mkdir()
            image_path = image_dir / "restored.png"
            outside_path = root / "outside.png"
            image_path.write_bytes(b"image")
            outside_path.write_bytes(b"outside")

            with patch(
                "App.Models.ProjectManager.user_documents_path",
                return_value=root,
            ):
                manager = ProjectManager()
            manager.current_projects["Project"] = str(project_path)

            valid = manager.validate_media_file_for_open(
                "Project",
                "Item",
                "Image",
                str(image_path),
            )
            outside = manager.validate_media_file_for_open(
                "Project",
                "Item",
                "Image",
                str(outside_path),
            )

            self.assertTrue(valid[0], valid[1])
            self.assertEqual(valid[2], image_path.name)
            self.assertFalse(outside[0])

    def test_open_media_restores_hidden_state_in_background(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "Project"
            image_dir = project_path / "Item" / "Image"
            image_dir.mkdir(parents=True)
            image_path = image_dir / "restored.png"
            image_path.write_bytes(b"image")
            normalized_path = os.path.normcase(os.path.abspath(image_path))
            gui_thread_id = int(QThread.currentThreadId())
            validation_thread_ids = []

            def validate_media(*args):
                validation_thread_ids.append(int(QThread.currentThreadId()))
                return (
                    True,
                    "Image file ready",
                    image_path.name,
                    str(image_path),
                )

            manager = SimpleNamespace(
                current_projects={"Project": str(project_path)},
                get_media_extensions=lambda media_type: (".png",),
                validate_media_file_for_open=validate_media,
            )
            view_model = MainViewModel.__new__(MainViewModel)
            QObject.__init__(view_model)
            view_model.project_manager = manager
            view_model.hidden_media_paths = {normalized_path}
            view_model.active_workers = []
            view_model._deferred_task_timers = set()
            revealed = QSignalSpy(view_model.media_revealed)
            editor_requests = QSignalSpy(
                view_model.open_editor_requested
            )

            view_model.handle_open_media_file(
                "Project",
                "Item",
                "Image",
                str(image_path),
            )
            self._wait_until(
                lambda: len(revealed) == 1
                and len(editor_requests) == 1
                and not view_model.active_workers
            )

            self.assertNotIn(
                normalized_path,
                view_model.hidden_media_paths,
            )
            self.assertNotEqual(
                validation_thread_ids[0],
                gui_thread_id,
            )
            self.assertEqual(revealed[0][3], str(image_path))
            self.assertEqual(editor_requests[0][0], str(image_path))


if __name__ == "__main__":
    unittest.main()
