import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from App.Infrastructure.Helpers import PathHelper
from App.Infrastructure.Helpers.PathHelper import (
    canonical_path,
    is_path_within,
    project_media_item_path,
    relative_path_within,
    user_documents_path,
)
from App.Models.ProjectManager import ProjectManager


class PathHandlingTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.project = self.root / "Project"
        self.item = self.project / "Item"
        self.image_dir = self.item / "Image"
        self.video_dir = self.item / "Video"
        self.image_dir.mkdir(parents=True)
        self.video_dir.mkdir()
        self.image_file = self.image_dir / "image.png"
        self.video_file = self.video_dir / "video.mp4"
        self.image_file.touch()
        self.video_file.touch()

    def tearDown(self):
        self.temp_dir.cleanup()

    @staticmethod
    def _mixed_separators(path):
        value = str(path)
        if os.name == "nt":
            prefix, tail = value[:3], value[3:]
            return prefix.replace("\\", "/") + tail.replace("\\", "/").replace(
                "/Image/",
                "\\Image\\",
            ).replace(
                "/Video/",
                "\\Video\\",
            )
        return value

    def test_relative_path_accepts_equivalent_separator_styles(self):
        mixed_file = self._mixed_separators(self.image_file)
        mixed_project = str(self.project).replace("\\", "/")

        relative = relative_path_within(mixed_file, mixed_project)

        self.assertEqual(
            relative,
            os.path.join("Item", "Image", "image.png"),
        )

    def test_containment_rejects_sibling_with_shared_prefix(self):
        sibling = self.root / "Project Backup" / "image.png"
        sibling.parent.mkdir()
        sibling.touch()

        self.assertFalse(is_path_within(sibling, self.project))
        self.assertIsNone(relative_path_within(sibling, self.project))

    def test_video_item_is_resolved_from_mixed_path(self):
        mixed_video = self._mixed_separators(self.video_file)

        item_path = project_media_item_path(
            mixed_video,
            "video",
            str(self.project).replace("\\", "/"),
        )

        self.assertEqual(
            os.path.normcase(item_path),
            os.path.normcase(canonical_path(self.item)),
        )

    def test_video_item_does_not_require_existing_image_folder(self):
        self.image_file.unlink()
        self.image_dir.rmdir()

        item_path = project_media_item_path(
            self.video_file,
            "Video",
            self.project,
        )

        self.assertEqual(item_path, canonical_path(self.item))

    def test_project_manager_rejects_relative_path_escape(self):
        with patch(
            "App.Models.ProjectManager.user_documents_path",
            return_value=self.root,
        ):
            manager = ProjectManager()
        manager.current_projects["Project"] = str(self.project)

        self.assertEqual(
            manager.get_file_path(
                "Project",
                os.path.join("Item", "Image", "image.png"),
            ),
            canonical_path(self.image_file),
        )
        self.assertIsNone(
            manager.get_file_path(
                "Project",
                os.path.join("..", "outside.png"),
            )
        )

    def test_windows_documents_uses_known_folder_api(self):
        redirected_documents = self.root / "Redirected Documents"

        with (
            patch.object(PathHelper.sys, "platform", "win32"),
            patch.object(
                PathHelper,
                "_get_windows_documents_path",
                return_value=redirected_documents,
            ) as known_folder,
        ):
            result = user_documents_path()

        self.assertEqual(result, redirected_documents)
        known_folder.assert_called_once_with()

    def test_windows_documents_falls_back_to_user_profile(self):
        user_profile = self.root / "WindowsUser"

        with (
            patch.object(PathHelper.sys, "platform", "win32"),
            patch.object(
                PathHelper,
                "_get_windows_documents_path",
                side_effect=OSError("Known Folder API unavailable"),
            ),
            patch.dict(
                PathHelper.os.environ,
                {"USERPROFILE": str(user_profile)},
                clear=True,
            ),
        ):
            result = user_documents_path()

        self.assertEqual(result, user_profile / "Documents")

    def test_new_project_uses_documents_projects_folder(self):
        documents = self.root / "Documents"

        with patch(
            "App.Models.ProjectManager.user_documents_path",
            return_value=documents,
        ):
            manager = ProjectManager()

        success, project_path = manager.create_project("Untitled-1")
        expected_root = documents / "TNH Optima Projects"
        expected_project = expected_root / "Untitled-1"

        self.assertTrue(success)
        self.assertEqual(manager.temp_root, str(expected_root))
        self.assertEqual(project_path, str(expected_project))
        self.assertTrue((expected_project / "config.json").is_file())
        self.assertTrue(manager.is_project_temp("Untitled-1"))


if __name__ == "__main__":
    unittest.main()
