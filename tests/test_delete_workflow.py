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
from PyQt6.QtWidgets import QApplication, QDialog

from App.Infrastructure.Repositories.SessionRepository import SessionRepository
from App.Models.ProjectManager import ProjectManager
from App.Models.SessionManager import SessionManager
from App.Presentation.ViewModels.MainViewModel import MainViewModel
from App.Presentation.Views.MainView import MainView
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

    def test_sidebar_media_pickers_use_independent_recent_directories(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project_path = root / "Project"
            image_directory = root / "Previous Images"
            video_directory = root / "Previous Videos"
            image_directory.mkdir()
            video_directory.mkdir()
            manager = SimpleNamespace(
                current_projects={"Project": str(project_path)},
                get_media_extensions=lambda media_type: (
                    (".png", ".jpg")
                    if media_type == "Image"
                    else (".mp4", ".avi")
                ),
            )
            view_model = MainViewModel.__new__(MainViewModel)
            QObject.__init__(view_model)
            view_model.project_manager = manager
            view_model._editor_directories = {
                purpose: None
                for purpose in view_model._EDITOR_DIRECTORY_PURPOSES
            }
            view_model._editor_directories["sidebar_image_open"] = str(
                image_directory
            )
            view_model._editor_directories["sidebar_video_open"] = str(
                video_directory
            )

            image_config = view_model.get_media_picker_config(
                "Project",
                "Item",
                "Image",
            )
            video_config = view_model.get_media_picker_config(
                "Project",
                "Item",
                "Video",
            )

            self.assertEqual(
                image_config["directory"],
                str(image_directory),
            )
            self.assertEqual(
                video_config["directory"],
                str(video_directory),
            )

    def test_sidebar_watchers_can_be_released_and_restored(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "Project"
            item_path = project_path / "Item"
            image_dir = item_path / "Image"
            video_dir = item_path / "Video"
            image_dir.mkdir(parents=True)
            video_dir.mkdir()
            sidebar = ProjectSidebar()
            sidebar.add_project_item("Project", str(project_path))
            sidebar.add_structure_item(
                "Project",
                "Item",
                str(item_path),
            )

            self.assertIn(str(image_dir), sidebar.watched_paths)
            self.assertIn(str(video_dir), sidebar.watched_paths)

            sidebar.unwatch_item_media("Project", "Item")

            self.assertNotIn(str(image_dir), sidebar.watched_paths)
            self.assertNotIn(str(video_dir), sidebar.watched_paths)

            sidebar.watch_item_media("Project", "Item")

            self.assertIn(str(image_dir), sidebar.watched_paths)
            self.assertIn(str(video_dir), sidebar.watched_paths)
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

    def test_model_accepts_supported_media_from_any_existing_location(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project_path = root / "Project"
            image_dir = project_path / "Item" / "Image"
            video_dir = project_path / "Item" / "Video"
            other_image_dir = (
                root / "Other Project" / "Other Item" / "Image"
            )
            image_dir.mkdir(parents=True)
            video_dir.mkdir()
            other_image_dir.mkdir(parents=True)
            image_path = image_dir / "restored.png"
            other_project_image = other_image_dir / "foreign.JPG"
            outside_video = root / "outside.MP4"
            unsupported_path = root / "outside.txt"
            image_path.write_bytes(b"image")
            other_project_image.write_bytes(b"foreign image")
            outside_video.write_bytes(b"outside video")
            unsupported_path.write_bytes(b"unsupported")

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
            other_project = manager.validate_media_file_for_open(
                "Project",
                "Item",
                "Image",
                str(other_project_image),
            )
            outside = manager.validate_media_file_for_open(
                "Project",
                "Item",
                "Video",
                str(outside_video),
            )
            unsupported = manager.validate_media_file_for_open(
                "Project",
                "Item",
                "Image",
                str(unsupported_path),
            )

            self.assertTrue(valid[0], valid[1])
            self.assertEqual(valid[2], image_path.name)
            self.assertTrue(other_project[0], other_project[1])
            self.assertEqual(
                other_project[3],
                os.path.normpath(str(other_project_image)),
            )
            self.assertTrue(outside[0], outside[1])
            self.assertEqual(outside[2], outside_video.name)
            self.assertFalse(unsupported[0])

    def test_model_imports_media_into_selected_item_without_overwrite(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project_path = root / "Project"
            image_dir = project_path / "Item" / "Image"
            video_dir = project_path / "Item" / "Video"
            image_dir.mkdir(parents=True)
            video_dir.mkdir()
            source_dir = root / "External"
            source_dir.mkdir()
            source_image = source_dir / "sample.png"
            source_video = source_dir / "sample.mp4"
            source_image.write_bytes(b"external image")
            source_video.write_bytes(b"external video")

            with patch(
                "App.Models.ProjectManager.user_documents_path",
                return_value=root,
            ):
                manager = ProjectManager()
            manager.current_projects["Project"] = str(project_path)

            first_image = manager.import_media_file_for_open(
                "Project",
                "Item",
                "Image",
                str(source_image),
            )
            second_image = manager.import_media_file_for_open(
                "Project",
                "Item",
                "Image",
                str(source_image),
            )
            imported_video = manager.import_media_file_for_open(
                "Project",
                "Item",
                "Video",
                str(source_video),
            )

            self.assertTrue(first_image[0], first_image[1])
            self.assertTrue(first_image[4])
            self.assertEqual(first_image[2], "sample.png")
            self.assertEqual(
                Path(first_image[3]).read_bytes(),
                b"external image",
            )
            self.assertTrue(second_image[0], second_image[1])
            self.assertTrue(second_image[4])
            self.assertEqual(second_image[2], "sample_Copy1.png")
            self.assertEqual(
                Path(second_image[3]).read_bytes(),
                b"external image",
            )
            self.assertTrue(imported_video[0], imported_video[1])
            self.assertTrue(imported_video[4])
            self.assertEqual(
                Path(imported_video[3]).parent,
                video_dir,
            )
            self.assertEqual(source_image.read_bytes(), b"external image")
            self.assertEqual(source_video.read_bytes(), b"external video")
            self.assertEqual(
                list(project_path.rglob(".tnh-optima-import-*.tmp")),
                [],
            )

    def test_model_does_not_copy_media_already_in_selected_item(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project_path = root / "Project"
            image_dir = project_path / "Item" / "Image"
            image_dir.mkdir(parents=True)
            image_path = image_dir / "existing.png"
            image_path.write_bytes(b"existing")

            with patch(
                "App.Models.ProjectManager.user_documents_path",
                return_value=root,
            ):
                manager = ProjectManager()
            manager.current_projects["Project"] = str(project_path)

            result = manager.import_media_file_for_open(
                "Project",
                "Item",
                "Image",
                str(image_path),
            )

            self.assertTrue(result[0], result[1])
            self.assertFalse(result[4])
            self.assertEqual(result[3], os.path.normpath(str(image_path)))
            self.assertEqual(list(image_dir.iterdir()), [image_path])

    def test_failed_media_import_cleans_partial_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project_path = root / "Project"
            image_dir = project_path / "Item" / "Image"
            image_dir.mkdir(parents=True)
            source_path = root / "external.png"
            source_path.write_bytes(b"external")

            with patch(
                "App.Models.ProjectManager.user_documents_path",
                return_value=root,
            ):
                manager = ProjectManager()
            manager.current_projects["Project"] = str(project_path)

            with patch(
                "App.Models.ProjectManager.shutil.copy2",
                side_effect=OSError("disk full"),
            ):
                result = manager.import_media_file_for_open(
                    "Project",
                    "Item",
                    "Image",
                    str(source_path),
                )

            self.assertFalse(result[0])
            self.assertIn("disk full", result[1])
            self.assertEqual(list(image_dir.iterdir()), [])
            self.assertEqual(source_path.read_bytes(), b"external")

    def test_external_media_request_is_queued_as_standalone_editor(self):
        project_path = os.path.abspath("Project")
        external_path = os.path.abspath(
            os.path.join("External", "outside.png")
        )
        continue_calls = []
        host = SimpleNamespace(
            view_model=SimpleNamespace(
                get_project_path=lambda project_name: project_path,
                get_project_relative_path=lambda project_name, path: None,
            ),
            pending_restore_editors=[],
            restoring_in_progress=False,
            _continue_session_restore=lambda: continue_calls.append(True),
        )

        MainView._on_open_editor_requested(
            host,
            external_path,
            "Project",
        )

        self.assertEqual(
            host.pending_restore_editors,
            [(None, external_path)],
        )
        self.assertTrue(host.restoring_in_progress)
        self.assertEqual(continue_calls, [True])

    def test_open_media_restores_hidden_state_in_background(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "Project"
            image_dir = project_path / "Item" / "Image"
            image_dir.mkdir(parents=True)
            image_path = image_dir / "restored.png"
            image_path.write_bytes(b"image")
            normalized_path = os.path.normcase(os.path.abspath(image_path))
            gui_thread_id = int(QThread.currentThreadId())
            import_thread_ids = []

            def import_media(*args):
                import_thread_ids.append(int(QThread.currentThreadId()))
                return (
                    True,
                    "Image file ready",
                    image_path.name,
                    str(image_path),
                    False,
                )

            manager = SimpleNamespace(
                current_projects={"Project": str(project_path)},
                get_media_extensions=lambda media_type: (".png",),
                import_media_file_for_open=import_media,
            )
            view_model = MainViewModel.__new__(MainViewModel)
            QObject.__init__(view_model)
            view_model.project_manager = manager
            view_model.hidden_media_paths = {normalized_path}
            view_model.active_workers = []
            view_model._deferred_task_timers = set()
            remembered_directories = []
            view_model.remember_editor_directory = (
                lambda purpose, directory: remembered_directories.append(
                    (purpose, directory)
                )
            )
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
                import_thread_ids[0],
                gui_thread_id,
            )
            self.assertEqual(revealed[0][3], str(image_path))
            self.assertEqual(editor_requests[0][0], str(image_path))
            self.assertEqual(
                remembered_directories,
                [
                    (
                        "sidebar_image_open",
                        str(image_path.parent),
                    )
                ],
            )

    def test_sidebar_open_history_updates_image_and_video_separately(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "Image Source" / "image.png"
            video_path = root / "Video Source" / "video.mp4"
            image_path.parent.mkdir()
            video_path.parent.mkdir()
            image_path.write_bytes(b"image")
            video_path.write_bytes(b"video")

            def import_media(
                _project_name,
                _item_name,
                _media_type,
                file_path,
            ):
                return (
                    True,
                    "Media file ready",
                    os.path.basename(file_path),
                    file_path,
                    False,
                )

            view_model = MainViewModel.__new__(MainViewModel)
            QObject.__init__(view_model)
            view_model.project_manager = SimpleNamespace(
                import_media_file_for_open=import_media,
            )
            view_model.hidden_media_paths = set()
            view_model.active_workers = []
            view_model._deferred_task_timers = set()
            remembered = []
            view_model.remember_editor_directory = (
                lambda purpose, directory: remembered.append(
                    (purpose, directory)
                )
            )

            view_model.handle_open_media_file(
                "Project",
                "Item",
                "Image",
                str(image_path),
            )
            view_model.handle_open_media_file(
                "Project",
                "Item",
                "Video",
                str(video_path),
            )
            self._wait_until(
                lambda: len(remembered) == 2
                and not view_model.active_workers
            )

            self.assertCountEqual(
                remembered,
                [
                    (
                        "sidebar_image_open",
                        str(image_path.parent),
                    ),
                    (
                        "sidebar_video_open",
                        str(video_path.parent),
                    ),
                ],
            )

    def test_failed_sidebar_media_import_does_not_replace_history_or_open(self):
        view_model = MainViewModel.__new__(MainViewModel)
        QObject.__init__(view_model)
        view_model.project_manager = SimpleNamespace(
            import_media_file_for_open=lambda *_args: (
                False,
                "Import failed",
                "",
                "",
                False,
            ),
        )
        view_model.hidden_media_paths = set()
        view_model.active_workers = []
        view_model._deferred_task_timers = set()
        remembered = []
        view_model.remember_editor_directory = (
            lambda purpose, directory: remembered.append(
                (purpose, directory)
            )
        )
        errors = QSignalSpy(view_model.error_occurred)
        editor_requests = QSignalSpy(view_model.open_editor_requested)

        view_model.handle_open_media_file(
            "Project",
            "Item",
            "Video",
            r"C:\Source\failed.mp4",
        )
        self._wait_until(
            lambda: len(errors) == 1 and not view_model.active_workers
        )

        self.assertFalse(remembered)
        self.assertEqual(len(editor_requests), 0)

    def test_disk_item_delete_releases_handles_and_runs_in_background(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "Project"
            item_path = project_path / "Item"
            (item_path / "Image").mkdir(parents=True)
            (item_path / "Video").mkdir()
            gui_thread_id = int(QThread.currentThreadId())
            deletion_thread_ids = []

            def delete_item(project_name, item_name):
                deletion_thread_ids.append(int(QThread.currentThreadId()))
                return True, "Item moved to Recycle Bin successfully"

            manager = SimpleNamespace(
                current_projects={"Project": str(project_path)},
                get_file_path=lambda project_name, relative_path: str(
                    project_path / relative_path
                ),
                delete_item=delete_item,
            )
            view_model = MainViewModel.__new__(MainViewModel)
            QObject.__init__(view_model)
            view_model.project_manager = manager
            view_model.opened_items = {"Project": {"Item"}}
            view_model.hidden_media_paths = set()
            view_model.active_workers = []
            view_model._deferred_task_timers = set()
            unwatched = QSignalSpy(view_model.request_unwatch_item)
            editors_closed = QSignalSpy(
                view_model.request_close_editors_for_item
            )
            removed = QSignalSpy(view_model.item_removed)

            view_model.handle_delete_item("Project", "Item", True)

            self.assertEqual(unwatched[0], ["Project", "Item"])
            self.assertEqual(editors_closed[0], ["Project", "Item"])
            self._wait_until(
                lambda: len(removed) == 1
                and not view_model.active_workers
            )
            self.assertNotEqual(deletion_thread_ids[0], gui_thread_id)
            self.assertNotIn("Project", view_model.opened_items)

    def test_failed_disk_project_delete_restores_watchers(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "Project"
            project_path.mkdir()

            manager = SimpleNamespace(
                current_projects={"Project": str(project_path)},
                delete_project=lambda project_name: (
                    False,
                    "Move to Recycle Bin failed: source is locked",
                ),
            )
            view_model = MainViewModel.__new__(MainViewModel)
            QObject.__init__(view_model)
            view_model.project_manager = manager
            view_model.opened_items = {}
            view_model.hidden_media_paths = set()
            view_model.active_workers = []
            view_model._deferred_task_timers = set()
            unwatched = QSignalSpy(view_model.request_unwatch_project)
            rewatched = QSignalSpy(view_model.request_watch_project)
            errors = QSignalSpy(view_model.error_occurred)

            view_model.handle_delete_project("Project", True)

            self.assertEqual(unwatched[0], ["Project"])
            self._wait_until(
                lambda: len(rewatched) == 1
                and len(errors) == 1
                and not view_model.active_workers
            )
            self.assertEqual(rewatched[0], ["Project"])
            self.assertTrue(project_path.exists())

    def test_save_as_uses_worker_path_when_project_registry_changes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            old_path = root / "Temporary" / "Project"
            new_path = root / "Saved" / "Project"
            (old_path / "Item" / "Image").mkdir(parents=True)
            (old_path / "Item" / "Video").mkdir()
            (new_path / "Item" / "Image").mkdir(parents=True)
            (new_path / "Item" / "Video").mkdir()

            manager = SimpleNamespace(
                current_projects={"Project": str(old_path)},
            )

            def save_project_as(project_name, target_folder):
                manager.current_projects.pop(project_name, None)
                return True, str(new_path)

            manager.save_project_as = save_project_as
            manager.get_project_items = lambda project_name: ["Item"]

            view_model = MainViewModel.__new__(MainViewModel)
            QObject.__init__(view_model)
            view_model.project_manager = manager
            view_model.opened_items = {"Project": {"Item"}}
            view_model.hidden_media_paths = set()
            view_model.active_workers = []
            view_model._deferred_task_timers = set()
            project_added = QSignalSpy(view_model.project_added)
            item_added = QSignalSpy(view_model.item_added)
            errors = QSignalSpy(view_model.error_occurred)
            completed = []

            view_model.handle_save_as_project(
                "Project",
                str(root / "Saved"),
                on_success=lambda: completed.append(True),
            )
            self._wait_until(
                lambda: completed and not view_model.active_workers
            )

            self.assertEqual(len(errors), 0)
            self.assertEqual(
                project_added[0],
                ["Project", os.path.abspath(new_path)],
            )
            self.assertEqual(
                item_added[0],
                [
                    "Project",
                    "Item",
                    os.path.join(os.path.abspath(new_path), "Item"),
                ],
            )

    def test_temp_project_save_waits_for_success_before_close(self):
        class FakeSaveDialog:
            def __init__(self, *args, **kwargs):
                pass

            def exec(self):
                return QDialog.DialogCode.Accepted

            def get_action(self):
                return "SAVE"

        calls = []

        def handle_save(project_name, folder, on_success=None):
            calls.append(("save", project_name, folder))
            calls.append(("callback", on_success))

        view_model = SimpleNamespace(
            is_project_temp=lambda project_name: True,
            get_project_path=lambda project_name: r"C:\Temporary\Project",
            handle_save_as_project=handle_save,
            handle_delete_project=lambda project_name, delete_from_disk: (
                calls.append(
                    ("close", project_name, delete_from_disk)
                )
            ),
        )
        host = SimpleNamespace(view_model=view_model)

        with (
            patch(
                "App.Presentation.Views.MainView.SaveResourcesDialog",
                FakeSaveDialog,
            ),
            patch(
                "App.Presentation.Views.MainView."
                "QFileDialog.getExistingDirectory",
                return_value=r"C:\Saved",
            ),
        ):
            MainView._confirm_delete_project(host, "Project")

        self.assertEqual(calls[0], ("save", "Project", r"C:\Saved"))
        self.assertEqual(len(calls), 2)
        on_success = calls[1][1]
        self.assertTrue(callable(on_success))

        on_success()

        self.assertEqual(calls[2], ("close", "Project", False))


if __name__ == "__main__":
    unittest.main()
