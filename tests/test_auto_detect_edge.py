import unittest

import cv2
import numpy as np

from App.Models.Analysis.DropletAnalysis import auto_detect_edge_points


class AutoDetectEdgeTests(unittest.TestCase):
    IMAGE_WIDTH = 900
    IMAGE_HEIGHT = 600
    PHYSICAL_WIDTH = 5.0
    PHYSICAL_HEIGHT = 3.0
    BASELINE_Y_PX = 430
    LEFT_CONTACT_X_PX = 270
    RIGHT_CONTACT_X_PX = 630

    def _pixel_x_to_physical(self, x_value):
        return (
            float(x_value)
            * self.PHYSICAL_WIDTH
            / (self.IMAGE_WIDTH - 1)
        )

    def _pixel_y_to_physical(self, y_value):
        return self.PHYSICAL_HEIGHT - (
            float(y_value)
            * self.PHYSICAL_HEIGHT
            / (self.IMAGE_HEIGHT - 1)
        )

    def _physical_points_to_pixels(self, points):
        points_array = np.asarray(points, dtype=np.float64)
        return np.column_stack(
            (
                points_array[:, 0]
                * (self.IMAGE_WIDTH - 1)
                / self.PHYSICAL_WIDTH,
                (
                    self.PHYSICAL_HEIGHT - points_array[:, 1]
                )
                * (self.IMAGE_HEIGHT - 1)
                / self.PHYSICAL_HEIGHT,
            )
        )

    def _baseline_coefficients(self):
        baseline_y = self._pixel_y_to_physical(self.BASELINE_Y_PX)
        return (0.0, 1.0, -baseline_y)

    def _baseline_anchors(
        self,
        left_x=None,
        right_x=None,
    ):
        baseline_y = self._pixel_y_to_physical(self.BASELINE_Y_PX)
        left_x = (
            self.LEFT_CONTACT_X_PX if left_x is None else float(left_x)
        )
        right_x = (
            self.RIGHT_CONTACT_X_PX if right_x is None else float(right_x)
        )
        return (
            (
                self._pixel_x_to_physical(left_x),
                baseline_y,
            ),
            (
                self._pixel_x_to_physical(right_x),
                baseline_y,
            ),
        )

    def _make_sessile_droplet_image(
        self,
        *,
        include_droplet=True,
        needle_top=0,
    ):
        image = np.full(
            (self.IMAGE_HEIGHT, self.IMAGE_WIDTH),
            242,
            dtype=np.uint8,
        )

        if include_droplet:
            cv2.ellipse(
                image,
                (
                    (self.LEFT_CONTACT_X_PX + self.RIGHT_CONTACT_X_PX)
                    // 2,
                    self.BASELINE_Y_PX,
                ),
                (
                    (
                        self.RIGHT_CONTACT_X_PX
                        - self.LEFT_CONTACT_X_PX
                    )
                    // 2,
                    125,
                ),
                0,
                0,
                360,
                65,
                -1,
            )

        # A high-contrast needle is intentionally larger/taller than the cap.
        cv2.rectangle(
            image,
            (410, needle_top),
            (490, 230),
            18,
            -1,
        )

        # Strong substrate and reflection below the baseline must be ignored.
        cv2.rectangle(
            image,
            (0, self.BASELINE_Y_PX + 2),
            (self.IMAGE_WIDTH - 1, self.IMAGE_HEIGHT - 1),
            25,
            -1,
        )
        cv2.ellipse(
            image,
            (450, self.BASELINE_Y_PX + 80),
            (150, 72),
            0,
            0,
            360,
            80,
            -1,
        )
        return image

    def _detect(self, image, num_points=80, baseline_anchors=None):
        if baseline_anchors is None:
            baseline_anchors = self._baseline_anchors()
        return auto_detect_edge_points(
            image,
            num_points,
            physical_width=self.PHYSICAL_WIDTH,
            physical_height=self.PHYSICAL_HEIGHT,
            baseline_coeffs=self._baseline_coefficients(),
            baseline_anchor_points=baseline_anchors,
        )

    def _assert_points_follow_droplet_cap(self, points):
        self.assertEqual(len(points), 80)
        pixels = self._physical_points_to_pixels(points)

        self.assertGreater(float(np.min(pixels[:, 1])), 280.0)
        self.assertLessEqual(
            float(np.max(pixels[:, 1])),
            self.BASELINE_Y_PX,
        )
        self.assertGreater(float(np.ptp(pixels[:, 0])), 300.0)
        self.assertAlmostEqual(
            float(np.min(pixels[:, 0])),
            self.LEFT_CONTACT_X_PX,
            delta=20.0,
        )
        self.assertAlmostEqual(
            float(np.max(pixels[:, 0])),
            self.RIGHT_CONTACT_X_PX,
            delta=20.0,
        )

    def test_rejects_top_connected_needle_and_below_baseline_reflection(self):
        points = self._detect(
            self._make_sessile_droplet_image(needle_top=0)
        )

        self._assert_points_follow_droplet_cap(points)

    def test_rejects_detached_needle_without_two_sided_baseline_contact(self):
        points = self._detect(
            self._make_sessile_droplet_image(needle_top=35)
        )

        self._assert_points_follow_droplet_cap(points)

    def test_returns_no_edge_when_only_a_suspended_needle_is_present(self):
        points = self._detect(
            self._make_sessile_droplet_image(
                include_droplet=False,
                needle_top=35,
            )
        )

        self.assertEqual(points, [])

    def test_refines_a_strongly_blurred_silhouette_to_the_optical_edge(self):
        image = cv2.GaussianBlur(
            self._make_sessile_droplet_image(needle_top=0),
            (0, 0),
            6.0,
        )

        points = self._detect(image, num_points=160)

        self.assertEqual(len(points), 160)
        pixels = self._physical_points_to_pixels(points)
        ellipse_level = (
            ((pixels[:, 0] - 450.0) / 180.0) ** 2
            + ((pixels[:, 1] - self.BASELINE_Y_PX) / 125.0) ** 2
        )
        edge_error = np.abs(ellipse_level - 1.0)
        self.assertLess(float(np.median(edge_error)), 0.01)
        self.assertLess(float(np.percentile(edge_error, 95.0)), 0.025)
        self.assertLess(float(np.max(edge_error)), 0.05)

    def test_localizes_the_outer_rim_instead_of_a_dark_inner_region(self):
        image = np.full(
            (self.IMAGE_HEIGHT, self.IMAGE_WIDTH),
            242,
            dtype=np.uint8,
        )
        cv2.ellipse(
            image,
            (450, self.BASELINE_Y_PX),
            (180, 125),
            0,
            0,
            360,
            180,
            -1,
        )
        cv2.ellipse(
            image,
            (450, self.BASELINE_Y_PX),
            (145, 98),
            0,
            0,
            360,
            65,
            -1,
        )
        cv2.rectangle(image, (410, 0), (490, 230), 18, -1)
        cv2.rectangle(
            image,
            (0, self.BASELINE_Y_PX + 2),
            (self.IMAGE_WIDTH - 1, self.IMAGE_HEIGHT - 1),
            25,
            -1,
        )
        image = cv2.GaussianBlur(image, (0, 0), 3.0)

        points = self._detect(image, num_points=160)

        self.assertEqual(len(points), 160)
        pixels = self._physical_points_to_pixels(points)
        outer_ellipse_level = (
            ((pixels[:, 0] - 450.0) / 180.0) ** 2
            + ((pixels[:, 1] - self.BASELINE_Y_PX) / 125.0) ** 2
        )
        edge_error = np.abs(outer_ellipse_level - 1.0)
        self.assertLess(float(np.percentile(edge_error, 95.0)), 0.025)
        self.assertLess(float(np.max(edge_error)), 0.05)

    def test_baseline_segment_may_be_wider_than_the_droplet_footprint(self):
        image = np.full(
            (self.IMAGE_HEIGHT, self.IMAGE_WIDTH),
            242,
            dtype=np.uint8,
        )
        cv2.ellipse(
            image,
            (450, self.BASELINE_Y_PX),
            (90, 90),
            0,
            0,
            360,
            65,
            -1,
        )
        cv2.rectangle(image, (410, 0), (490, 230), 18, -1)
        cv2.rectangle(
            image,
            (0, self.BASELINE_Y_PX + 2),
            (self.IMAGE_WIDTH - 1, self.IMAGE_HEIGHT - 1),
            25,
            -1,
        )

        points = self._detect(
            image,
            baseline_anchors=self._baseline_anchors(50, 850),
        )

        self.assertEqual(len(points), 80)
        pixels = self._physical_points_to_pixels(points)
        self.assertAlmostEqual(float(np.min(pixels[:, 0])), 360.0, delta=5.0)
        self.assertAlmostEqual(float(np.max(pixels[:, 0])), 540.0, delta=5.0)

    def test_prunes_annotation_and_substrate_tails_from_overhanging_drop(self):
        baseline_y_px = 500
        circle_center = np.array((450.0, 300.0))
        circle_radius = 220.0
        image = np.full(
            (self.IMAGE_HEIGHT, self.IMAGE_WIDTH),
            242,
            dtype=np.uint8,
        )
        cv2.circle(image, (450, 300), 220, 65, -1)

        # Low-contrast branches and an elevated substrate ridge are connected
        # to the permissive mask but are not persistent liquid-air interfaces.
        cv2.line(image, (254, 400), (120, 480), 175, 8)
        cv2.line(image, (646, 400), (780, 480), 175, 8)
        cv2.rectangle(
            image,
            (0, 485),
            (self.IMAGE_WIDTH - 1, self.IMAGE_HEIGHT - 1),
            175,
            -1,
        )

        baseline_y = self._pixel_y_to_physical(baseline_y_px)
        contact_half_span = np.sqrt(
            circle_radius ** 2
            - (baseline_y_px - circle_center[1]) ** 2
        )
        left_contact = circle_center[0] - contact_half_span
        right_contact = circle_center[0] + contact_half_span
        anchors = (
            (self._pixel_x_to_physical(left_contact), baseline_y),
            (self._pixel_x_to_physical(right_contact), baseline_y),
        )

        points = auto_detect_edge_points(
            image,
            240,
            physical_width=self.PHYSICAL_WIDTH,
            physical_height=self.PHYSICAL_HEIGHT,
            baseline_coeffs=(0.0, 1.0, -baseline_y),
            baseline_anchor_points=anchors,
        )

        self.assertEqual(len(points), 240)
        pixels = self._physical_points_to_pixels(points)
        self.assertAlmostEqual(float(np.min(pixels[:, 0])), 230.0, delta=3.0)
        self.assertAlmostEqual(float(np.max(pixels[:, 0])), 670.0, delta=3.0)
        self.assertAlmostEqual(float(pixels[0, 0]), left_contact, delta=1.0)
        self.assertAlmostEqual(float(pixels[-1, 0]), right_contact, delta=1.0)

        visible_interface = pixels[:, 1] < baseline_y_px - 25.0
        radial_error = np.abs(
            np.hypot(
                pixels[:, 0] - circle_center[0],
                pixels[:, 1] - circle_center[1],
            )
            - circle_radius
        )
        self.assertLess(
            float(np.percentile(radial_error[visible_interface], 95.0)),
            1.5,
        )
        self.assertLess(float(np.max(radial_error[visible_interface])), 3.0)


if __name__ == "__main__":
    unittest.main()
