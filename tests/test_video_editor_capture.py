import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage
from PyQt6.QtMultimedia import QMediaPlayer
from PyQt6.QtTest import QSignalSpy, QTest
from PyQt6.QtWidgets import QApplication, QTabWidget

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
            any(worker.isRunning() for worker in editor._workers)
            and time.monotonic() < deadline
        ):
            self.app.processEvents()
            QTest.qWait(10)
        self.app.processEvents()
        self.assertFalse(
            any(worker.isRunning() for worker in editor._workers),
            "Video capture worker did not finish",
        )

    def test_opened_video_is_paused_and_has_no_decoder_source(self):
        editor = VideoEditor(str(self.video_file))

        self.assertEqual(
            editor.media_player.playbackState(),
            QMediaPlayer.PlaybackState.StoppedState,
        )
        self.assertTrue(editor.media_player.source().isEmpty())
        self.assertFalse(editor.is_media_loading())
        self.assertEqual(editor.btn_play.toolTip(), "Play")
        editor.close()

    def test_many_restored_video_tabs_do_not_allocate_decoder_sources(self):
        editors = []
        for index in range(12):
            video_path = self.video_dir / f"restored_{index}.mp4"
            video_path.touch()
            editors.append(VideoEditor(str(video_path)))

        self.assertTrue(
            all(editor.media_player.source().isEmpty() for editor in editors)
        )
        self.assertTrue(
            all(
                editor.media_player.playbackState()
                == QMediaPlayer.PlaybackState.StoppedState
                for editor in editors
            )
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

        self.assertEqual(len(playback_requested), 1)
        self.assertEqual(len(media_load_started), 1)
        self.assertFalse(editor.media_player.source().isEmpty())
        self.assertEqual(
            os.path.normcase(editor.media_player.source().toLocalFile()),
            os.path.normcase(str(self.video_file)),
        )
        editor.close()

    def test_releasing_inactive_video_preserves_lazy_resume_state(self):
        editor = VideoEditor(str(self.video_file))
        editor.toggle_play()

        editor.pause_playback(release_resources=True)

        self.assertTrue(editor.media_player.source().isEmpty())
        self.assertEqual(
            editor.media_player.playbackState(),
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

    def test_project_video_capture_repairs_image_folder(self):
        editor = VideoEditor(
            str(self.video_file).replace("\\", "/"),
            project_name="Project",
            project_path=str(self.project),
        )
        editor.current_frame = self._frame()
        media_created = QSignalSpy(editor.media_created)

        with patch.object(editor, "video_widget"), patch(
            "App.Presentation.Views.Widgets.FileEditorWorkspace.VideoEditor."
            "QMessageBox.warning"
        ) as warning:
            editor.capture_image()
            self._wait_for_workers(editor)

        captures = list((self.item / "Image").glob("capture_*.png"))
        self.assertEqual(len(captures), 1)
        self.assertEqual(len(media_created), 1)
        self.assertEqual(media_created[0][0:3], ["Project", "Item", "Image"])
        warning.assert_not_called()
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
