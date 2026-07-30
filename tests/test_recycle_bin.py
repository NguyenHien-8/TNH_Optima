import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from App.Infrastructure.Helpers import RecycleBinHelper
from App.Models.ProjectManager import ProjectManager


class RecycleBinTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.project = self.root / "Project"
        self.source_item = self.project / "Source"
        self.target_item = self.project / "Target"
        for item in (self.source_item, self.target_item):
            (item / "Image").mkdir(parents=True)
            (item / "Video").mkdir()

        with patch(
            "App.Models.ProjectManager.user_documents_path",
            return_value=self.root,
        ):
            self.manager = ProjectManager()
        self.manager.current_projects["Project"] = str(self.project)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_checked_media_delete_moves_file_to_recycle_bin(self):
        image_path = self.source_item / "Image" / "image.png"
        image_path.write_bytes(b"image")
        recycled_paths = []

        def fake_recycle(path):
            recycled_paths.append(os.path.abspath(path))
            os.remove(path)

        with patch(
            "App.Models.ProjectManager.move_to_recycle_bin",
            side_effect=fake_recycle,
        ):
            success, message = self.manager.delete_file(
                "Project",
                "Source",
                "Image",
                image_path.name,
            )

        self.assertTrue(success, message)
        self.assertFalse(image_path.exists())
        self.assertEqual(recycled_paths, [os.path.abspath(image_path)])
        self.assertIn("Recycle Bin", message)

    def test_checked_item_delete_moves_folder_to_recycle_bin(self):
        recycled_paths = []

        def fake_recycle(path):
            recycled_paths.append(os.path.abspath(path))
            shutil.rmtree(path)

        with patch(
            "App.Models.ProjectManager.move_to_recycle_bin",
            side_effect=fake_recycle,
        ):
            success, message = self.manager.delete_item(
                "Project",
                "Source",
            )

        self.assertTrue(success, message)
        self.assertFalse(self.source_item.exists())
        self.assertEqual(
            recycled_paths,
            [os.path.abspath(self.source_item)],
        )
        self.assertIn("Recycle Bin", message)

    def test_checked_project_delete_moves_folder_to_recycle_bin(self):
        recycled_paths = []

        def fake_recycle(path):
            recycled_paths.append(os.path.abspath(path))
            shutil.rmtree(path)

        with patch(
            "App.Models.ProjectManager.move_to_recycle_bin",
            side_effect=fake_recycle,
        ):
            success, message = self.manager.delete_project("Project")

        self.assertTrue(success, message)
        self.assertFalse(self.project.exists())
        self.assertEqual(
            recycled_paths,
            [os.path.abspath(self.project)],
        )
        self.assertNotIn("Project", self.manager.current_projects)
        self.assertIn("Recycle Bin", message)

    def test_recycle_failure_keeps_original_file(self):
        video_path = self.source_item / "Video" / "video.mp4"
        video_path.write_bytes(b"video")

        with patch(
            "App.Models.ProjectManager.move_to_recycle_bin",
            side_effect=OSError("Recycle Bin is unavailable"),
        ):
            success, message = self.manager.delete_file(
                "Project",
                "Source",
                "Video",
                video_path.name,
            )

        self.assertFalse(success)
        self.assertTrue(video_path.exists())
        self.assertIn("Recycle Bin", message)

    def test_cut_move_does_not_create_recycle_bin_copy(self):
        source_path = self.source_item / "Image" / "move.png"
        source_path.write_bytes(b"move")

        with patch(
            "App.Models.ProjectManager.move_to_recycle_bin"
        ) as recycle:
            success, message, new_name = self.manager.move_file(
                "Project",
                "Source",
                "Image",
                source_path.name,
                "Project",
                "Target",
                "Image",
            )

        self.assertTrue(success, message)
        self.assertFalse(source_path.exists())
        self.assertEqual(new_name, source_path.name)
        self.assertEqual(
            (self.target_item / "Image" / new_name).read_bytes(),
            b"move",
        )
        recycle.assert_not_called()

    def test_cut_move_item_does_not_create_recycle_bin_copy(self):
        (self.source_item / "Image" / "source.png").write_bytes(b"source")
        second_project = self.root / "SecondProject"
        second_project.mkdir()
        self.manager.current_projects["SecondProject"] = str(second_project)

        with patch(
            "App.Models.ProjectManager.move_to_recycle_bin"
        ) as recycle:
            success, message, new_name = self.manager.move_item_structure(
                "Project",
                "Source",
                "SecondProject",
            )

        self.assertTrue(success, message)
        self.assertFalse(self.source_item.exists())
        self.assertEqual(new_name, "Source")
        self.assertTrue((second_project / new_name).is_dir())
        recycle.assert_not_called()

    def test_helper_never_falls_back_to_permanent_delete(self):
        image_path = self.source_item / "Image" / "safe.png"
        image_path.write_bytes(b"safe")

        with (
            patch.object(RecycleBinHelper.sys, "platform", "win32"),
            patch(
                "send2trash.send2trash",
                side_effect=OSError("native recycle failed"),
            ),
        ):
            with self.assertRaisesRegex(OSError, "native recycle failed"):
                RecycleBinHelper.move_to_recycle_bin(image_path)

        self.assertTrue(image_path.exists())

    def test_helper_retries_transient_copy_engine_access_denied(self):
        image_path = self.source_item / "Image" / "locked.png"
        image_path.write_bytes(b"locked")
        attempts = []
        access_denied = OSError("source is temporarily locked")
        access_denied.winerror = -2144927711  # 0x80270021

        def fake_recycle(path):
            attempts.append(path)
            if len(attempts) == 1:
                raise access_denied
            os.remove(path)

        with (
            patch.object(RecycleBinHelper.sys, "platform", "win32"),
            patch(
                "send2trash.send2trash",
                side_effect=fake_recycle,
            ),
            patch.object(RecycleBinHelper.time, "sleep") as sleep,
        ):
            recycled_path = RecycleBinHelper.move_to_recycle_bin(
                image_path
            )

        self.assertEqual(recycled_path, os.path.abspath(image_path))
        self.assertEqual(len(attempts), 2)
        sleep.assert_called_once_with(0.1)
        self.assertFalse(image_path.exists())


if __name__ == "__main__":
    unittest.main()
