import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QThread, Qt
from PyQt6.QtGui import QImage
from PyQt6.QtMultimedia import QMediaPlayer
from PyQt6.QtTest import QSignalSpy, QTest
from PyQt6.QtWidgets import QApplication, QTabWidget

from App.Presentation.ViewModels.FeatureViewModel.VideoEditorViewModel import (
    VideoEditorViewModel,
)
from App.Presentation.Views.MainView import MainView
from App.Presentation.Views.Widgets.FileEditorWorkspace.VideoEditor import (
    VideoEditor,
)


class VideoEditorCaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.project = self.root / "Project"
        self.item = self.project / "Item"
        self.video_dir = self.item / "Video"
        self.video_dir.mkdir(parents=True)
        self.video_file = self.video_dir / "video.mp4"
        self.video_file.touch()

    def tearDown(self):
        self.app.processEvents()
        self.temp_dir.cleanup()

    @staticmethod
    def _frame():
        image = QImage(160, 120, QImage.Format.Format_RGB32)
        image.fill(Qt.GlobalColor.black)
        return image

    def _wait_for_workers(self, editor, timeout_seconds=5):
        deadline = time.monotonic() + timeout_seconds
        while (
            (
                any(worker.isRunning() for worker in editor._workers)
                or editor.view_model.has_running_workers()
            )
            and time.monotonic() < deadline
        ):
            self.app.processEvents()
            QTest.qWait(10)
        self.app.processEvents()
        self.assertFalse(
            any(worker.isRunning() for worker in editor._workers),
            "Video capture worker did not finish",
        )
        self.assertFalse(editor.view_model.has_running_workers())

    def _wait_until(self, predicate, timeout_seconds=5):
        deadline = time.monotonic() + timeout_seconds
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            QTest.qWait(10)
        self.app.processEvents()
        self.assertTrue(predicate(), "Timed out waiting for video state")

    def test_opened_video_is_paused_and_has_no_decoder_source(self):
        editor = VideoEditor(str(self.video_file))

        self.assertIsNone(editor._media_player)
        self.assertIsNone(editor.video_widget)
        self.assertFalse(editor.is_media_loading())
        self.assertEqual(editor.btn_play.toolTip(), "Play")
        editor.close()

    def test_open_video_and_capture_use_independent_recent_directories(self):
        initial_open_dir = self.root / "Initial Open"
        selected_open_dir = self.root / "Selected Open"
        initial_capture_dir = self.root / "Initial Capture"
        selected_capture_dir = self.root / "Selected Capture"
        for directory in (
            initial_open_dir,
            selected_open_dir,
            initial_capture_dir,
            selected_capture_dir,
        ):
            directory.mkdir()

        selected_video = selected_open_dir / "selected.mp4"
        selected_video.touch()
        capture_path = selected_capture_dir / "captured.png"
        state = {
            VideoEditorViewModel.OPEN_DIRECTORY: str(initial_open_dir),
            VideoEditorViewModel.CAPTURE_DIRECTORY: str(
                initial_capture_dir
            ),
        }

        def remember(purpose, directory):
            state[purpose] = directory

        view_model = VideoEditorViewModel(
            file_path=str(self.video_file),
            recent_directory_provider=lambda purpose: state[purpose],
            recent_directory_recorder=remember,
        )
        editor = VideoEditor(
            str(self.video_file),
            view_model=view_model,
        )
        editor.current_frame = self._frame()

        with patch(
            "App.Presentation.Views.Widgets.FileEditorWorkspace.VideoEditor."
            "QFileDialog.getOpenFileName",
            return_value=(str(selected_video), "Videos (*.mp4)"),
        ) as open_dialog:
            editor.on_open_clicked()

        self.assertEqual(
            open_dialog.call_args.args[2],
            str(initial_open_dir),
        )
        self.assertEqual(
            state[view_model.OPEN_DIRECTORY],
            str(selected_open_dir),
        )
        self.assertEqual(
            state[view_model.CAPTURE_DIRECTORY],
            str(initial_capture_dir),
        )

        with patch(
            "App.Presentation.Views.Widgets.FileEditorWorkspace.VideoEditor."
            "QFileDialog.getSaveFileName",
            return_value=(str(capture_path), "PNG Images (*.png)"),
        ) as save_dialog:
            editor.capture_image()
            self._wait_for_workers(editor)

        suggested_path = Path(save_dialog.call_args.args[2])
        self.assertEqual(suggested_path.parent, initial_capture_dir)
        self.assertTrue(suggested_path.name.startswith("capture_"))
        self.assertEqual(
            state[view_model.CAPTURE_DIRECTORY],
            str(selected_capture_dir),
        )
        self.assertEqual(
            state[view_model.OPEN_DIRECTORY],
            str(selected_open_dir),
        )
        self.assertTrue(capture_path.is_file())
        editor.close()

    def test_many_restored_video_tabs_do_not_allocate_decoder_sources(self):
        editors = []
        for index in range(12):
            video_path = self.video_dir / f"restored_{index}.mp4"
            video_path.touch()
            editors.append(VideoEditor(str(video_path)))

        self.assertTrue(
            all(editor._media_player is None for editor in editors)
        )
        self.assertTrue(
            all(editor.video_widget is None for editor in editors)
        )
        self.assertTrue(
            all(not editor.is_media_loading() for editor in editors)
        )
        for editor in editors:
            editor.close()

    def test_decoder_source_is_created_only_after_user_clicks_play(self):
        editor = VideoEditor(str(self.video_file))
        playback_requested = QSignalSpy(editor.playback_requested)
        media_load_started = QSignalSpy(editor.media_load_started)

        editor.toggle_play()
        self._wait_until(
            lambda: editor._media_player is not None
            and not editor._media_player.source().isEmpty()
        )

        self.assertEqual(len(playback_requested), 1)
        self.assertEqual(len(media_load_started), 1)
        self.assertFalse(editor._media_player.source().isEmpty())
        self.assertEqual(
            os.path.normcase(editor._media_player.source().toLocalFile()),
            os.path.normcase(str(self.video_file)),
        )
        self._wait_for_workers(editor)
        editor.close()

    def test_video_source_validation_runs_outside_gui_thread(self):
        editor = VideoEditor(str(self.video_file))
        gui_thread_id = int(QThread.currentThreadId())
        validation_thread_ids = []
        original_inspect = editor.view_model._inspect_source

        def inspect_source(file_path):
            validation_thread_ids.append(int(QThread.currentThreadId()))
            return original_inspect(file_path)

        with patch.object(
            editor.view_model,
            "_inspect_source",
            side_effect=inspect_source,
        ):
            editor.toggle_play()
            self._wait_until(lambda: bool(validation_thread_ids))
            self._wait_for_workers(editor)

        self.assertNotEqual(validation_thread_ids[0], gui_thread_id)
        editor.close()

    def test_video_frame_probe_throttles_gui_thread_conversion(self):
        editor = VideoEditor()
        image = self._frame()

        class FakeFrame:
            def __init__(self):
                self.to_image_calls = 0

            def isValid(self):
                return True

            def toImage(self):
                self.to_image_calls += 1
                return image

        frame = FakeFrame()

        editor.on_video_frame_probed(frame)
        editor.on_video_frame_probed(frame)
        editor.on_video_frame_probed(frame)

        self.assertEqual(frame.to_image_calls, 1)
        self.assertFalse(editor.current_frame.isNull())
        editor.close()

    def test_releasing_inactive_video_preserves_lazy_resume_state(self):
        editor = VideoEditor(str(self.video_file))
        editor.toggle_play()

        editor.pause_playback(release_resources=True)
        self._wait_for_workers(editor)

        self.assertTrue(
            editor._media_player is None
            or editor._media_player.source().isEmpty()
        )
        if editor._media_player is not None:
            self.assertEqual(
                editor._media_player.playbackState(),
                QMediaPlayer.PlaybackState.StoppedState,
            )
        self.assertEqual(editor.btn_play.toolTip(), "Play")
        editor.close()

    def test_starting_one_video_releases_every_other_video_decoder(self):
        first = VideoEditor(str(self.video_file))
        second_path = self.video_dir / "second.mp4"
        second_path.touch()
        second = VideoEditor(str(second_path))
        first.setProperty("editor_kind", "video")
        second.setProperty("editor_kind", "video")
        tabs = QTabWidget()
        tabs.addTab(first, "first")
        tabs.addTab(second, "second")
        host = SimpleNamespace(
            editor_workspace=SimpleNamespace(tab_widget=tabs),
            _is_video_editor=MainView._is_video_editor,
        )

        with patch.object(first, "pause_playback") as pause_first, patch.object(
            second,
            "pause_playback",
        ) as pause_second:
            MainView._activate_video_playback(host, second)

        pause_first.assert_called_once_with(release_resources=True)
        pause_second.assert_not_called()
        first.close()
        second.close()
        tabs.close()

    def test_session_restore_yields_between_editor_tabs(self):
        calls = []
        host = SimpleNamespace(
            restoring_in_progress=True,
            _process_next_pending_editor=lambda: calls.append("next"),
        )

        MainView._continue_session_restore(host)

        self.assertFalse(calls)
        self._wait_until(lambda: calls == ["next"])

    def test_project_video_capture_uses_save_as_and_updates_project_when_selected(self):
        remembered = {}
        image_folder = self.item / "Image"
        image_folder.mkdir()
        target = image_folder / "chosen_capture.png"
        view_model = VideoEditorViewModel(
            file_path=str(self.video_file),
            recent_directory_recorder=lambda purpose, directory: (
                remembered.update({purpose: directory})
            ),
        )
        editor = VideoEditor(
            str(self.video_file).replace("\\", "/"),
            project_name="Project",
            project_path=str(self.project),
            view_model=view_model,
        )
        editor.current_frame = self._frame()
        media_created = QSignalSpy(editor.media_created)

        with patch(
            "App.Presentation.Views.Widgets.FileEditorWorkspace.VideoEditor."
            "QFileDialog.getSaveFileName",
            return_value=(str(target), "PNG Images (*.png)"),
        ) as save_dialog, patch.object(editor, "video_widget"), patch(
            "App.Presentation.Views.Widgets.FileEditorWorkspace.VideoEditor."
            "QMessageBox.warning"
        ) as warning:
            editor.capture_image()
            self._wait_for_workers(editor)

        save_dialog.assert_called_once()
        self.assertTrue(target.is_file())
        self.assertEqual(len(media_created), 1)
        self.assertEqual(media_created[0][0:3], ["Project", "Item", "Image"])
        self.assertEqual(
            remembered[view_model.CAPTURE_DIRECTORY],
            str(image_folder),
        )
        warning.assert_not_called()
        editor.close()

    def test_project_video_capture_can_save_outside_project(self):
        selected_folder = self.root / "Selected"
        selected_folder.mkdir()
        target = selected_folder / "chosen_capture.png"
        editor = VideoEditor(
            str(self.video_file),
            project_name="Project",
            project_path=str(self.project),
        )
        editor.current_frame = self._frame()
        media_created = QSignalSpy(editor.media_created)

        with patch(
            "App.Presentation.Views.Widgets.FileEditorWorkspace.VideoEditor."
            "QFileDialog.getSaveFileName",
            return_value=(str(target), "PNG Images (*.png)"),
        ) as save_dialog:
            editor.capture_image()
            self._wait_for_workers(editor)

        save_dialog.assert_called_once()
        self.assertTrue(target.is_file())
        self.assertFalse((self.item / "Image").exists())
        self.assertEqual(len(media_created), 0)
        editor.close()

    def test_project_video_capture_cancel_does_not_save(self):
        editor = VideoEditor(
            str(self.video_file),
            project_name="Project",
            project_path=str(self.project),
        )
        editor.current_frame = self._frame()

        with patch(
            "App.Presentation.Views.Widgets.FileEditorWorkspace.VideoEditor."
            "QFileDialog.getSaveFileName",
            return_value=("", ""),
        ) as save_dialog, patch.object(
            editor.view_model,
            "save_capture",
        ) as save_capture:
            editor.capture_image()

        save_dialog.assert_called_once()
        save_capture.assert_not_called()
        self.assertFalse((self.item / "Image").exists())
        editor.close()

    def test_external_video_capture_uses_save_as_instead_of_structure_error(self):
        external_video = self.root / "external.mp4"
        external_video.touch()
        target = self.root / "captured.png"
        editor = VideoEditor(str(external_video))
        editor.current_frame = self._frame()

        with patch(
            "App.Presentation.Views.Widgets.FileEditorWorkspace.VideoEditor."
            "QFileDialog.getSaveFileName",
            return_value=(str(target), "PNG Images (*.png)"),
        ) as save_dialog, patch(
            "App.Presentation.Views.Widgets.FileEditorWorkspace.VideoEditor."
            "QMessageBox.warning"
        ) as warning:
            editor.capture_image()
            self._wait_for_workers(editor)

        self.assertTrue(target.is_file())
        save_dialog.assert_called_once()
        warning.assert_not_called()
        editor.close()


if __name__ == "__main__":
    unittest.main()
