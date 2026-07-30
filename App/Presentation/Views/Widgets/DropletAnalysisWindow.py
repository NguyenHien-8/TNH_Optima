###############################################################
# @file App/Presentation/Views/Widgets/DropletAnalysisWindow.py
# Author: TRAN NGUYEN HIEN
# Email: trannguyenhien29085@gmail.com
###############################################################
import os
import numpy as np
from pathlib import Path

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QGroupBox, QSplitter, QRadioButton,
    QTextEdit, QMessageBox, QButtonGroup, QInputDialog, QComboBox, QMenu,
    QLabel, QSpinBox, QDoubleSpinBox, QSizePolicy, QStyle, QFileDialog
)
from PyQt6.QtCore import QRect, Qt, QTimer, QSettings, QSize, pyqtSlot
from PyQt6.QtGui import QPixmap, QIcon, QCursor

import matplotlib
matplotlib.use('Qt5Agg')
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.patches import Arc, FancyArrowPatch, Rectangle

from App.Infrastructure.Helpers.ResourceHelper import apply_stylesheet, resource_path
from App.Infrastructure.Helpers.WindowOwnershipHelper import (
    configure_secondary_window,
    fit_window_to_available_screen,
    resolve_window_owner,
)


class DropletAnalysisWindow(QMainWindow):
    """
    Enhanced GUI-only version:
    - Keep original droplet angle calculation algorithm unchanged
    - Redesign overlay rendering to resemble reference contact-angle images:
        + original grayscale image as main view
        + clean baseline
        + cyan tangent arrows
        + angle arcs near contact points
        + soft angle labels
    - Preserve existing structure / tools / logic flow

    [PATCH 1]
    - Removed coordinate text rendering for measurement points and baseline points
    - Preserved all GUI / algorithm / structure / interaction logic
    - Kept point deletion support by attaching _point_index to point artists directly

    [PATCH 2]
    - Save Analysis Results always opens QFileDialog
    - Remembers the last successful destination independently
    - Suggests a timestamped PNG name derived from the source image

    [PATCH 3]
    - Saved image no longer has black border
    - Only save flow is adjusted; on-screen GUI remains unchanged
    """

    _instances = []
    MEASURE_THRESHOLD = 0.02
    SELECTION_DRAG_THRESHOLD_PX = 5
    DEFAULT_ANGLE_LABEL_FONT_SIZE = 25
    MIN_ANGLE_LABEL_FONT_SIZE = 8
    MAX_ANGLE_LABEL_FONT_SIZE = 72
    MIN_ARROW_LENGTH_SCALE = 0.12
    ANGLE_FONT_SIZE_SETTING_KEY = "DropletAnalysis/angle_label_font_size"
    DEFAULT_BASELINE_SIZE = 2.5
    DEFAULT_ARROW_SIZE = 3.0
    MIN_OVERLAY_LINE_SIZE = 0.5
    MAX_OVERLAY_LINE_SIZE = 10.0
    BASELINE_SIZE_SETTING_KEY = "DropletAnalysis/baseline_size"
    ARROW_SIZE_SETTING_KEY = "DropletAnalysis/arrow_size"

    def __init__(
        self,
        view_model,
        pixmap,
        parent=None,
        source_image_path=None,
        item_path=None,
        project_name=None,
        item_name=None,
        settings=None,
    ):
        # Keep a logical MainView owner without creating a native transient
        # relationship, so restoring MainView cannot restore this window too.
        super().__init__(None, Qt.WindowType.Window)
        DropletAnalysisWindow._instances.append(self)

        self.screen_anchor = parent
        self.main_view = resolve_window_owner(parent)
        self.view_model = view_model
        self.input_pixmap = pixmap
        self._close_when_idle = False
        self._screen_fit_applied = False

        # ===== Save-dialog context =====
        self.source_image_path = source_image_path
        self.item_path = item_path
        self.project_name = project_name
        self.item_name = item_name

        self.setWindowTitle(
            self.build_window_title(
                source_image_path=source_image_path,
                project_name=project_name,
                item_name=item_name,
            )
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("DropletAnalysisWindow")

        self.view_model.image_loaded.connect(self.on_image_loaded)
        self.view_model.image_data_ready.connect(self.view_model.perform_analysis)
        self.view_model.analysis_completed.connect(self.on_analysis_completed)
        self.view_model.baseline_completed.connect(self._on_baseline_completed)
        self.view_model.edges_detected.connect(self._on_edges_detected)
        self.view_model.droplet_analysis_completed.connect(
            self._on_droplet_analysis_finished
        )
        self.view_model.save_completed.connect(self._on_save_completed)
        self.view_model.operation_failed.connect(self._on_operation_failed)
        self.view_model.workers_idle.connect(self._on_workers_idle)
        self.view_model.error_occurred.connect(self.on_error)
        self.view_model.configure_storage_context(
            source_image_path=source_image_path,
            item_path=item_path,
        )

        self.default_xlim = (0.0, 5.0)
        self.default_ylim = (0.0, 3.0)
        self.xlim = self.default_xlim
        self.ylim = self.default_ylim

        self.x_bound = (0.0, 5.0)
        self.y_bound = (0.0, 3.0)

        self.is_panning = False
        self.pan_start_x = 0.0
        self.pan_start_y = 0.0

        self.baseline_method = "Double Points"
        self.analysis_method = "Ellipsoid Fit"

        self.is_measuring = False
        self.measurement_points = []
        self.measurement_artists = []
        self.selected_measurement_indices = set()
        self.selection_rect_artist = None
        self.selection_start_point = None
        self.selection_start_canvas = None
        self.pending_measure_click = None
        self.pending_measure_click_canvas = None
        self.is_selecting_measurement_points = False
        self.crosshair_lines = []
        self.dragging_point_index = -1

        self.is_baseline_mode = False
        self.baseline_points = []
        self.baseline_artists = []
        self.baseline_line = None
        self.baseline_coeffs = None
        self.baseline_anchor_points = None

        self.last_analysis_results = None
        self.tangent_artists = []
        self.angle_text_artists = []
        self.angle_text_artists_by_side = {}
        self.tangent_arrow_artists_by_side = {}
        self.arrow_handle_artists_by_side = {}
        self.angle_arc_artists_by_side = {}
        self.baseline_guide_artists_by_side = {}
        self.angle_geometry_by_side = {}
        self.arrow_start_points = {}
        self.arrow_default_tips = {}
        self.arrow_current_tips = {}
        self.show_original = True
        self.angle_mode = "Two Angles"

        self.is_config_label_mode = False
        self.settings = (
            settings
            if settings is not None
            else QSettings("TNH", "TNH Optima")
        )
        self.angle_label_font_size = self._load_angle_label_font_size()
        self.baseline_size = self._load_overlay_line_size(
            self.BASELINE_SIZE_SETTING_KEY,
            self.DEFAULT_BASELINE_SIZE,
        )
        self.arrow_size = self._load_overlay_line_size(
            self.ARROW_SIZE_SETTING_KEY,
            self.DEFAULT_ARROW_SIZE,
        )
        self.angle_label_positions = {"left": None, "right": None}
        self.arrow_length_scales = {"left": 1.0, "right": 1.0}
        self.config_drag_kind = None
        self.config_drag_side = None
        self.config_drag_offset = (0.0, 0.0)

        # visual tuning for reference-style overlay
        self.overlay_cfg = {
            "baseline_color": "#b2aafa",
            "baseline_alpha": 0.95,
            "baseline_width": self.baseline_size,

            "tangent_color": "#1900ff",
            "tangent_alpha": 0.95,
            "tangent_width": self.arrow_size,

            "arc_color": "#cfd7ea",
            "arc_alpha": 0.75,
            "arc_width": 1.1,

            "label_color": "#1900ff",
            "label_bbox_face": (0.10, 0.14, 0.18, 0.18),
            "label_bbox_edge": (0.80, 0.90, 1.00, 0.25),

            "contact_color": "#f8d7da",
            "contact_edge": "#ffffff",
            "contact_size": 18,

            "measure_point_color": "#ff5a5a",
            "baseline_point_color": "#5aa6ff",
            "crosshair_color": "#7CFFB2",
        }

        self.setup_ui()
        self.load_style()
        configure_secondary_window(self, self.main_view)

        self._mpl_connection_ids = [
            self.canvas.mpl_connect('scroll_event', self.on_scroll),
            self.canvas.mpl_connect('button_press_event', self.on_mouse_press),
            self.canvas.mpl_connect('button_release_event', self.on_mouse_release),
            self.canvas.mpl_connect('motion_notify_event', self.on_mouse_move),
        ]

        self.view_model.load_image(self.input_pixmap.toImage())

    @staticmethod
    def build_window_title(
        source_image_path=None,
        project_name=None,
        item_name=None,
    ):
        """Build a descriptive title from the image's project context."""
        project = project_name.strip() if isinstance(project_name, str) else ""
        item = item_name.strip() if isinstance(item_name, str) else ""
        image_name = ""

        if isinstance(source_image_path, str) and source_image_path.strip():
            image_path = Path(source_image_path)
            image_name = image_path.name
            media_dir = image_path.parent

            # Project images use <Project>/<Item>/Image/<Image>.
            if media_dir.name.casefold() == "image":
                item = media_dir.parent.name or item
                project = media_dir.parent.parent.name or project

        context = [name for name in (project, item, image_name) if name]
        if not context:
            return "Droplet Analysis"
        return f"Droplet Analysis - {'/'.join(context)}"

    def _load_angle_label_font_size(self):
        try:
            value = int(
                self.settings.value(
                    self.ANGLE_FONT_SIZE_SETTING_KEY,
                    self.DEFAULT_ANGLE_LABEL_FONT_SIZE,
                )
            )
        except (TypeError, ValueError):
            value = self.DEFAULT_ANGLE_LABEL_FONT_SIZE
        return min(
            max(value, self.MIN_ANGLE_LABEL_FONT_SIZE),
            self.MAX_ANGLE_LABEL_FONT_SIZE,
        )

    def _load_overlay_line_size(self, setting_key, default_value):
        try:
            value = float(self.settings.value(setting_key, default_value))
        except (TypeError, ValueError):
            value = float(default_value)
        return min(
            max(value, self.MIN_OVERLAY_LINE_SIZE),
            self.MAX_OVERLAY_LINE_SIZE,
        )

    def showEvent(self, event):
        super().showEvent(event)
        if not self._screen_fit_applied:
            fit_window_to_available_screen(
                self,
                preferred_size=(1100, 760),
                anchor=(
                    self.screen_anchor
                    if self.screen_anchor is not None
                    else self.main_view
                ),
                width_ratio=0.94,
                height_ratio=0.90,
                minimum_size=(640, 420),
            )
            self._screen_fit_applied = True
        configure_secondary_window(self, self.main_view)

    # =========================
    # UI
    # =========================
    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left panel
        chart_widget = QWidget()
        chart_layout = QVBoxLayout(chart_widget)
        chart_layout.setContentsMargins(0, 0, 0, 0)

        self.figure = Figure(figsize=(7, 5), dpi=100, facecolor="#111111")
        self.canvas = FigureCanvas(self.figure)
        chart_layout.addWidget(self.canvas)

        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.clicked.connect(self.on_refresh_clicked)

        self.btn_save = QPushButton("Save Analysis Results")
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.clicked.connect(self.on_save_clicked)

        self.btn_analysis_manually = QPushButton("Analysis Manually")
        self.btn_analysis_manually.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_analysis_manually.clicked.connect(self.on_analysis_manually_clicked)

        self.btn_delete_measure_point = QPushButton("Delete Measure Point")
        self.btn_delete_measure_point.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_delete_measure_point.clicked.connect(self.on_delete_measure_point_clicked)

        self.btn_config_label = QPushButton("Config Label")
        self.btn_config_label.setCheckable(True)
        self.btn_config_label.setEnabled(False)
        self.btn_config_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_config_label.setToolTip(
            "Available after analysis. Click to configure labels and arrow heights."
        )
        self.btn_config_label.toggled.connect(self.on_config_label_toggled)

        self.cb_angle_mode = QComboBox()
        self.cb_angle_mode.addItems(["Left Angle", "Right Angle", "Two Angles"])
        self.cb_angle_mode.setCurrentText("Two Angles")
        self.cb_angle_mode.currentTextChanged.connect(self.on_angle_mode_changed)

        self.action_bar = QWidget()
        self.action_bar.setObjectName("AnalysisActionBar")
        self.action_bar.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Maximum,
        )
        action_bar_layout = QHBoxLayout(self.action_bar)
        action_bar_layout.setContentsMargins(0, 0, 0, 0)
        action_bar_layout.setSpacing(6)
        action_bar_layout.addWidget(self.btn_refresh)
        action_bar_layout.addWidget(self.btn_save)
        action_bar_layout.addWidget(self.btn_analysis_manually)
        action_bar_layout.addWidget(self.btn_delete_measure_point)
        action_bar_layout.addWidget(self.btn_config_label)
        action_bar_layout.addWidget(self.cb_angle_mode)
        action_bar_layout.addStretch()
        chart_layout.addWidget(self.action_bar)

        self.config_label_group = QGroupBox("Label and Arrow Configuration")
        self.config_label_group.setObjectName("LabelConfigGroup")
        self.config_label_group.setSizePolicy(
            QSizePolicy.Policy.Maximum,
            QSizePolicy.Policy.Maximum,
        )
        self.config_label_group.setMaximumWidth(760)
        config_label_layout = QHBoxLayout(self.config_label_group)

        font_size_label = QLabel("Angle Size:")
        config_label_layout.addWidget(font_size_label)
        self.spin_angle_font_size = QSpinBox()
        self.spin_angle_font_size.setRange(
            self.MIN_ANGLE_LABEL_FONT_SIZE,
            self.MAX_ANGLE_LABEL_FONT_SIZE,
        )
        self.spin_angle_font_size.setValue(self.angle_label_font_size)
        self.spin_angle_font_size.setSuffix(" pt")
        self.spin_angle_font_size.setMaximumWidth(90)
        self.spin_angle_font_size.setToolTip(
            "Change and automatically save the font size of both angle labels."
        )
        self.spin_angle_font_size.valueChanged.connect(
            self.on_angle_font_size_changed
        )
        config_label_layout.addWidget(self.spin_angle_font_size)

        baseline_size_label = QLabel("Baseline Size:")
        config_label_layout.addWidget(baseline_size_label)
        self.spin_baseline_size = QDoubleSpinBox()
        self.spin_baseline_size.setRange(
            self.MIN_OVERLAY_LINE_SIZE,
            self.MAX_OVERLAY_LINE_SIZE,
        )
        self.spin_baseline_size.setDecimals(1)
        self.spin_baseline_size.setSingleStep(0.5)
        self.spin_baseline_size.setValue(self.baseline_size)
        self.spin_baseline_size.setSuffix(" pt")
        self.spin_baseline_size.setMaximumWidth(95)
        self.spin_baseline_size.setToolTip(
            "Change and automatically save the baseline line width."
        )
        self.spin_baseline_size.valueChanged.connect(
            self.on_baseline_size_changed
        )
        config_label_layout.addWidget(self.spin_baseline_size)

        arrow_size_label = QLabel("Arrow Size:")
        config_label_layout.addWidget(arrow_size_label)
        self.spin_arrow_size = QDoubleSpinBox()
        self.spin_arrow_size.setRange(
            self.MIN_OVERLAY_LINE_SIZE,
            self.MAX_OVERLAY_LINE_SIZE,
        )
        self.spin_arrow_size.setDecimals(1)
        self.spin_arrow_size.setSingleStep(0.5)
        self.spin_arrow_size.setValue(self.arrow_size)
        self.spin_arrow_size.setSuffix(" pt")
        self.spin_arrow_size.setMaximumWidth(95)
        self.spin_arrow_size.setToolTip(
            "Change and automatically save the left/right arrow line width."
        )
        self.spin_arrow_size.valueChanged.connect(
            self.on_arrow_size_changed
        )
        config_label_layout.addWidget(self.spin_arrow_size)

        self.btn_reset_label_layout = QPushButton()
        self.btn_reset_label_layout.setObjectName("ResetLabelLayoutButton")
        self.btn_reset_label_layout.setAccessibleName("Reset Label Layout")
        self.btn_reset_label_layout.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload)
        )
        self.btn_reset_label_layout.setIconSize(QSize(18, 18))
        self.btn_reset_label_layout.setFixedSize(20, 20)
        self.btn_reset_label_layout.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reset_label_layout.setToolTip(
            "Reset label positions and arrow lengths. Saved sizes are preserved."
        )
        self.btn_reset_label_layout.clicked.connect(
            self.on_reset_label_layout_clicked
        )
        config_label_layout.addWidget(self.btn_reset_label_layout)
        config_label_layout.addStretch()

        self.config_label_group.setVisible(False)
        chart_layout.addWidget(
            self.config_label_group,
            alignment=Qt.AlignmentFlag.AlignLeft,
        )

        splitter.addWidget(chart_widget)
        splitter.setStretchFactor(0, 3)

        # Right panel
        info_widget = QWidget()
        info_layout = QVBoxLayout(info_widget)
        info_layout.setContentsMargins(0, 0, 0, 0)

        info_group = QGroupBox("Analysis Information")
        info_group_layout = QVBoxLayout(info_group)

        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        self.info_text.setMaximumHeight(250)
        self.info_text.setStyleSheet("""
            QTextEdit {
                border: 1px solid #cccccc;
                border-radius: 6px;
                padding: 8px;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 10pt;
                background: #fcfcfc;
            }
        """)
        info_group_layout.addWidget(self.info_text)
        info_layout.addWidget(info_group)

        tool_group = QGroupBox("Tool")
        tool_group_layout = QVBoxLayout(tool_group)
        tool_group_layout.setContentsMargins(5, 5, 5, 5)
        tool_group_layout.setSpacing(0)

        tool_btn_layout = QHBoxLayout()
        tool_btn_layout.setContentsMargins(0, 0, 0, 0)

        self.btn_actual_size = QPushButton()
        self.btn_actual_size.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_actual_size.setToolTip("Actual Size")
        icon_path_actual = resource_path(os.path.join(
            "App", "ReSource", "Icon", "DropletAnalysisWindow", "actualsize.svg"
        ))
        if os.path.exists(icon_path_actual):
            self.btn_actual_size.setIcon(QIcon(icon_path_actual))
            self.btn_actual_size.setIconSize(self.btn_actual_size.sizeHint())
        self.btn_actual_size.setMaximumWidth(40)
        self.btn_actual_size.setMaximumHeight(40)
        self.btn_actual_size.clicked.connect(self.on_actual_size_clicked)
        tool_btn_layout.addWidget(self.btn_actual_size)

        tool_btn_layout.addSpacing(10)

        self.btn_baseline = QPushButton()
        self.btn_baseline.setCheckable(True)
        self.btn_baseline.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_baseline.setToolTip("Baseline")
        icon_path_baseline = resource_path(os.path.join(
            "App", "ReSource", "Icon", "DropletAnalysisWindow", "baseline.svg"
        ))
        if os.path.exists(icon_path_baseline):
            self.btn_baseline.setIcon(QIcon(icon_path_baseline))
            self.btn_baseline.setIconSize(self.btn_baseline.sizeHint())
        self.btn_baseline.setMaximumWidth(40)
        self.btn_baseline.setMaximumHeight(40)
        self.btn_baseline.toggled.connect(self.on_baseline_toggled)
        tool_btn_layout.addWidget(self.btn_baseline)

        tool_btn_layout.addSpacing(10)

        self.btn_measure = QPushButton()
        self.btn_measure.setCheckable(True)
        self.btn_measure.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_measure.setToolTip("Measure Point")
        icon_path_measure = resource_path(os.path.join(
            "App", "ReSource", "Icon", "DropletAnalysisWindow", "point.svg"
        ))
        if os.path.exists(icon_path_measure):
            self.btn_measure.setIcon(QIcon(icon_path_measure))
            self.btn_measure.setIconSize(self.btn_measure.sizeHint())
        self.btn_measure.setMaximumWidth(40)
        self.btn_measure.setMaximumHeight(40)
        self.btn_measure.toggled.connect(self.on_measure_toggled)
        tool_btn_layout.addWidget(self.btn_measure)

        tool_btn_layout.addSpacing(10)

        self.btn_auto_detect = QPushButton()
        self.btn_auto_detect.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_auto_detect.setToolTip("Auto Detect Edge")
        icon_path_auto = resource_path(os.path.join(
            "App", "ReSource", "Icon", "DropletAnalysisWindow", "autodetectedge.svg"
        ))
        if os.path.exists(icon_path_auto):
            self.btn_auto_detect.setIcon(QIcon(icon_path_auto))
            self.btn_auto_detect.setIconSize(self.btn_auto_detect.sizeHint())
        self.btn_auto_detect.setMaximumWidth(40)
        self.btn_auto_detect.setMaximumHeight(40)
        self.btn_auto_detect.clicked.connect(self.on_auto_detect_clicked)
        tool_btn_layout.addWidget(self.btn_auto_detect)

        tool_btn_layout.addStretch()
        tool_group_layout.addLayout(tool_btn_layout)
        info_layout.addWidget(tool_group)

        config_group = QGroupBox("Display Settings")
        config_group_layout = QVBoxLayout(config_group)

        self.btn_colormap_viridis = QPushButton("Colormap: Viridis")
        self.btn_colormap_viridis.setCheckable(True)
        config_group_layout.addWidget(self.btn_colormap_viridis)

        self.btn_colormap_plasma = QPushButton("Colormap: Plasma")
        self.btn_colormap_plasma.setCheckable(True)
        config_group_layout.addWidget(self.btn_colormap_plasma)

        self.btn_colormap_hot = QPushButton("Colormap: Hot")
        self.btn_colormap_hot.setCheckable(True)
        config_group_layout.addWidget(self.btn_colormap_hot)

        self.btn_original = QPushButton("Original Image")
        self.btn_original.setCheckable(True)
        self.btn_original.setChecked(True)
        config_group_layout.addWidget(self.btn_original)

        self.display_group = QButtonGroup(self)
        self.display_group.setExclusive(True)
        self.display_group.addButton(self.btn_colormap_viridis)
        self.display_group.addButton(self.btn_colormap_plasma)
        self.display_group.addButton(self.btn_colormap_hot)
        self.display_group.addButton(self.btn_original)

        self.btn_colormap_viridis.toggled.connect(self.on_colormap_toggled)
        self.btn_colormap_plasma.toggled.connect(self.on_colormap_toggled)
        self.btn_colormap_hot.toggled.connect(self.on_colormap_toggled)
        self.btn_original.toggled.connect(self.on_original_toggled)

        info_layout.addWidget(config_group)

        baseline_group = QGroupBox("Set Baseline Manually")
        baseline_layout = QVBoxLayout(baseline_group)

        self.baseline_button_group = QButtonGroup(self)

        self.radio_double = QRadioButton("Double Points")
        self.radio_double.setChecked(True)
        self.radio_double.toggled.connect(self.on_baseline_method_changed)
        baseline_layout.addWidget(self.radio_double)
        self.baseline_button_group.addButton(self.radio_double)

        self.radio_mirror = QRadioButton("Mirror Image Method")
        self.radio_mirror.toggled.connect(self.on_baseline_method_changed)
        baseline_layout.addWidget(self.radio_mirror)
        self.baseline_button_group.addButton(self.radio_mirror)

        info_layout.addWidget(baseline_group)

        analysis_setup_group = QGroupBox("Droplet Analysis Setup")
        analysis_setup_layout = QVBoxLayout(analysis_setup_group)

        self.analysis_button_group = QButtonGroup(self)

        self.radio_ellipsoid = QRadioButton("Ellipsoid Fit")
        self.radio_ellipsoid.setChecked(True)
        self.radio_ellipsoid.toggled.connect(self.on_analysis_method_changed)
        analysis_setup_layout.addWidget(self.radio_ellipsoid)
        self.analysis_button_group.addButton(self.radio_ellipsoid)

        self.radio_young_laplace = QRadioButton("Young-Laplace Fit")
        self.radio_young_laplace.toggled.connect(self.on_analysis_method_changed)
        analysis_setup_layout.addWidget(self.radio_young_laplace)
        self.analysis_button_group.addButton(self.radio_young_laplace)

        info_layout.addWidget(analysis_setup_group)
        info_layout.addStretch()

        splitter.addWidget(info_widget)
        splitter.setStretchFactor(1, 1)
        splitter.setCollapsible(1, False)

        main_layout.addWidget(splitter, stretch=1)

        self.current_colormap = 'viridis'
        self.colormap_buttons = {
            'viridis': self.btn_colormap_viridis,
            'plasma': self.btn_colormap_plasma,
            'hot': self.btn_colormap_hot
        }

        self.ax = None

    def load_style(self):
        apply_stylesheet(self, "DropletAnalysisStyles.qss")

    # =========================
    # slots
    # =========================
    @pyqtSlot()
    def on_image_loaded(self):
        self.update_info_text("Image loaded successfully.")

    @pyqtSlot(object)
    def on_analysis_completed(self, analysis_data):
        if analysis_data:
            self.update_display()
            self.update_analysis_info(analysis_data)

    @pyqtSlot(str)
    def on_error(self, message):
        QMessageBox.critical(self, "Analysis Error", message)
        self.update_info_text(f"Error: {message}")

    # =========================
    # display helpers
    # =========================
    def _get_image_extent(self):
        return (0.0, 5.0, 0.0, 3.0)

    def _setup_axes_for_original(self):
        self.ax.set_facecolor("#111111")
        self.ax.set_xlim(self.xlim)
        self.ax.set_ylim(self.ylim)
        self.ax.set_aspect('equal', adjustable='box')
        self.ax.set_xticks([])
        self.ax.set_yticks([])
        for spine in self.ax.spines.values():
            spine.set_visible(False)

    def _setup_axes_for_heatmap(self):
        self.ax.set_facecolor("white")
        self.ax.set_xlim(self.xlim)
        self.ax.set_ylim(self.ylim)
        self.ax.set_xlabel('x [mm]', fontsize=11)
        self.ax.set_ylabel('y [mm]', fontsize=11)
        self.ax.grid(False)

    def update_display(self):
        try:
            self.figure.clear()
            self.selection_rect_artist = None
            self.ax = self.figure.add_subplot(111)

            if self.show_original:
                img = self.view_model.get_original_display_data()
                if img is None:
                    self.update_info_text("No original image available.")
                    return

                extent = self._get_image_extent()
                self.ax.imshow(
                    img,
                    cmap='gray',
                    extent=extent,
                    origin='upper',
                    aspect='equal',
                    interpolation='bilinear'
                )
                self._setup_axes_for_original()
            else:
                data = self.view_model.get_heatmap_data()
                if data is None:
                    self.update_info_text("No heatmap data available.")
                    return
                X, Y, Z = data
                im = self.ax.contourf(X, Y, Z, levels=20, cmap=self.current_colormap)
                self.figure.colorbar(im, ax=self.ax, label='Values')
                self.ax.set_title('Droplet Analysis - Heatmap', fontsize=12, fontweight='bold')
                self._setup_axes_for_heatmap()

            self._draw_measurement_points()
            self._draw_baseline_points()
            self._draw_baseline()
            if self.last_analysis_results is not None:
                self._draw_analysis_results(self.last_analysis_results)

            self.figure.tight_layout()
            self.canvas.draw_idle()

        except Exception as e:
            self.update_info_text(f"Error updating display: {str(e)}")

    # =========================
    # baseline drawing
    # =========================
    def _line_segment_within_axes(self, a, b, c, xlim, ylim):
        points = []
        eps = 1e-12

        if abs(b) > eps:
            for x in [xlim[0], xlim[1]]:
                y = (-a * x - c) / b
                if ylim[0] - 1e-9 <= y <= ylim[1] + 1e-9:
                    points.append((x, y))

        if abs(a) > eps:
            for y in [ylim[0], ylim[1]]:
                x = (-b * y - c) / a
                if xlim[0] - 1e-9 <= x <= xlim[1] + 1e-9:
                    points.append((x, y))

        unique = []
        for p in points:
            if not any(np.hypot(p[0] - q[0], p[1] - q[1]) < 1e-9 for q in unique):
                unique.append(p)

        if len(unique) >= 2:
            unique.sort(key=lambda p: (p[0], p[1]))
            return unique[0], unique[-1]
        return None

    def _draw_baseline(self):
        if self.ax is None or self.baseline_coeffs is None:
            return

        if self.baseline_line is not None:
            try:
                self.baseline_line.remove()
            except Exception:
                pass
            self.baseline_line = None

        if self.baseline_anchor_points is not None and len(self.baseline_anchor_points) == 2:
            (x1, y1), (x2, y2) = self.baseline_anchor_points
            self.baseline_line = self.ax.plot(
                [x1, x2], [y1, y2],
                color=self.overlay_cfg["baseline_color"],
                linestyle='-',
                linewidth=self.overlay_cfg["baseline_width"],
                alpha=self.overlay_cfg["baseline_alpha"],
                solid_capstyle='round',
                zorder=6
            )[0]
            return

        a, b, c = self.baseline_coeffs
        seg = self._line_segment_within_axes(a, b, c, self.ax.get_xlim(), self.ax.get_ylim())
        if seg is None:
            return

        (x1, y1), (x2, y2) = seg
        self.baseline_line = self.ax.plot(
            [x1, x2], [y1, y2],
            color=self.overlay_cfg["baseline_color"],
            linestyle='-',
            linewidth=self.overlay_cfg["baseline_width"],
            alpha=self.overlay_cfg["baseline_alpha"],
            solid_capstyle='round',
            zorder=6
        )[0]

    def _clear_baseline_points_artists(self):
        for artist in self.baseline_artists:
            try:
                artist.remove()
            except Exception:
                pass
        self.baseline_artists.clear()
        if self.ax is not None:
            self.canvas.draw_idle()

    def _draw_baseline_points(self):
        if self.ax is None:
            return

        self._clear_baseline_points_artists()
        for idx, (x, y) in enumerate(self.baseline_points):
            point = self.ax.plot(
                x, y,
                marker='o',
                linestyle='None',
                markersize=5.5,
                markerfacecolor=self.overlay_cfg["baseline_point_color"],
                markeredgecolor='white',
                markeredgewidth=0.8,
                zorder=9
            )[0]
            point._point_index = idx
            self.baseline_artists.append(point)

        self.canvas.draw_idle()

    # =========================
    # measure points
    # =========================
    def _clear_measurement_artists(self):
        for artist in self.measurement_artists:
            try:
                artist.remove()
            except Exception:
                pass
        self.measurement_artists.clear()

    def _sync_selected_measurement_indices(self):
        max_index = len(self.measurement_points) - 1
        self.selected_measurement_indices = {
            idx for idx in self.selected_measurement_indices
            if 0 <= idx <= max_index
        }

    def _clear_measurement_selection(self, redraw=True):
        self.selected_measurement_indices.clear()
        self._remove_selection_rectangle(redraw=False)
        if redraw:
            self._draw_measurement_points()

    def _set_selected_measurement_indices(self, indices, redraw=True):
        valid_indices = {
            int(idx) for idx in indices
            if 0 <= int(idx) < len(self.measurement_points)
        }
        self.selected_measurement_indices = valid_indices
        if redraw:
            self._draw_measurement_points()

    def _delete_selected_measurement_points(self):
        if not self.selected_measurement_indices:
            return False

        delete_indices = set(self.selected_measurement_indices)
        self.measurement_points = [
            point for idx, point in enumerate(self.measurement_points)
            if idx not in delete_indices
        ]
        deleted_count = len(delete_indices)
        self.selected_measurement_indices.clear()
        self._remove_selection_rectangle(redraw=False)
        self._draw_measurement_points()
        self.update_info_text(f"Deleted {deleted_count} selected measure point(s).")
        return True

    def _draw_measurement_points(self):
        if self.ax is None:
            return

        self._clear_measurement_artists()
        self._sync_selected_measurement_indices()
        for idx, (x, y) in enumerate(self.measurement_points):
            is_selected = idx in self.selected_measurement_indices
            point = self.ax.plot(
                x, y,
                marker='o',
                linestyle='None',
                markersize=6.4 if is_selected else 5.5,
                markerfacecolor='#111111' if is_selected else self.overlay_cfg["measure_point_color"],
                markeredgecolor='#ffd966' if is_selected else 'white',
                markeredgewidth=1.15 if is_selected else 0.8,
                zorder=10 if is_selected else 9
            )[0]
            point._point_index = idx
            self.measurement_artists.append(point)

        self.canvas.draw_idle()

    def _remove_selection_rectangle(self, redraw=True):
        if self.selection_rect_artist is not None:
            try:
                self.selection_rect_artist.remove()
            except Exception:
                pass
            self.selection_rect_artist = None
        if redraw and self.ax is not None:
            self.canvas.draw_idle()

    def _event_data_position(self, event):
        if self.ax is None:
            return None

        xdata = getattr(event, "xdata", None)
        ydata = getattr(event, "ydata", None)
        if xdata is not None and ydata is not None and np.isfinite(xdata) and np.isfinite(ydata):
            return float(xdata), float(ydata)

        x = getattr(event, "x", None)
        y = getattr(event, "y", None)
        if x is None or y is None:
            return None

        try:
            xdata, ydata = self.ax.transData.inverted().transform((x, y))
        except Exception:
            return None

        xlim = self.ax.get_xlim()
        ylim = self.ax.get_ylim()
        xdata = min(max(float(xdata), min(xlim)), max(xlim))
        ydata = min(max(float(ydata), min(ylim)), max(ylim))
        return xdata, ydata

    def _canvas_drag_distance(self, event):
        if self.pending_measure_click_canvas is None:
            return 0.0

        x = getattr(event, "x", None)
        y = getattr(event, "y", None)
        if x is None or y is None:
            return 0.0

        start_x, start_y = self.pending_measure_click_canvas
        return float(np.hypot(x - start_x, y - start_y))

    def _draw_selection_rectangle(self, start_point, end_point):
        if self.ax is None or start_point is None or end_point is None:
            return

        self._remove_selection_rectangle(redraw=False)
        x0, y0 = start_point
        x1, y1 = end_point
        xmin, xmax = sorted((x0, x1))
        ymin, ymax = sorted((y0, y1))
        self.selection_rect_artist = Rectangle(
            (xmin, ymin),
            xmax - xmin,
            ymax - ymin,
            facecolor="#111111",
            edgecolor="#ffd966",
            linewidth=1.1,
            linestyle="--",
            alpha=0.22,
            zorder=8,
        )
        self.ax.add_patch(self.selection_rect_artist)
        self.canvas.draw_idle()

    def _select_measurement_points_in_rect(self, start_point, end_point):
        if start_point is None or end_point is None:
            return

        x0, y0 = start_point
        x1, y1 = end_point
        xmin, xmax = sorted((x0, x1))
        ymin, ymax = sorted((y0, y1))

        indices = [
            idx for idx, (px, py) in enumerate(self.measurement_points)
            if xmin <= px <= xmax and ymin <= py <= ymax
        ]
        self._remove_selection_rectangle(redraw=False)
        self._set_selected_measurement_indices(indices)
        if indices:
            self.update_info_text(
                f"Selected {len(indices)} measure point(s). Right-click selection to delete."
            )
        else:
            self.update_info_text("No measure points selected.")

    def _find_measurement_point_at_event(self, event):
        for artist in self.measurement_artists:
            if hasattr(artist, 'contains') and callable(artist.contains):
                contains, _ = artist.contains(event)
                if contains and hasattr(artist, '_point_index'):
                    idx = artist._point_index
                    if 0 <= idx < len(self.measurement_points):
                        return idx

        pos = self._event_data_position(event)
        if pos is None:
            return None

        x, y = pos
        idx_to_select = None
        best_distance = None
        for idx, (px, py) in enumerate(self.measurement_points):
            dist = np.hypot(px - x, py - y)
            if dist < self.MEASURE_THRESHOLD and (best_distance is None or dist < best_distance):
                idx_to_select = idx
                best_distance = dist
        return idx_to_select

    def _event_global_pos(self, event):
        gui_event = getattr(event, "guiEvent", None)
        if gui_event is not None:
            if hasattr(gui_event, "globalPosition"):
                return gui_event.globalPosition().toPoint()
            if hasattr(gui_event, "globalPos"):
                return gui_event.globalPos()
        return QCursor.pos()

    def _show_measurement_selection_menu(self, event):
        if not self.selected_measurement_indices:
            return False

        menu = QMenu(self)
        delete_action = menu.addAction("Delete")
        selected_action = menu.exec(self._event_global_pos(event))
        if selected_action == delete_action:
            self._delete_selected_measurement_points()
        return True

    def _reset_pending_measure_selection(self):
        self.pending_measure_click = None
        self.pending_measure_click_canvas = None
        self.selection_start_point = None
        self.selection_start_canvas = None
        self.is_selecting_measurement_points = False

    # =========================
    # crosshair
    # =========================
    def _remove_crosshair(self):
        for line in self.crosshair_lines:
            try:
                line.remove()
            except Exception:
                pass
        self.crosshair_lines.clear()
        if self.ax is not None:
            self.canvas.draw_idle()

    def _draw_crosshair(self, x, y):
        if self.ax is None:
            return

        self._remove_crosshair()
        xr = self.ax.get_xlim()[1] - self.ax.get_xlim()[0]
        yr = self.ax.get_ylim()[1] - self.ax.get_ylim()[0]
        size = min(xr, yr) * 0.02

        line1 = self.ax.plot(
            [x - size / 2, x + size / 2],
            [y - size / 2, y + size / 2],
            color=self.overlay_cfg["crosshair_color"],
            linewidth=1.0,
            alpha=0.85,
            zorder=12
        )[0]
        line2 = self.ax.plot(
            [x - size / 2, x + size / 2],
            [y + size / 2, y - size / 2],
            color=self.overlay_cfg["crosshair_color"],
            linewidth=1.0,
            alpha=0.85,
            zorder=12
        )[0]

        self.crosshair_lines = [line1, line2]
        self.canvas.draw_idle()

    # =========================
    # geometry helpers for angle rendering
    # =========================
    def _normalize(self, v):
        v = np.asarray(v, dtype=float)
        n = np.hypot(v[0], v[1])
        if n < 1e-12:
            return None
        return v / n

    def _oriented_baseline_inside_direction(self, contact_pt, footprint_midpoint):
        if self.baseline_coeffs is None:
            return None

        a, b, _ = self.baseline_coeffs
        baseline_dir = self._normalize((b, -a))
        if baseline_dir is None:
            return None

        to_mid = np.asarray(footprint_midpoint, dtype=float) - np.asarray(contact_pt, dtype=float)
        if np.dot(baseline_dir, to_mid) < 0:
            baseline_dir = -baseline_dir
        return baseline_dir

    def _vector_angle_deg(self, v):
        return float(np.degrees(np.arctan2(v[1], v[0])))

    def _short_arc_angles(self, start_deg, end_deg):
        s = start_deg % 360.0
        e = end_deg % 360.0
        diff = (e - s) % 360.0
        if diff > 180.0:
            s, e = e, s
        return s, e

    def _data_radius(self):
        xr = self.ax.get_xlim()[1] - self.ax.get_xlim()[0]
        yr = self.ax.get_ylim()[1] - self.ax.get_ylim()[0]
        return min(xr, yr) * 0.085

    def _label_offset(self):
        xr = self.ax.get_xlim()[1] - self.ax.get_xlim()[0]
        yr = self.ax.get_ylim()[1] - self.ax.get_ylim()[0]
        return min(xr, yr) * 0.07

    def _reset_config_drag(self):
        self.config_drag_kind = None
        self.config_drag_side = None
        self.config_drag_offset = (0.0, 0.0)

    def _reset_label_layout(self):
        self.angle_label_positions = {"left": None, "right": None}
        self.arrow_length_scales = {"left": 1.0, "right": 1.0}
        self._reset_config_drag()

    def _cancel_canvas_edit_modes(self):
        """Leave point-editing modes without triggering modal validation."""
        if self.btn_measure.isChecked():
            self.btn_measure.blockSignals(True)
            self.btn_measure.setChecked(False)
            self.btn_measure.blockSignals(False)
        if self.btn_baseline.isChecked():
            self.btn_baseline.blockSignals(True)
            self.btn_baseline.setChecked(False)
            self.btn_baseline.blockSignals(False)

        self.is_measuring = False
        self.is_baseline_mode = False
        self.dragging_point_index = -1
        self._reset_pending_measure_selection()
        self._clear_measurement_selection(redraw=False)
        self.baseline_points.clear()
        self._clear_baseline_points_artists()
        self._remove_crosshair()

    def _config_target_at_event(self, event):
        if not self.is_config_label_mode:
            return None

        for side, artist in self.angle_text_artists_by_side.items():
            try:
                contains, _ = artist.contains(event)
            except Exception:
                contains = False
            if contains:
                return "label", side

        for side, artist in self.arrow_handle_artists_by_side.items():
            try:
                contains, _ = artist.contains(event)
            except Exception:
                contains = False
            if contains:
                return "arrow", side

        for side, artist in self.tangent_arrow_artists_by_side.items():
            try:
                contains, _ = artist.contains(event)
            except Exception:
                contains = False
            if contains:
                return "arrow", side
        return None

    def _start_config_drag(self, event):
        target = self._config_target_at_event(event)
        if target is None:
            return False

        data_pos = self._event_data_position(event)
        if data_pos is None:
            return False

        kind, side = target
        self.config_drag_kind = kind
        self.config_drag_side = side

        if kind == "label":
            label_pos = self.angle_text_artists_by_side[side].get_position()
            self.config_drag_offset = (
                float(label_pos[0]) - data_pos[0],
                float(label_pos[1]) - data_pos[1],
            )
            self.canvas.setCursor(Qt.CursorShape.SizeAllCursor)
        else:
            current_tip = self.arrow_current_tips.get(side)
            if current_tip is None:
                self._reset_config_drag()
                return False
            self.config_drag_offset = (0.0, float(current_tip[1]) - data_pos[1])
            self.canvas.setCursor(Qt.CursorShape.SizeVerCursor)
        return True

    def _clamp_point_to_axes(self, x, y):
        xlim = self.ax.get_xlim()
        ylim = self.ax.get_ylim()
        return (
            min(max(float(x), min(xlim)), max(xlim)),
            min(max(float(y), min(ylim)), max(ylim)),
        )

    def _clamp_arrow_scale_to_axes(self, start, default_tip, scale):
        """Keep the resized arrow on its original tangent ray and in view."""
        start = np.asarray(start, dtype=float)
        delta = np.asarray(default_tip, dtype=float) - start
        xlim = sorted(self.ax.get_xlim())
        ylim = sorted(self.ax.get_ylim())
        maximum_scale = float("inf")

        for origin, component, bounds in (
            (start[0], delta[0], xlim),
            (start[1], delta[1], ylim),
        ):
            if component > 1e-12:
                maximum_scale = min(
                    maximum_scale,
                    (bounds[1] - origin) / component,
                )
            elif component < -1e-12:
                maximum_scale = min(
                    maximum_scale,
                    (bounds[0] - origin) / component,
                )

        if not np.isfinite(maximum_scale):
            maximum_scale = 1.0
        maximum_scale = max(self.MIN_ARROW_LENGTH_SCALE, maximum_scale)
        return min(
            max(float(scale), self.MIN_ARROW_LENGTH_SCALE),
            maximum_scale,
        )

    def _default_angle_label_position(
        self,
        side,
        contact_point,
        baseline_direction,
        tangent_direction,
        arrow_scale,
    ):
        bisector = self._normalize(baseline_direction + tangent_direction)
        if bisector is None:
            bisector = np.array([0.0, 1.0])

        visual_scale = max(float(arrow_scale), 0.35)
        label_offset = self._label_offset() * visual_scale
        label_pos = np.asarray(contact_point, dtype=float) + bisector * label_offset

        if side == "left":
            label_pos += np.array([-label_offset * 1.35, label_offset * 0.07])
            alignment = "right"
        else:
            label_pos += np.array([label_offset * 1.35, label_offset * 0.07])
            alignment = "left"
        return label_pos, alignment

    def _update_contact_angle_geometry(self, side):
        """Synchronize the arc, baseline guide, and default label with an arrow."""
        geometry = self.angle_geometry_by_side.get(side)
        start = self.arrow_start_points.get(side)
        current_tip = self.arrow_current_tips.get(side)
        if geometry is None or start is None or current_tip is None:
            return

        tangent_direction = self._normalize(
            np.asarray(current_tip, dtype=float) - np.asarray(start, dtype=float)
        )
        if tangent_direction is None:
            return

        contact_point = geometry["contact_point"]
        baseline_direction = geometry["baseline_direction"]
        arrow_scale = self.arrow_length_scales.get(side, 1.0)
        radius = geometry["default_radius"] * arrow_scale

        arc = self.angle_arc_artists_by_side.get(side)
        if arc is not None:
            theta1, theta2 = self._short_arc_angles(
                self._vector_angle_deg(baseline_direction),
                self._vector_angle_deg(tangent_direction),
            )
            arc.set_width(2.0 * radius)
            arc.set_height(2.0 * radius)
            arc.theta1 = theta1
            arc.theta2 = theta2
            arc.stale = True

        guide = self.baseline_guide_artists_by_side.get(side)
        if guide is not None:
            guide_start = contact_point - baseline_direction * radius * 0.35
            guide_end = contact_point + baseline_direction * radius * 0.95
            guide.set_data(
                [guide_start[0], guide_end[0]],
                [guide_start[1], guide_end[1]],
            )

        if self.angle_label_positions.get(side) is None:
            label = self.angle_text_artists_by_side.get(side)
            if label is not None:
                label_pos, _ = self._default_angle_label_position(
                    side,
                    contact_point,
                    baseline_direction,
                    tangent_direction,
                    arrow_scale,
                )
                label.set_position(label_pos)

    def _update_config_drag(self, event):
        if self.config_drag_kind is None or self.config_drag_side is None:
            return False

        data_pos = self._event_data_position(event)
        if data_pos is None:
            return True

        side = self.config_drag_side
        if self.config_drag_kind == "label":
            x = data_pos[0] + self.config_drag_offset[0]
            y = data_pos[1] + self.config_drag_offset[1]
            x, y = self._clamp_point_to_axes(x, y)
            artist = self.angle_text_artists_by_side.get(side)
            if artist is not None:
                artist.set_position((x, y))
                self.angle_label_positions[side] = (x, y)
        else:
            default_tip = self.arrow_default_tips.get(side)
            start = self.arrow_start_points.get(side)
            arrow = self.tangent_arrow_artists_by_side.get(side)
            if default_tip is None or start is None or arrow is None:
                return True

            _, requested_tip_y = self._clamp_point_to_axes(
                default_tip[0],
                data_pos[1] + self.config_drag_offset[1],
            )
            default_delta = (
                np.asarray(default_tip, dtype=float)
                - np.asarray(start, dtype=float)
            )
            if abs(default_delta[1]) < 1e-12:
                return True

            requested_scale = (
                requested_tip_y - float(start[1])
            ) / float(default_delta[1])
            arrow_scale = self._clamp_arrow_scale_to_axes(
                start,
                default_tip,
                requested_scale,
            )
            current_tip_array = (
                np.asarray(start, dtype=float) + default_delta * arrow_scale
            )
            current_tip = (
                float(current_tip_array[0]),
                float(current_tip_array[1]),
            )
            self.arrow_length_scales[side] = arrow_scale
            self.arrow_current_tips[side] = current_tip
            arrow.set_positions(start, current_tip)

            handle = self.arrow_handle_artists_by_side.get(side)
            if handle is not None:
                handle.set_data([current_tip[0]], [current_tip[1]])
            self._update_contact_angle_geometry(side)

        self.canvas.draw_idle()
        return True

    def _update_config_hover_cursor(self, event):
        if not self.is_config_label_mode or self.config_drag_kind is not None:
            return
        target = self._config_target_at_event(event)
        if target is None:
            self.canvas.setCursor(Qt.CursorShape.ArrowCursor)
        elif target[0] == "label":
            self.canvas.setCursor(Qt.CursorShape.SizeAllCursor)
        else:
            self.canvas.setCursor(Qt.CursorShape.SizeVerCursor)

    # =========================
    # analysis overlay drawing
    # =========================
    def _clear_analysis_artists(self):
        for artist in self.tangent_artists + self.angle_text_artists:
            try:
                artist.remove()
            except Exception:
                pass
        self.tangent_artists.clear()
        self.angle_text_artists.clear()
        self.angle_text_artists_by_side.clear()
        self.tangent_arrow_artists_by_side.clear()
        self.arrow_handle_artists_by_side.clear()
        self.angle_arc_artists_by_side.clear()
        self.baseline_guide_artists_by_side.clear()
        self.angle_geometry_by_side.clear()
        self.arrow_start_points.clear()
        self.arrow_default_tips.clear()
        self.arrow_current_tips.clear()
        if self.ax is not None:
            self.canvas.draw_idle()

    def _draw_tangent_arrow(self, side, pt, direction, length):
        start = np.asarray(pt, dtype=float)
        default_end = start + direction * length
        arrow_scale = self._clamp_arrow_scale_to_axes(
            start,
            default_end,
            self.arrow_length_scales.get(side, 1.0),
        )
        self.arrow_length_scales[side] = arrow_scale
        end = start + (default_end - start) * arrow_scale

        arrow = FancyArrowPatch(
            posA=(start[0], start[1]),
            posB=(end[0], end[1]),
            arrowstyle='->',
            mutation_scale=13,
            lw=self.overlay_cfg["tangent_width"],
            color=self.overlay_cfg["tangent_color"],
            alpha=self.overlay_cfg["tangent_alpha"],
            shrinkA=0.0,
            shrinkB=0.0,
            zorder=11
        )
        self.ax.add_patch(arrow)
        self.tangent_artists.append(arrow)
        self.tangent_arrow_artists_by_side[side] = arrow
        self.arrow_start_points[side] = (float(start[0]), float(start[1]))
        self.arrow_default_tips[side] = (
            float(default_end[0]),
            float(default_end[1]),
        )
        self.arrow_current_tips[side] = (float(end[0]), float(end[1]))

        if self.is_config_label_mode:
            handle = self.ax.plot(
                [end[0]],
                [end[1]],
                marker='o',
                linestyle='None',
                markersize=8,
                markerfacecolor='#ffd966',
                markeredgecolor='#202124',
                markeredgewidth=1.0,
                zorder=14,
                picker=7,
            )[0]
            handle._config_side = side
            self.tangent_artists.append(handle)
            self.arrow_handle_artists_by_side[side] = handle
        return arrow_scale

    def _draw_contact_angle_item(self, side, pt, tan_vec, angle_deg, footprint_midpoint):
        if pt is None or tan_vec is None or angle_deg is None:
            return

        tangent_in = self._normalize(tan_vec)
        baseline_in = self._oriented_baseline_inside_direction(pt, footprint_midpoint)
        if tangent_in is None or baseline_in is None:
            return

        pt_arr = np.asarray(pt, dtype=float)
        default_radius = self._data_radius()
        tangent_len = default_radius * 4.6

        sc = self.ax.scatter(
            [pt_arr[0]], [pt_arr[1]],
            s=self.overlay_cfg["contact_size"],
            c=self.overlay_cfg["contact_color"],
            edgecolors=self.overlay_cfg["contact_edge"],
            linewidths=0.8,
            alpha=0.95,
            zorder=12
        )
        self.tangent_artists.append(sc)

        arrow_scale = self._draw_tangent_arrow(
            side,
            pt_arr,
            tangent_in,
            tangent_len,
        )
        radius = default_radius * arrow_scale

        start_deg = self._vector_angle_deg(baseline_in)
        end_deg = self._vector_angle_deg(tangent_in)
        theta1, theta2 = self._short_arc_angles(start_deg, end_deg)

        arc = Arc(
            (pt_arr[0], pt_arr[1]),
            width=2 * radius,
            height=2 * radius,
            angle=0.0,
            theta1=theta1,
            theta2=theta2,
            color=self.overlay_cfg["arc_color"],
            lw=self.overlay_cfg["arc_width"],
            alpha=self.overlay_cfg["arc_alpha"],
            zorder=10
        )
        self.ax.add_patch(arc)
        self.tangent_artists.append(arc)
        self.angle_arc_artists_by_side[side] = arc

        baseline_seg_a = pt_arr - baseline_in * radius * 0.35
        baseline_seg_b = pt_arr + baseline_in * radius * 0.95
        line = self.ax.plot(
            [baseline_seg_a[0], baseline_seg_b[0]],
            [baseline_seg_a[1], baseline_seg_b[1]],
            color=self.overlay_cfg["arc_color"],
            linewidth=0.9,
            alpha=0.60,
            zorder=9
        )[0]
        self.tangent_artists.append(line)
        self.baseline_guide_artists_by_side[side] = line
        self.angle_geometry_by_side[side] = {
            "contact_point": pt_arr,
            "baseline_direction": baseline_in,
            "default_radius": default_radius,
        }

        label_pos, ha = self._default_angle_label_position(
            side,
            pt_arr,
            baseline_in,
            tangent_in,
            arrow_scale,
        )

        configured_label_pos = self.angle_label_positions.get(side)
        if configured_label_pos is not None:
            label_pos = np.asarray(configured_label_pos, dtype=float)

        txt = self.ax.text(
            label_pos[0],
            label_pos[1],
            f"{angle_deg:.1f}°",
            fontsize=self.angle_label_font_size,
            fontweight='bold',
            color=self.overlay_cfg["label_color"],
            ha=ha,
            va='center',
            zorder=13,
            bbox=dict(
                boxstyle='round,pad=0.18',
                facecolor=self.overlay_cfg["label_bbox_face"],
                edgecolor=self.overlay_cfg["label_bbox_edge"],
                linewidth=0.8
            )
        )
        txt._config_side = side
        self.angle_text_artists.append(txt)
        self.angle_text_artists_by_side[side] = txt

    def _draw_analysis_results(self, results: dict):
        if self.ax is None or results is None:
            return

        self._clear_analysis_artists()

        left_pt = results.get('left_point')
        right_pt = results.get('right_point')
        left_tan = results.get('left_tangent')
        right_tan = results.get('right_tangent')
        left_angle = results.get('left_angle')
        right_angle = results.get('right_angle')

        if left_pt is None or right_pt is None:
            return

        footprint_midpoint = (
            (left_pt[0] + right_pt[0]) / 2.0,
            (left_pt[1] + right_pt[1]) / 2.0
        )

        info_parts = []

        if (
            self.angle_mode in ("Left Angle", "Two Angles")
            and left_pt is not None
            and left_tan is not None
            and left_angle is not None
        ):
            self._draw_contact_angle_item(
                "left", left_pt, left_tan, left_angle, footprint_midpoint
            )
            info_parts.append(f"Left contact angle : {left_angle:.2f}°")

        if (
            self.angle_mode in ("Right Angle", "Two Angles")
            and right_pt is not None
            and right_tan is not None
            and right_angle is not None
        ):
            self._draw_contact_angle_item(
                "right", right_pt, right_tan, right_angle, footprint_midpoint
            )
            info_parts.append(f"Right contact angle: {right_angle:.2f}°")

        if left_angle is not None and right_angle is not None and self.angle_mode == "Two Angles":
            mean_angle = (left_angle + right_angle) / 2.0
            info_parts.append(f"Average angle      : {mean_angle:.2f}°")

        self.update_info_text("\n".join(info_parts))
        self.canvas.draw_idle()

    # =========================
    # interactions
    # =========================
    @pyqtSlot(bool)
    def on_config_label_toggled(self, checked):
        if checked and self.last_analysis_results is None:
            self.btn_config_label.blockSignals(True)
            self.btn_config_label.setChecked(False)
            self.btn_config_label.blockSignals(False)
            self.update_info_text(
                "Run droplet analysis before configuring angle labels."
            )
            return

        self.is_config_label_mode = checked
        self.config_label_group.setVisible(checked)
        self._reset_config_drag()

        if checked:
            self._cancel_canvas_edit_modes()
            self.btn_config_label.setToolTip(
                "Click again to finish configuring labels and arrows."
            )
        else:
            self.canvas.setCursor(Qt.CursorShape.ArrowCursor)
            self.btn_config_label.setToolTip(
                "Configure angle labels and arrow heights."
            )

        if self.last_analysis_results is not None:
            self._draw_analysis_results(self.last_analysis_results)

        if checked:
            self.update_info_text(
                "Config Label mode: drag labels freely. Drag each yellow handle "
                "up or down to resize its arrow on the measured tangent; the "
                "angle arc follows automatically."
            )

    @pyqtSlot(int)
    def on_angle_font_size_changed(self, value):
        self.angle_label_font_size = int(value)
        self.settings.setValue(
            self.ANGLE_FONT_SIZE_SETTING_KEY,
            self.angle_label_font_size,
        )
        for artist in self.angle_text_artists:
            artist.set_fontsize(self.angle_label_font_size)
        if self.ax is not None:
            self.canvas.draw_idle()

    @pyqtSlot(float)
    def on_baseline_size_changed(self, value):
        self.baseline_size = min(
            max(float(value), self.MIN_OVERLAY_LINE_SIZE),
            self.MAX_OVERLAY_LINE_SIZE,
        )
        self.overlay_cfg["baseline_width"] = self.baseline_size
        self.settings.setValue(
            self.BASELINE_SIZE_SETTING_KEY,
            self.baseline_size,
        )
        if self.baseline_line is not None:
            try:
                self.baseline_line.set_linewidth(self.baseline_size)
            except (AttributeError, RuntimeError):
                self.baseline_line = None
        if self.ax is not None:
            self.canvas.draw_idle()

    @pyqtSlot(float)
    def on_arrow_size_changed(self, value):
        self.arrow_size = min(
            max(float(value), self.MIN_OVERLAY_LINE_SIZE),
            self.MAX_OVERLAY_LINE_SIZE,
        )
        self.overlay_cfg["tangent_width"] = self.arrow_size
        self.settings.setValue(
            self.ARROW_SIZE_SETTING_KEY,
            self.arrow_size,
        )
        for arrow in self.tangent_arrow_artists_by_side.values():
            try:
                arrow.set_linewidth(self.arrow_size)
            except (AttributeError, RuntimeError):
                continue
        if self.ax is not None:
            self.canvas.draw_idle()

    @pyqtSlot()
    def on_reset_label_layout_clicked(self):
        self._reset_label_layout()
        if self.last_analysis_results is not None:
            self._draw_analysis_results(self.last_analysis_results)
        self.update_info_text(
            "Label positions and arrow lengths restored. Saved sizes preserved."
        )

    @pyqtSlot(bool)
    def on_baseline_toggled(self, checked):
        if checked:
            if self.is_config_label_mode:
                self.btn_config_label.setChecked(False)
            if self.is_measuring:
                self.btn_measure.setChecked(False)
            self.is_baseline_mode = True
            self.baseline_coeffs = None
            self.baseline_anchor_points = None
            if self.baseline_line is not None:
                try:
                    self.baseline_line.remove()
                except Exception:
                    pass
                self.baseline_line = None

            self.baseline_points.clear()
            self._clear_baseline_points_artists()
            self.update_info_text("Baseline mode: click on image to add baseline points.")
        else:
            self.is_baseline_mode = False
            method = self.baseline_method

            if method == "Double Points":
                if len(self.baseline_points) < 2:
                    QMessageBox.warning(
                        self, "Not Enough Points",
                        "Please place at least two points for baseline."
                    )
                    self.baseline_points.clear()
                    self._clear_baseline_points_artists()
                else:
                    points = self.baseline_points[:2]
                    self.baseline_anchor_points = list(points)
                    self.baseline_points.clear()
                    self._clear_baseline_points_artists()
                    self.update_info_text("Computing baseline...")
                    self.view_model.compute_baseline(method, points)

            elif method == "Mirror Image Method":
                if not self.view_model.is_mirror_method_available():
                    QMessageBox.information(
                        self, "Under Development",
                        "Mirror Image Method is currently under development."
                    )
                self.baseline_points.clear()
                self._clear_baseline_points_artists()
            else:
                self.baseline_points.clear()
                self._clear_baseline_points_artists()

            self.canvas.draw_idle()

    @pyqtSlot(str, object)
    def _on_baseline_completed(self, method, coeffs):
        if method != "Double Points":
            return
        if coeffs is None:
            self.baseline_anchor_points = None
            QMessageBox.critical(
                self,
                "Error",
                "Cannot compute baseline from the selected points.",
            )
            return

        self.baseline_coeffs = coeffs
        self._draw_baseline()
        a, b, c = coeffs
        self.update_info_text(
            f"Baseline computed: {a:.3f}x + {b:.3f}y + {c:.3f} = 0"
        )
        self.canvas.draw_idle()

    @pyqtSlot(bool)
    def on_measure_toggled(self, checked):
        if checked:
            if self.is_config_label_mode:
                self.btn_config_label.setChecked(False)
            if self.is_baseline_mode:
                self.btn_baseline.setChecked(False)
            self.is_measuring = True
            self.update_info_text("Measure mode: click to add profile points.")
        else:
            self.is_measuring = False
            self.dragging_point_index = -1
            self._reset_pending_measure_selection()
            self._clear_measurement_selection(redraw=True)
            self.update_info_text("")

    @pyqtSlot()
    def on_auto_detect_clicked(self):
        if not self.view_model.has_image():
            QMessageBox.warning(self, "No Image", "No image loaded.")
            return
        if self.baseline_coeffs is None:
            QMessageBox.warning(
                self,
                "Baseline Required",
                "Please define the droplet baseline before using Auto Detect Edge.",
            )
            return

        num_points, ok = QInputDialog.getInt(
            self, "Auto Detect Edge",
            "Enter number of edge points:",
            value=50, min=1, max=1000, step=1
        )
        if not ok:
            return

        baseline_coeffs = tuple(self.baseline_coeffs)
        baseline_anchor_points = (
            tuple(tuple(point) for point in self.baseline_anchor_points)
            if self.baseline_anchor_points is not None
            else None
        )
        self.btn_auto_detect.setEnabled(False)
        self.update_info_text("Detecting droplet edge...")
        self.view_model.auto_detect_edges(
            num_points,
            baseline_coeffs,
            baseline_anchor_points,
        )

    def _on_edges_detected(self, new_points):
        self.btn_auto_detect.setEnabled(True)
        if not new_points:
            QMessageBox.warning(self, "No Edges", "No edges detected.")
            return
        self._clear_measurement_selection(redraw=False)
        self.measurement_points = new_points
        self._draw_measurement_points()
        self.update_info_text(
            f"Auto detected {len(new_points)} droplet-edge points "
            "above the baseline."
        )

    def on_mouse_press(self, event):
        if event.button == 1 and self.is_config_label_mode:
            if event.inaxes:
                self._start_config_drag(event)
            return

        if event.button == 3 and self.is_measuring and event.inaxes:
            idx = self._find_measurement_point_at_event(event)
            if idx is not None and idx not in self.selected_measurement_indices:
                self._set_selected_measurement_indices([idx])
            if self._show_measurement_selection_menu(event):
                return

        if event.dblclick and event.button == 3 and self.is_baseline_mode and event.inaxes:
            x, y = event.xdata, event.ydata
            threshold = self.MEASURE_THRESHOLD
            points_list = self.baseline_points
            artists_list = self.baseline_artists

            for artist in artists_list:
                if hasattr(artist, 'contains') and callable(artist.contains):
                    contains, _ = artist.contains(event)
                    if contains and hasattr(artist, '_point_index'):
                        idx = artist._point_index
                        if 0 <= idx < len(points_list):
                            del points_list[idx]
                            self._draw_baseline_points()
                            return

            idx_to_remove = None
            for i, (px, py) in enumerate(points_list):
                dist = np.sqrt((px - x) ** 2 + (py - y) ** 2)
                if dist < threshold:
                    idx_to_remove = i
                    break

            if idx_to_remove is not None:
                del points_list[idx_to_remove]
                self._draw_baseline_points()
            return

        if event.button == 1 and self.is_measuring and event.inaxes:
            data_pos = self._event_data_position(event)
            if data_pos is None:
                return

            idx = self._find_measurement_point_at_event(event)
            if idx is not None:
                self.dragging_point_index = idx
                if idx not in self.selected_measurement_indices:
                    self._clear_measurement_selection(redraw=True)
                return

            self.pending_measure_click = data_pos
            self.pending_measure_click_canvas = (event.x, event.y)
            self.selection_start_point = data_pos
            self.selection_start_canvas = (event.x, event.y)
            self.is_selecting_measurement_points = False
            return

        if event.button == 1 and self.is_baseline_mode and event.inaxes:
            x, y = event.xdata, event.ydata
            points_list = self.baseline_points
            threshold = self.MEASURE_THRESHOLD

            for i, (px, py) in enumerate(points_list):
                dist = np.sqrt((px - x) ** 2 + (py - y) ** 2)
                if dist < threshold:
                    self.dragging_point_index = i
                    return

            points_list.append((x, y))
            self._draw_baseline_points()
            return

        if event.button == 3 and event.inaxes:
            self.is_panning = True
            self.pan_start_x = event.xdata
            self.pan_start_y = event.ydata
            self.canvas.setCursor(Qt.CursorShape.ClosedHandCursor)

    def on_mouse_release(self, event):
        if event.button == 1 and self.is_config_label_mode:
            self._reset_config_drag()
            self._update_config_hover_cursor(event)
            return

        if event.button == 1 and self.is_measuring:
            if self.dragging_point_index != -1:
                self.dragging_point_index = -1
                self._reset_pending_measure_selection()
                return

            if self.pending_measure_click is not None:
                if self.is_selecting_measurement_points:
                    end_point = self._event_data_position(event) or self.pending_measure_click
                    self._select_measurement_points_in_rect(
                        self.selection_start_point, end_point
                    )
                else:
                    self._clear_measurement_selection(redraw=False)
                    self.measurement_points.append(self.pending_measure_click)
                    self._draw_measurement_points()
                self._reset_pending_measure_selection()
                return

        if event.button == 3:
            self.is_panning = False
            self.pan_start_x = None
            self.pan_start_y = None
            self.canvas.setCursor(Qt.CursorShape.ArrowCursor)

        if event.button == 1 and self.dragging_point_index != -1:
            self.dragging_point_index = -1

    def on_mouse_move(self, event):
        if self.is_config_label_mode:
            if self._update_config_drag(event):
                return
            self._update_config_hover_cursor(event)

        if (
            self.is_measuring
            and self.pending_measure_click is not None
            and self.dragging_point_index == -1
        ):
            data_pos = self._event_data_position(event)
            if data_pos is None:
                return
            if self._canvas_drag_distance(event) >= self.SELECTION_DRAG_THRESHOLD_PX:
                self.is_selecting_measurement_points = True
                self._draw_selection_rectangle(self.selection_start_point, data_pos)
                self._remove_crosshair()
                return

        if self.dragging_point_index != -1 and event.inaxes:
            x, y = event.xdata, event.ydata
            if self.is_measuring:
                self.measurement_points[self.dragging_point_index] = (x, y)
                self._draw_measurement_points()
            elif self.is_baseline_mode:
                self.baseline_points[self.dragging_point_index] = (x, y)
                self._draw_baseline_points()

        if (self.is_measuring or self.is_baseline_mode) and event.inaxes:
            self._draw_crosshair(event.xdata, event.ydata)
        else:
            self._remove_crosshair()

        if self.is_panning and event.inaxes and self.dragging_point_index == -1:
            dx = event.xdata - self.pan_start_x
            dy = event.ydata - self.pan_start_y

            cur_xlim = self.ax.get_xlim()
            cur_ylim = self.ax.get_ylim()

            new_xlim_min = cur_xlim[0] - dx
            new_xlim_max = cur_xlim[1] - dx
            new_ylim_min = cur_ylim[0] - dy
            new_ylim_max = cur_ylim[1] - dy

            if new_xlim_min < self.x_bound[0]:
                offset = self.x_bound[0] - new_xlim_min
                new_xlim_min += offset
                new_xlim_max += offset
            elif new_xlim_max > self.x_bound[1]:
                offset = self.x_bound[1] - new_xlim_max
                new_xlim_min += offset
                new_xlim_max += offset

            if new_ylim_min < self.y_bound[0]:
                offset = self.y_bound[0] - new_ylim_min
                new_ylim_min += offset
                new_ylim_max += offset
            elif new_ylim_max > self.y_bound[1]:
                offset = self.y_bound[1] - new_ylim_max
                new_ylim_min += offset
                new_ylim_max += offset

            self.xlim = (new_xlim_min, new_xlim_max)
            self.ylim = (new_ylim_min, new_ylim_max)
            self.ax.set_xlim(self.xlim)
            self.ax.set_ylim(self.ylim)
            self.canvas.draw_idle()

    # =========================
    # zoom
    # =========================
    def _clamp_limits(self, xmin, xmax, ymin, ymax):
        xmin = max(self.x_bound[0], xmin)
        xmax = min(self.x_bound[1], xmax)
        ymin = max(self.y_bound[0], ymin)
        ymax = min(self.y_bound[1], ymax)

        min_range = 0.1
        if xmax - xmin < min_range:
            center = (xmin + xmax) / 2
            xmin = center - min_range / 2
            xmax = center + min_range / 2
            xmin = max(self.x_bound[0], xmin)
            xmax = min(self.x_bound[1], xmax)

        if ymax - ymin < min_range:
            center = (ymin + ymax) / 2
            ymin = center - min_range / 2
            ymax = center + min_range / 2
            ymin = max(self.y_bound[0], ymin)
            ymax = min(self.y_bound[1], ymax)

        return xmin, xmax, ymin, ymax

    def on_scroll(self, event):
        if event.inaxes is None:
            return

        scale_factor = 1.2 if event.button == 'up' else 1 / 1.2
        xdata, ydata = event.xdata, event.ydata
        xmin, xmax = self.xlim
        ymin, ymax = self.ylim

        new_xmin = xdata - (xdata - xmin) * scale_factor
        new_xmax = xdata + (xmax - xdata) * scale_factor
        new_ymin = ydata - (ydata - ymin) * scale_factor
        new_ymax = ydata + (ymax - ydata) * scale_factor

        new_xmin, new_xmax, new_ymin, new_ymax = self._clamp_limits(
            new_xmin, new_xmax, new_ymin, new_ymax
        )

        self.xlim = (new_xmin, new_xmax)
        self.ylim = (new_ymin, new_ymax)
        self.ax.set_xlim(self.xlim)
        self.ax.set_ylim(self.ylim)
        self.canvas.draw_idle()

    def reset_zoom(self):
        self.xlim = self.default_xlim
        self.ylim = self.default_ylim
        if self.ax is not None:
            self.ax.set_xlim(self.xlim)
            self.ax.set_ylim(self.ylim)
            self.canvas.draw_idle()

    # =========================
    # info
    # =========================
    def update_analysis_info(self, analysis_data):
        info_text = f"""
Analysis Results:

Image Dimensions:
  Width : {analysis_data.get('width', 'N/A')} pixels
  Height: {analysis_data.get('height', 'N/A')} pixels

Coordinates:
  Physical Size: 5.0 mm x 3.0 mm

Display:
  Default view : Original Image
  Overlay style: Contact-angle reference mode
"""
        self.info_text.setText(info_text)

    def update_info_text(self, text):
        self.info_text.setText(text)

    # =========================
    # button slots
    # =========================
    @pyqtSlot()
    def on_actual_size_clicked(self):
        self.reset_zoom()

    @pyqtSlot()
    def on_refresh_clicked(self):
        if self.btn_config_label.isChecked():
            self.btn_config_label.setChecked(False)
        self.btn_config_label.setEnabled(False)
        self._reset_label_layout()
        self.baseline_coeffs = None
        self.baseline_anchor_points = None
        self.last_analysis_results = None

        if self.baseline_line is not None:
            try:
                self.baseline_line.remove()
            except Exception:
                pass
            self.baseline_line = None

        self._clear_analysis_artists()

        self._clear_measurement_selection(redraw=False)
        self.measurement_points.clear()
        self._clear_measurement_artists()
        self.baseline_points.clear()
        self._clear_baseline_points_artists()

        self.is_measuring = False
        self.is_baseline_mode = False
        self.btn_measure.setChecked(False)
        self.btn_baseline.setChecked(False)

        if self.view_model.perform_analysis():
            self.update_info_text("Refreshing analysis...")
        else:
            QMessageBox.warning(self, "Refresh Failed", "Could not refresh analysis.")

    @pyqtSlot()
    def on_save_clicked(self):
        """Render on the GUI thread, then encode and write in the ViewModel."""
        initial_directory = self.view_model.get_save_dialog_directory()
        suggested_filename = (
            self.view_model.get_suggested_save_filename()
        )
        suggested_path = (
            os.path.join(initial_directory, suggested_filename)
            if initial_directory
            else suggested_filename
        )
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Analysis Result",
            suggested_path,
            "PNG Images (*.png)",
        )
        if not file_path:
            return
        if os.path.splitext(file_path)[1].casefold() != ".png":
            file_path += ".png"

        hidden_config_handles = []
        try:
            original_figure_facecolor = self.figure.get_facecolor()
            original_ax_facecolor = self.ax.get_facecolor() if self.ax is not None else None

            for handle in self.arrow_handle_artists_by_side.values():
                if handle.get_visible():
                    handle.set_visible(False)
                    hidden_config_handles.append(handle)

            self.figure.set_facecolor("white")
            if self.ax is not None:
                self.ax.set_facecolor("white")
            self.canvas.draw()
            rendered_image = self._crop_original_render_to_axes(
                self.canvas.grab().toImage()
            )
            self.figure.set_facecolor(original_figure_facecolor)
            if self.ax is not None and original_ax_facecolor is not None:
                self.ax.set_facecolor(original_ax_facecolor)
            for handle in hidden_config_handles:
                handle.set_visible(True)
            self.canvas.draw_idle()
            self.btn_save.setEnabled(False)
            self.update_info_text("Saving analysis image...")
            if not self.view_model.save_rendered_image(
                rendered_image,
                file_path,
            ):
                self.btn_save.setEnabled(True)
        except Exception as e:
            try:
                self.figure.set_facecolor("#111111")
                if self.ax is not None:
                    if self.show_original:
                        self.ax.set_facecolor("#111111")
                    else:
                        self.ax.set_facecolor("white")
                for handle in hidden_config_handles:
                    handle.set_visible(True)
                self.canvas.draw_idle()
            except Exception:
                pass

            QMessageBox.critical(self, "Save Failed", f"Could not save file:\n{str(e)}")

    def _crop_original_render_to_axes(self, rendered_image):
        """
        Remove Matplotlib figure padding from an original-image export.

        ImageEditor already supplies its own 5 x 3 mm axes. Saving the entire
        FigureCanvas bakes a second white frame into the PNG, so fitting that
        PNG later makes the actual image appear undersized. The active axes
        position is normalized to the figure and remains valid across window
        sizes and display scale factors.
        """
        if (
            rendered_image is None
            or rendered_image.isNull()
            or not self.show_original
            or self.ax is None
        ):
            return rendered_image

        position = self.ax.get_position()
        image_width = rendered_image.width()
        image_height = rendered_image.height()
        left = int(np.floor(position.x0 * image_width))
        right = int(np.ceil(position.x1 * image_width))
        top = int(np.floor((1.0 - position.y1) * image_height))
        bottom = int(np.ceil((1.0 - position.y0) * image_height))

        crop_rect = QRect(
            max(0, left),
            max(0, top),
            max(0, right - left),
            max(0, bottom - top),
        ).intersected(rendered_image.rect())
        if crop_rect.width() < 2 or crop_rect.height() < 2:
            return rendered_image

        cropped_image = rendered_image.copy(crop_rect)
        return rendered_image if cropped_image.isNull() else cropped_image

    @pyqtSlot(str)
    def _on_save_completed(self, file_path):
        self.btn_save.setEnabled(True)
        QMessageBox.information(self, "Success", f"Saved to:\n{file_path}")
        self.update_info_text(f"Analysis image saved to:\n{file_path}")

    @pyqtSlot(str, str)
    def _on_operation_failed(self, operation, message):
        if operation == "save":
            self.btn_save.setEnabled(True)
        elif operation == "edge_detection":
            self.btn_auto_detect.setEnabled(True)
        elif operation == "droplet_analysis":
            self.btn_analysis_manually.setEnabled(True)

    @pyqtSlot()
    def on_analysis_manually_clicked(self):
        if self.baseline_coeffs is None:
            QMessageBox.warning(
                self, "No Baseline",
                "Please set a baseline first using the Baseline button."
            )
            return

        if len(self.measurement_points) < 3:
            QMessageBox.warning(
                self, "Not Enough Points",
                "Please place at least three points on the droplet profile using the Measure tool or Auto Detect."
            )
            return

        analysis_method = self.analysis_method
        baseline_coeffs = tuple(self.baseline_coeffs)
        measurement_points = list(self.measurement_points)
        self.btn_analysis_manually.setEnabled(False)
        self.update_info_text(f"Running {analysis_method}...")
        self.view_model.analyze_droplet(
            analysis_method,
            baseline_coeffs,
            measurement_points,
        )

    @pyqtSlot(str, object)
    def _on_droplet_analysis_finished(self, analysis_method, results):
        self.btn_analysis_manually.setEnabled(True)
        if results is None:
            QMessageBox.critical(
                self, "Analysis Failed",
                f"Could not perform {analysis_method} with the given points."
            )
            return

        if self.btn_config_label.isChecked():
            self.btn_config_label.setChecked(False)
        self._reset_label_layout()
        self.last_analysis_results = results
        self.btn_config_label.setEnabled(True)
        self.btn_config_label.setToolTip(
            "Configure angle labels and arrow heights."
        )
        self._draw_analysis_results(results)

        self._clear_measurement_selection(redraw=False)
        self.measurement_points.clear()
        self._clear_measurement_artists()
        self.canvas.draw_idle()
        self.update_info_text("Analysis completed. Measure points cleared.")

    @pyqtSlot()
    def on_delete_measure_point_clicked(self):
        if self._delete_selected_measurement_points():
            return

        self._clear_measurement_selection(redraw=False)
        self.measurement_points.clear()
        self._clear_measurement_artists()
        self.update_info_text("All measure points deleted.")
        self.canvas.draw_idle()

    @pyqtSlot(str)
    def on_angle_mode_changed(self, text):
        self.angle_mode = text
        if self.last_analysis_results is not None:
            self._draw_analysis_results(self.last_analysis_results)

    @pyqtSlot(bool)
    def on_baseline_method_changed(self, checked):
        if checked:
            sender = self.sender()
            if sender == self.radio_double:
                self.baseline_method = "Double Points"
            elif sender == self.radio_mirror:
                self.baseline_method = "Mirror Image Method"

    @pyqtSlot(bool)
    def on_analysis_method_changed(self, checked):
        if checked:
            sender = self.sender()
            if sender == self.radio_ellipsoid:
                self.analysis_method = "Ellipsoid Fit"
            elif sender == self.radio_young_laplace:
                self.analysis_method = "Young-Laplace Fit"

    @pyqtSlot(bool)
    def on_colormap_toggled(self, checked):
        if not checked:
            return

        sender = self.sender()
        if sender == self.btn_colormap_viridis:
            self.current_colormap = 'viridis'
        elif sender == self.btn_colormap_plasma:
            self.current_colormap = 'plasma'
        elif sender == self.btn_colormap_hot:
            self.current_colormap = 'hot'
        else:
            return

        self.show_original = False
        self.update_display()

    @pyqtSlot(bool)
    def on_original_toggled(self, checked):
        if checked:
            self.show_original = True
            self.update_display()

    # =========================
    # lifecycle
    # =========================
    def closeEvent(self, event):
        if not self.view_model.request_close():
            self._close_when_idle = True
            self.update_info_text("Waiting for analysis to finish before closing...")
            event.ignore()
            return
        for connection_id in self._mpl_connection_ids:
            self.canvas.mpl_disconnect(connection_id)
        self._mpl_connection_ids.clear()
        self.figure.clear()
        if hasattr(self.view_model, "close"):
            self.view_model.close()
        try:
            self.settings.sync()
        except Exception:
            pass
        if self in DropletAnalysisWindow._instances:
            DropletAnalysisWindow._instances.remove(self)
        super().closeEvent(event)

    @pyqtSlot()
    def _on_workers_idle(self):
        if self._close_when_idle:
            self._close_when_idle = False
            QTimer.singleShot(0, self.close)

    @classmethod
    def close_all_windows(cls):
        for window in cls._instances[:]:
            window.close()

    @classmethod
    def get_instance_count(cls):
        return len(cls._instances)
