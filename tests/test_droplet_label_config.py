import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from matplotlib.backend_bases import MouseEvent
from PyQt6.QtCore import QObject, QSettings, Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QApplication

from App.Presentation.Views.Widgets.DropletAnalysisWindow import (
    DropletAnalysisWindow,
)
from App.Presentation.Views.Widgets.FileEditorWorkspace.ImageCanvas import (
    ImageCanvas,
)


class FakeDropletAnalysisViewModel(QObject):
    analysis_completed = pyqtSignal(object)
    baseline_completed = pyqtSignal(str, object)
    droplet_analysis_completed = pyqtSignal(str, object)
    edges_detected = pyqtSignal(object)
    error_occurred = pyqtSignal(str)
    operation_failed = pyqtSignal(str, str)
    image_loaded = pyqtSignal()
    image_data_ready = pyqtSignal()
    save_completed = pyqtSignal(str)
    workers_idle = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.display_image = np.zeros((60, 100), dtype=np.uint8)
        self.saved_rendered_image = None
        self.saved_file_path = None

    def configure_storage_context(self, **_kwargs):
        return None

    def load_image(self, _image):
        return True

    def perform_analysis(self):
        return True

    def get_original_display_data(self):
        return self.display_image

    def get_heatmap_data(self):
        return None

    def get_save_dialog_directory(self):
        return ""

    def get_suggested_save_filename(self):
        return "analysis_result.png"

    def save_rendered_image(self, image, file_path):
        self.saved_rendered_image = image.copy()
        self.saved_file_path = file_path
        return True

    def request_close(self):
        return True

    def close(self):
        return None


class DropletLabelConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.settings_temp_dir = tempfile.TemporaryDirectory()
        self.settings_path = os.path.join(
            self.settings_temp_dir.name,
            "droplet-analysis.ini",
        )
        self.settings = QSettings(
            self.settings_path,
            QSettings.Format.IniFormat,
        )
        pixmap = QPixmap(100, 60)
        pixmap.fill(Qt.GlobalColor.black)
        self.window = DropletAnalysisWindow(
            FakeDropletAnalysisViewModel(),
            pixmap,
            settings=self.settings,
        )
        self.window.resize(1200, 760)
        self.window.show()
        self.window.update_display()
        self.window.baseline_coeffs = (0.0, 1.0, -0.5)
        self.window._draw_baseline()
        self.results = {
            "left_point": (1.0, 0.5),
            "right_point": (4.0, 0.5),
            "left_tangent": (1.0, 1.0),
            "right_tangent": (-1.0, 1.0),
            "left_angle": 92.0,
            "right_angle": 88.0,
        }
        self.window.last_analysis_results = self.results
        self.window.btn_config_label.setEnabled(True)
        self.window._draw_analysis_results(self.results)
        self.window.canvas.draw()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.app.processEvents()
        self.settings_temp_dir.cleanup()

    def _mouse_event_at_data(self, name, x, y, button=None):
        canvas_x, canvas_y = self.window.ax.transData.transform((x, y))
        return MouseEvent(
            name,
            self.window.canvas,
            canvas_x,
            canvas_y,
            button=button,
        )

    def test_config_button_toggles_panel_font_and_handles(self):
        self.window.resize(1200, 760)
        self.app.processEvents()
        controls = (
            self.window.btn_refresh,
            self.window.btn_save,
            self.window.btn_analysis_manually,
            self.window.btn_delete_measure_point,
            self.window.btn_config_label,
            self.window.cb_angle_mode,
        )
        self.assertTrue(
            all(control.parentWidget() is self.window.action_bar for control in controls)
        )
        self.assertLessEqual(
            max(control.geometry().center().y() for control in controls)
            - min(control.geometry().center().y() for control in controls),
            1,
        )
        self.assertEqual(
            [control.geometry().left() for control in controls],
            sorted(control.geometry().left() for control in controls),
        )

        self.window.btn_measure.setChecked(True)
        self.assertTrue(self.window.is_measuring)
        self.window.btn_config_label.click()
        self.app.processEvents()

        self.assertTrue(self.window.is_config_label_mode)
        self.assertFalse(self.window.is_measuring)
        self.assertFalse(self.window.btn_measure.isChecked())
        self.assertFalse(self.window.config_label_group.isHidden())
        self.assertLessEqual(self.window.config_label_group.width(), 760)
        self.assertEqual(self.window.btn_reset_label_layout.text(), "")
        self.assertFalse(self.window.btn_reset_label_layout.icon().isNull())
        self.assertEqual(
            self.window.btn_reset_label_layout.accessibleName(),
            "Reset Label Layout",
        )
        self.assertEqual(
            set(self.window.arrow_handle_artists_by_side),
            {"left", "right"},
        )

        self.window.spin_angle_font_size.setValue(32)
        self.assertEqual(self.window.angle_label_font_size, 32)
        self.assertTrue(
            all(
                artist.get_fontsize() == 32
                for artist in self.window.angle_text_artists
            )
        )
        self.assertEqual(
            self.settings.value(
                self.window.ANGLE_FONT_SIZE_SETTING_KEY,
                type=int,
            ),
            32,
        )

        self.window.spin_baseline_size.setValue(4.5)
        self.window.spin_arrow_size.setValue(5.5)
        self.assertAlmostEqual(self.window.baseline_size, 4.5)
        self.assertAlmostEqual(self.window.baseline_line.get_linewidth(), 4.5)
        self.assertAlmostEqual(self.window.arrow_size, 5.5)
        self.assertTrue(
            all(
                arrow.get_linewidth() == 5.5
                for arrow in self.window.tangent_arrow_artists_by_side.values()
            )
        )
        self.assertAlmostEqual(
            self.settings.value(
                self.window.BASELINE_SIZE_SETTING_KEY,
                type=float,
            ),
            4.5,
        )
        self.assertAlmostEqual(
            self.settings.value(
                self.window.ARROW_SIZE_SETTING_KEY,
                type=float,
            ),
            5.5,
        )

        self.window.btn_reset_label_layout.click()
        self.assertEqual(self.window.angle_label_font_size, 32)
        self.assertEqual(self.window.spin_angle_font_size.value(), 32)
        self.assertAlmostEqual(self.window.spin_baseline_size.value(), 4.5)
        self.assertAlmostEqual(self.window.spin_arrow_size.value(), 5.5)

        self.window.btn_config_label.click()
        self.app.processEvents()

        self.assertFalse(self.window.is_config_label_mode)
        self.assertTrue(self.window.config_label_group.isHidden())
        self.assertFalse(self.window.arrow_handle_artists_by_side)

    def test_saved_sizes_are_restored_in_a_new_window(self):
        self.window.spin_angle_font_size.setValue(37)
        self.window.spin_baseline_size.setValue(4.0)
        self.window.spin_arrow_size.setValue(6.0)
        self.window.close()
        self.app.processEvents()

        reloaded_settings = QSettings(
            self.settings_path,
            QSettings.Format.IniFormat,
        )
        pixmap = QPixmap(100, 60)
        pixmap.fill(Qt.GlobalColor.black)
        self.window = DropletAnalysisWindow(
            FakeDropletAnalysisViewModel(),
            pixmap,
            settings=reloaded_settings,
        )

        self.assertEqual(self.window.angle_label_font_size, 37)
        self.assertEqual(self.window.spin_angle_font_size.value(), 37)
        self.assertAlmostEqual(self.window.baseline_size, 4.0)
        self.assertAlmostEqual(self.window.spin_baseline_size.value(), 4.0)
        self.assertAlmostEqual(self.window.arrow_size, 6.0)
        self.assertAlmostEqual(self.window.spin_arrow_size.value(), 6.0)

    def test_label_drag_is_free_and_arrow_drag_is_vertical_only(self):
        self.window.btn_config_label.click()
        self.window.canvas.draw()

        label = self.window.angle_text_artists_by_side["left"]
        old_label_pos = tuple(label.get_position())
        bbox = label.get_window_extent(self.window.canvas.get_renderer())
        press = MouseEvent(
            "button_press_event",
            self.window.canvas,
            (bbox.x0 + bbox.x1) / 2.0,
            (bbox.y0 + bbox.y1) / 2.0,
            button=1,
        )
        self.window.on_mouse_press(press)
        move = self._mouse_event_at_data("motion_notify_event", 2.5, 2.0)
        self.window.on_mouse_move(move)
        self.window.on_mouse_release(
            self._mouse_event_at_data("button_release_event", 2.5, 2.0, 1)
        )

        new_label_pos = self.window.angle_label_positions["left"]
        self.assertIsNotNone(new_label_pos)
        self.assertNotEqual(new_label_pos[0], old_label_pos[0])
        self.assertNotEqual(new_label_pos[1], old_label_pos[1])

        side = "left"
        old_tip = self.window.arrow_current_tips[side]
        start = self.window.arrow_start_points[side]
        default_tip = self.window.arrow_default_tips[side]
        arc = self.window.angle_arc_artists_by_side[side]
        old_arc_width = arc.width
        arrow_press = self._mouse_event_at_data(
            "button_press_event",
            old_tip[0],
            old_tip[1],
            1,
        )
        self.window.on_mouse_press(arrow_press)
        arrow_move = self._mouse_event_at_data(
            "motion_notify_event",
            old_tip[0] + 0.8,
            old_tip[1] - 0.35,
        )
        self.window.on_mouse_move(arrow_move)
        self.window.on_mouse_release(
            self._mouse_event_at_data(
                "button_release_event",
                old_tip[0] + 0.8,
                old_tip[1] - 0.35,
                1,
            )
        )

        new_tip = self.window.arrow_current_tips[side]
        default_vector = np.asarray(default_tip) - np.asarray(start)
        resized_vector = np.asarray(new_tip) - np.asarray(start)
        self.assertAlmostEqual(
            default_vector[0] * resized_vector[1]
            - default_vector[1] * resized_vector[0],
            0.0,
        )
        self.assertLess(new_tip[1], old_tip[1])
        self.assertLess(new_tip[0], old_tip[0])
        self.assertLess(self.window.arrow_length_scales[side], 1.0)
        self.assertLess(arc.width, old_arc_width)

        self.window.btn_config_label.click()
        self.assertEqual(
            tuple(self.window.angle_text_artists_by_side["left"].get_position()),
            new_label_pos,
        )
        self.assertEqual(self.window.arrow_current_tips["left"], new_tip)

    def test_saved_original_is_cropped_to_axes_and_fills_image_editor_view(self):
        self.window.canvas.draw()
        full_canvas_image = self.window.canvas.grab().toImage()
        axes_position = self.window.ax.get_position()

        selected_path = os.path.join(
            self.settings_temp_dir.name,
            "selected_analysis.png",
        )
        with patch(
            "App.Presentation.Views.Widgets.DropletAnalysisWindow."
            "QFileDialog.getSaveFileName",
            return_value=(selected_path, "PNG Images (*.png)"),
        ) as save_dialog:
            self.window.on_save_clicked()
        self.app.processEvents()

        save_dialog.assert_called_once()
        self.assertEqual(
            self.window.view_model.saved_file_path,
            selected_path,
        )
        saved_image = self.window.view_model.saved_rendered_image
        self.assertIsNotNone(saved_image)
        self.assertFalse(saved_image.isNull())
        self.assertLess(saved_image.width(), full_canvas_image.width())
        self.assertLess(saved_image.height(), full_canvas_image.height())
        self.assertAlmostEqual(
            saved_image.width() / saved_image.height(),
            5.0 / 3.0,
            delta=0.02,
        )
        self.assertAlmostEqual(
            saved_image.width() / full_canvas_image.width(),
            axes_position.width,
            delta=0.01,
        )
        self.assertAlmostEqual(
            saved_image.height() / full_canvas_image.height(),
            axes_position.height,
            delta=0.01,
        )

        # The synthetic source is black across its full 5 x 3 extent. A white
        # corner would indicate that FigureCanvas padding was still exported.
        corner = saved_image.pixelColor(1, 1)
        self.assertLess(corner.red(), 24)
        self.assertLess(corner.green(), 24)
        self.assertLess(corner.blue(), 24)

        image_canvas = ImageCanvas()
        image_canvas.resize(900, 600)
        image_canvas.set_pixmap(QPixmap.fromImage(saved_image))
        image_canvas.show()
        self.app.processEvents()
        viewer_image = image_canvas.grab().toImage()
        plot_rect = image_canvas._plot_rect()
        for x_ratio, y_ratio in (
            (0.02, 0.02),
            (0.98, 0.02),
            (0.02, 0.98),
            (0.98, 0.98),
        ):
            color = viewer_image.pixelColor(
                round(plot_rect.left() + x_ratio * plot_rect.width()),
                round(plot_rect.top() + y_ratio * plot_rect.height()),
            )
            self.assertLess(color.red(), 32)
            self.assertLess(color.green(), 32)
            self.assertLess(color.blue(), 32)
        image_canvas.close()

    def test_save_analysis_cancel_keeps_ui_and_does_not_render(self):
        with patch(
            "App.Presentation.Views.Widgets.DropletAnalysisWindow."
            "QFileDialog.getSaveFileName",
            return_value=("", ""),
        ) as save_dialog:
            self.window.on_save_clicked()

        save_dialog.assert_called_once()
        self.assertIsNone(self.window.view_model.saved_rendered_image)
        self.assertIsNone(self.window.view_model.saved_file_path)
        self.assertTrue(self.window.btn_save.isEnabled())


if __name__ == "__main__":
    unittest.main()
