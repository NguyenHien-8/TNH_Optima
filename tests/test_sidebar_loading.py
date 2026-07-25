import os
import tempfile
import time
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QAbstractAnimation
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from App.Presentation.Views.Widgets.SideBar import ProjectSidebar


class SidebarLoadingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.sidebar = ProjectSidebar()

    def tearDown(self):
        self.sidebar.shutdown(wait_ms=2000)
        self.sidebar.close()
        self.sidebar.deleteLater()
        self.app.processEvents()
        self.temp_dir.cleanup()

    def test_indicator_is_thin_shimmer_and_has_no_text_widget(self):
        bar = self.sidebar.loading_bar

        self.assertEqual(bar.height(), 3)
        self.assertEqual(bar.children(), [bar._animation])
        self.assertFalse(bar.is_active())
        self.assertFalse(bar.is_animation_running())
        self.assertTrue(bar.isHidden())

    def test_indicator_waits_for_all_concurrent_sources(self):
        self.sidebar.set_loading_source("project", True)
        self.sidebar.set_loading_source("file-editor", True)

        self.assertTrue(self.sidebar.is_loading())
        self.assertFalse(self.sidebar.loading_bar.isHidden())

        self.sidebar.set_loading_source("project", False)
        self.assertTrue(self.sidebar.is_loading())
        self.assertFalse(self.sidebar.loading_bar.isHidden())

        self.sidebar.set_loading_source("file-editor", False)
        self.assertFalse(self.sidebar.is_loading())
        self.assertFalse(self.sidebar.loading_bar.is_animation_running())
        self.assertTrue(self.sidebar.loading_bar.isHidden())

    def test_shimmer_animates_only_while_visible_and_loading(self):
        self.sidebar.resize(280, 500)
        self.sidebar.show()
        self.sidebar.set_loading_source("project", True)
        self.app.processEvents()

        start_phase = self.sidebar.loading_bar.phase()
        QTest.qWait(80)
        self.app.processEvents()

        self.assertTrue(self.sidebar.loading_bar.is_animation_running())
        self.assertNotEqual(self.sidebar.loading_bar.phase(), start_phase)

        self.sidebar.set_loading_source("project", False)
        self.app.processEvents()
        self.assertEqual(
            self.sidebar.loading_bar._animation.state(),
            QAbstractAnimation.State.Stopped,
        )

    def test_sidebar_and_shimmer_follow_horizontal_resize(self):
        self.sidebar.resize(240, 500)
        self.sidebar.show()
        self.sidebar.set_loading_source("project", True)
        self.app.processEvents()
        narrow_width = self.sidebar.loading_bar.width()

        self.sidebar.resize(620, 500)
        QTest.qWait(20)
        self.app.processEvents()
        wide_width = self.sidebar.loading_bar.width()

        self.assertGreater(wide_width, narrow_width)
        self.assertGreaterEqual(self.sidebar.maximumWidth(), 620)

    def test_project_media_scans_keep_indicator_active_until_queue_is_idle(self):
        project = Path(self.temp_dir.name) / "Project"
        item = project / "Item"
        (item / "Image").mkdir(parents=True)
        (item / "Video").mkdir()

        self.sidebar.add_project_item("Project", str(project))
        self.sidebar.add_structure_item("Project", "Item", str(item))

        self.assertTrue(self.sidebar.is_loading())
        deadline = time.monotonic() + 5
        while (
            (
                self.sidebar._media_scan_queue
                or self.sidebar._media_scan_workers
            )
            and time.monotonic() < deadline
        ):
            self.app.processEvents()
            QTest.qWait(10)
        self.app.processEvents()

        self.assertFalse(self.sidebar._media_scan_queue)
        self.assertFalse(self.sidebar._media_scan_workers)
        self.assertFalse(self.sidebar.is_loading())
        self.assertTrue(self.sidebar.loading_bar.isHidden())


if __name__ == "__main__":
    unittest.main()
