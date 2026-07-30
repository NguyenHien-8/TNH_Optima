#############################################
# @file App/Presentation/Views/MainView.py
# Author: TRAN NGUYEN HIEN
# Email: trannguyenhien29085@gmail.com
#############################################
import os
import weakref
from PyQt6.QtWidgets import (QMainWindow, QVBoxLayout, QWidget,
                             QFileDialog, QInputDialog, QMessageBox, QDialog,
                             QStatusBar, QDockWidget, QTextEdit, QMenu)
from PyQt6.QtCore import Qt, QEvent, pyqtSlot, QTimer, QPoint
from PyQt6.QtGui import QCloseEvent

from App.Infrastructure.Helpers.ResourceHelper import apply_stylesheet
from App.Infrastructure.Helpers.PathHelper import (
    canonical_path,
    is_path_within,
)
from App.Infrastructure.Helpers.WindowOwnershipHelper import (
    configure_secondary_window,
    fit_window_to_available_screen,
)
from App.Infrastructure.CrashHandler import log_exception
from App.Presentation.ViewModels.MainViewModel import MainViewModel
from App.Presentation.Views.MenuBar import MenuBar
from App.Presentation.Views.Widgets.SideBar import ProjectSidebar
from App.Presentation.Views.Widgets.StatusBar import StatusBar
from App.Presentation.Views.Widgets.EditorWorkspace import EditorWorkspace
from App.Presentation.Views.Dialog.DeleteResourcesDialog import DeleteResourcesDialog
from App.Presentation.Views.Dialog.SaveResourcesDialog import SaveResourcesDialog


class FileEditorWindow(QMainWindow):
    """
    Standalone window for FileEditor.
    Uses QMainWindow so the OS window has minimize / maximize / close / resize.
    """
    def __init__(self, main_view, editor_widget, view_model):
        # Keep this native window independent from MainView. Windows otherwise
        # restores every owned window together with its owner.
        super().__init__(None, Qt.WindowType.Window)
        self.main_view = main_view
        self.editor_widget = editor_widget
        self.view_model = view_model
        self._opened = False
        self._close_pending = False
        self._screen_fit_applied = False

        self.setWindowTitle("FileEditor")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setCentralWidget(self.editor_widget)
        self._apply_window_title()

        if hasattr(self.view_model, "storage_target_changed"):
            self.view_model.storage_target_changed.connect(self._on_storage_target_changed)
        if hasattr(self.view_model, "close_ready"):
            self.view_model.close_ready.connect(self._on_close_ready)
        configure_secondary_window(self, self.main_view)

    def _apply_window_title(self):
        project_name = getattr(self.view_model, "project_name", "")
        item_name = getattr(self.view_model, "item_name", "")
        if project_name and item_name:
            self.setWindowTitle(f"FileEditor - {project_name}/{item_name}")
        elif item_name:
            self.setWindowTitle(f"FileEditor - {item_name}")
        else:
            self.setWindowTitle("FileEditor")

    @pyqtSlot(str, str, str)
    def _on_storage_target_changed(self, project_name, item_name, item_path):
        self._apply_window_title()

    def showEvent(self, event):
        super().showEvent(event)
        if not self._screen_fit_applied:
            fit_window_to_available_screen(
                self,
                preferred_size=(1100, 720),
                anchor=self.main_view,
                width_ratio=0.94,
                height_ratio=0.90,
                minimum_size=(640, 420),
            )
            self._screen_fit_applied = True
        configure_secondary_window(self, self.main_view)
        if not self._opened:
            self._opened = True
            self.main_view.view_model.on_editor_opened()
        self.main_view.view_model.set_active_frame_view_model(self.view_model)

    def closeEvent(self, event):
        try:
            if (
                hasattr(self.view_model, "request_close")
                and not self.view_model.request_close()
            ):
                self._close_pending = True
                event.ignore()
                return

            self._close_pending = False
            self.main_view.view_model.clear_active_frame_view_model(
                self.view_model
            )

            if hasattr(self.editor_widget, "close_editor"):
                self.editor_widget.close_editor()
            elif hasattr(self.view_model, "close"):
                self.view_model.close()

            if self._opened:
                self.main_view.view_model.on_editor_closed()

            self.main_view.file_editor_window = None
            event.accept()
            if self.main_view._close_after_file_editor:
                self.main_view._close_after_file_editor = False
                QTimer.singleShot(0, self.main_view.close)
        except Exception as e:
            log_exception("Could not close FileEditor safely")
            QMessageBox.warning(self, "Close Error", str(e))
            # Keep the window and its ViewModel alive. Accepting here can
            # destroy a QThread owner while a recorder or file task is still
            # running, which terminates the process in Qt.
            event.ignore()

    @pyqtSlot()
    def _on_close_ready(self):
        if self._close_pending:
            QTimer.singleShot(0, self.close)


class MainView(QMainWindow):
    def __init__(self, view_model=None):
        super().__init__()
        self._secondary_windows = weakref.WeakSet()
        self.setWindowTitle("TNH Optima")
        self.resize(1000, 700)

        self.view_model = view_model or MainViewModel()
        self._close_after_file_editor = False
        self._close_after_background_workers = False
        self._close_after_sidebar = False
        self._close_after_services = False

        self.sidebar = ProjectSidebar(self)
        self.sidebar.shutdown_ready.connect(self._on_sidebar_shutdown_ready)
        self.sidebar.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable |
                                 QDockWidget.DockWidgetFeature.DockWidgetMovable |
                                 QDockWidget.DockWidgetFeature.DockWidgetFloatable)
        self.sidebar.setVisible(True)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.sidebar)

        self.menu_bar_manager = MenuBar(self)
        self.setMenuBar(self.menu_bar_manager)

        self.system_status_bar = QStatusBar()
        self.setStatusBar(self.system_status_bar)
        self.status_bar = StatusBar()
        self.system_status_bar.addWidget(self.status_bar, 1)
        self.system_status_bar.setContentsMargins(0, 0, 0, 0)
        self.camera_info = {}

        self.tab_view_models = {}
        self.file_editor_window = None
        self._pending_text_loads = {}
        self._pending_tab_closes = set()
        self._close_after_tabs = False
        self._tab_close_cancelled = False

        self.setup_ui()
        self.editor_workspace.tab_widget.currentChanged.connect(self.on_tab_changed)
        self.editor_workspace.tab_widget.tabCloseRequested.connect(self.on_tab_close_requested)
        self._connect_view_model_signals()
        self.connect_signals()
        self.view_model.background_workers_idle.connect(
            self._on_background_workers_idle
        )
        self.view_model.shutdown_ready.connect(self._on_services_shutdown_ready)

        self.pending_restore_editors = []
        self.restoring_in_progress = False

        self.pending_rename_project = None
        self.pending_rename_item = None

        self.view_model.restore_session()

        tab_bar = self.editor_workspace.tab_widget.tabBar()
        tab_bar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        tab_bar.customContextMenuRequested.connect(self.on_tab_context_menu)

        self.sidebar.project_tree.itemSelectionChanged.connect(self._on_sidebar_selection_changed)
        QTimer.singleShot(0, self.view_model.start_deferred_initialization)

    def register_secondary_window(self, window):
        """Track a taskbar window whose minimize state follows MainView."""
        if window is not None and window is not self:
            self._secondary_windows.add(window)

    def _minimize_secondary_windows(self):
        for window in tuple(self._secondary_windows):
            try:
                if window.isVisible() and not window.isMinimized():
                    window.showMinimized()
            except RuntimeError:
                # The underlying QObject may already have been deleted.
                self._secondary_windows.discard(window)

    def changeEvent(self, event):
        super().changeEvent(event)
        if (
            event.type() == QEvent.Type.WindowStateChange
            and self.isMinimized()
            and not (event.oldState() & Qt.WindowState.WindowMinimized)
        ):
            self._minimize_secondary_windows()

    def _connect_view_model_signals(self):
        self.view_model.status_message.connect(self.system_status_bar.showMessage)
        self.view_model.error_occurred.connect(lambda msg: QMessageBox.critical(self, "Error", msg))
        self.view_model.project_added.connect(self.sidebar.add_project_item)
        self.view_model.project_removed.connect(self.sidebar.remove_project_item)
        self.view_model.project_renamed.connect(self.sidebar.rename_project_item)
        self.view_model.item_added.connect(self.sidebar.add_structure_item)
        self.view_model.item_removed.connect(self.sidebar.remove_item_node)
        self.view_model.item_renamed.connect(self.sidebar.rename_item_node)
        self.view_model.file_removed.connect(self.sidebar.remove_file_node)
        self.view_model.hidden_media_paths_changed.connect(
            self.sidebar.set_hidden_media_paths
        )
        self.view_model.media_revealed.connect(
            self.sidebar.reveal_media_file
        )
        self.view_model.file_loaded.connect(self._on_file_loaded)
        self.view_model.sidebar_loading_changed.connect(
            self.sidebar.set_loading_source
        )
        self.view_model.camera_error.connect(self.show_error)
        self.view_model.open_editor_requested.connect(self._on_open_editor_requested)
        self.view_model.file_renamed.connect(self._on_file_renamed)
        self.view_model.camera_list_updated.connect(self._on_camera_list_updated)

        self.view_model.request_unwatch_item.connect(self.sidebar.unwatch_item_media)
        self.view_model.request_unwatch_project.connect(self.sidebar.unwatch_project_media)
        self.view_model.request_watch_item.connect(self.sidebar.watch_item_media)
        self.view_model.request_watch_project.connect(self.sidebar.watch_project_media)
        self.view_model.request_close_editors_for_item.connect(self._close_editors_for_target)

        self.view_model.camera_status_changed.connect(self._update_camera_status)
        self.view_model.camera_error.connect(self._on_camera_error)
        self.view_model.hardware_status_changed.connect(self._update_hardware_status)

        self.view_model.request_stop_video_editor.connect(self._stop_video_editor)
        self.view_model.request_close_editor_for_file.connect(self._close_editor_by_path)
        self.view_model.session_restored.connect(self.sidebar.restore_expanded_paths)

    @pyqtSlot(str, str)
    def _close_editors_for_target(self, project_name, item_name):
        tab_widget = self.editor_workspace.tab_widget
        item_path = (
            self.view_model.get_item_path(project_name, item_name)
            if item_name
            else None
        )
        for i in range(tab_widget.count() - 1, -1, -1):
            widget = tab_widget.widget(i)
            p_name = widget.property("project_name")
            f_path = widget.property("full_path")

            if p_name == project_name:
                if not item_name:
                    self._close_tab_safely(i)
                elif (
                    f_path
                    and item_path
                    and is_path_within(f_path, item_path)
                ):
                    self._close_tab_safely(i)

    @pyqtSlot(str)
    def _stop_video_editor(self, full_path):
        tab_widget = self.editor_workspace.tab_widget
        for i in range(tab_widget.count()):
            widget = tab_widget.widget(i)
            if self._is_video_editor(widget) and widget.property("full_path") == full_path:
                widget.stop_playback()
                break

    @staticmethod
    def _is_video_editor(widget):
        return widget is not None and widget.property("editor_kind") == "video"

    def _track_video_editor_loading(self, editor):
        loading_token = f"video-editor:{id(editor)}"
        start_loading = lambda: self.sidebar.set_loading_source(
            loading_token,
            True,
        )
        finish_loading = lambda: self.sidebar.set_loading_source(
            loading_token,
            False,
        )
        editor.media_load_started.connect(start_loading)
        editor.media_load_finished.connect(finish_loading)
        editor.destroyed.connect(lambda *_: finish_loading())
        if editor.is_media_loading():
            start_loading()

    def _activate_video_playback(self, active_editor):
        """Keep at most one VideoEditor decoder active at a time."""
        tab_widget = self.editor_workspace.tab_widget
        for index in range(tab_widget.count()):
            editor = tab_widget.widget(index)
            if (
                editor is not active_editor
                and self._is_video_editor(editor)
            ):
                editor.pause_playback(release_resources=True)

    @pyqtSlot(str)
    def _close_editor_by_path(self, full_path):
        norm_target = os.path.normpath(full_path)

        tab_widget = self.editor_workspace.tab_widget
        for i in range(tab_widget.count()):
            widget = tab_widget.widget(i)
            widget_path = widget.property("full_path")
            if widget_path and os.path.normpath(widget_path) == norm_target:
                self._close_tab_safely(i)
                return

    @pyqtSlot(str, str)
    def _on_open_editor_requested(self, full_path, project_name):
        project_path = self.view_model.get_project_path(project_name)
        relative_path = self.view_model.get_project_relative_path(
            project_name,
            full_path,
        )
        if project_path and relative_path is not None:
            editor_context = (project_name, relative_path)
        else:
            # Media selected outside the active Project has no valid relative
            # path. Open it as a standalone file while preserving the Project
            # context for media that belongs to the active Project.
            editor_context = (None, full_path)

        self.pending_restore_editors.append(editor_context)
        if not self.restoring_in_progress:
            self.restoring_in_progress = True
            self._continue_session_restore()

    def _continue_session_restore(self):
        """Yield to the GUI event loop between restored editor tabs."""
        if self.restoring_in_progress:
            QTimer.singleShot(0, self._process_next_pending_editor)

    def _process_next_pending_editor(self):
        if not self.pending_restore_editors:
            self.restoring_in_progress = False
            return
        project_name, relative_path = self.pending_restore_editors.pop(0)
        self.action_open_file_in_editor(project_name, relative_path)

    def setup_ui(self):
        central_widget = QWidget()
        central_widget.setObjectName("CentralWidget")
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.editor_workspace = EditorWorkspace()
        self.load_mainview_style()
        main_layout.addWidget(self.editor_workspace)

    def load_mainview_style(self):
        apply_stylesheet(self, "MainViewStyles.qss")

    def connect_signals(self):
        self.editor_workspace.sig_request_open_file.connect(self.on_open_file_requested)
        self.editor_workspace.sig_request_save_file.connect(self.view_model.handle_save_file_content)

        sb = self.sidebar
        sb.sig_new_item.connect(lambda p: self._input_new_item(p))
        sb.sig_delete.connect(self._confirm_delete_project)
        sb.sig_rename.connect(self._input_rename_project)
        sb.sig_save_as.connect(self._select_folder_save_as)
        sb.sig_import_file.connect(lambda p: self._open_project_dialog())
        sb.sig_import_item.connect(lambda p: self._open_item_dialog(p))
        sb.sig_paste_to_project.connect(self.view_model.handle_paste_item)
        sb.sig_item_copy.connect(self.view_model.handle_copy_item)
        sb.sig_item_cut.connect(self.view_model.handle_cut_item)
        sb.sig_item_delete.connect(self._confirm_delete_item)
        sb.sig_item_rename.connect(self._input_rename_item)
        sb.sig_item_open_media.connect(self._open_item_media_dialog)
        sb.sig_open_editor.connect(self.action_open_file_in_editor)

        sb.sig_file_copy.connect(self.view_model.handle_copy_file)
        sb.sig_file_cut.connect(self.view_model.handle_cut_file)
        sb.sig_file_rename.connect(self._input_rename_file)
        sb.sig_file_delete.connect(self._confirm_delete_file)
        sb.sig_file_paste.connect(self.view_model.handle_paste_file)

    @pyqtSlot(str, str)
    def on_open_file_requested(self, project_name, relative_path):
        self.action_open_file_in_editor(project_name, relative_path)

    @pyqtSlot(QPoint)
    def on_tab_context_menu(self, pos):
        tab_bar = self.sender()
        index = tab_bar.tabAt(pos)
        if index == -1:
            return
        widget = self.editor_workspace.tab_widget.widget(index)
        menu = QMenu(self)
        act_calib = menu.addAction("Calibration")
        action = menu.exec(tab_bar.mapToGlobal(pos))
        if action == act_calib:
            self.create_calibration_tab_from(widget)

    def create_calibration_tab_from(self, source_widget):
        from App.Presentation.Views.Widgets.FileEditorWorkspace.ImageEditor import ImageEditor

        project_name = source_widget.property("project_name")
        if not project_name:
            project_name = "Unknown"
        file_name = source_widget.property("file_name")
        base_name = file_name if file_name else "Image"
        new_tab_name = f"Calibration-{base_name}"

        view_model = self.view_model.create_image_editor_view_model(
            project_name=project_name
        )
        editor = ImageEditor(view_model)
        editor.setProperty("project_name", project_name)
        editor.setProperty("file_name", new_tab_name)
        editor.setProperty("full_path", None)

        self.editor_workspace.add_editor_tab(editor, new_tab_name, project_name, "")

    def _input_new_item(self, project_name):
        folder_name, ok = QInputDialog.getText(self, "New Item", f"Create new item in '{project_name}':")
        if ok and folder_name:
            self.view_model.handle_new_item(project_name, folder_name)

    def _input_rename_project(self, old_name):
        self._execute_rename_project(old_name)

    def _execute_rename_project(self, old_name):
        new_name, ok = QInputDialog.getText(self, "Rename Project", "New Name:", text=old_name)
        if ok and new_name:
            self.view_model.handle_rename_project(old_name, new_name)

    def _do_rename_project(self, old_name):
        new_name, ok = QInputDialog.getText(self, "Rename Project", "New Name:", text=old_name)
        if ok and new_name:
            self.view_model.handle_rename_project(old_name, new_name)
        self.pending_rename_project = None

    def _input_rename_item(self, project_name, old_name):
        self._execute_rename_item(project_name, old_name)

    def _execute_rename_item(self, project_name, old_name):
        new_name, ok = QInputDialog.getText(self, "Rename Item", "New Name:", text=old_name)
        if ok and new_name:
            self.view_model.handle_rename_item(project_name, old_name, new_name)

    def _do_rename_item(self, project_name, old_name):
        new_name, ok = QInputDialog.getText(self, "Rename Item", "New Name:", text=old_name)
        if ok and new_name:
            self.view_model.handle_rename_item(project_name, old_name, new_name)
        self.pending_rename_item = None

    def _input_rename_file(self, project_name, item_name, media_type, old_name, _):
        base, ext = os.path.splitext(old_name)
        new_name, ok = QInputDialog.getText(self, "Rename File", "New name:", text=base)
        if ok and new_name:
            if not os.path.splitext(new_name)[1]:
                new_name = new_name + ext
            self.view_model.handle_rename_file(project_name, item_name, media_type, old_name, new_name)

    def _confirm_delete_project(self, project_name):
        is_temp = self.view_model.is_project_temp(project_name)
        full_path = self.view_model.get_project_path(project_name)
        if is_temp:
            dlg = SaveResourcesDialog(
                self,
                item_name=project_name,
            )
            if dlg.exec() == QDialog.DialogCode.Accepted:
                action = dlg.get_action()
                if action == "SAVE":
                    folder = QFileDialog.getExistingDirectory(self, "Choose a folder to save the project")
                    if folder:
                        self.view_model.handle_save_as_project(
                            project_name,
                            folder,
                            on_success=lambda name=project_name: (
                                self.view_model.handle_delete_project(
                                    name,
                                    False,
                                )
                            ),
                        )
                elif action == "DONT_SAVE":
                    self.view_model.handle_delete_project(project_name, delete_from_disk=False)
            return
        else:
            dlg = DeleteResourcesDialog(
                self, "Delete Project",
                f"Remove project '{project_name}' from the workspace?",
                full_path, show_checkbox=True
            )
            if dlg.exec() == QDialog.DialogCode.Accepted:
                self.view_model.handle_delete_project(project_name, dlg.is_delete_disk_checked())

    def _confirm_delete_item(self, project_name, folder_name):
        is_temp = self.view_model.is_project_temp(project_name)
        full_path = self.view_model.get_item_path(project_name, folder_name)
        if is_temp:
            dlg = SaveResourcesDialog(
                self,
                item_name=project_name,
            )
            if dlg.exec() == QDialog.DialogCode.Accepted:
                action = dlg.get_action()
                if action == "SAVE":
                    folder = QFileDialog.getExistingDirectory(self, "Choose a folder to save the project")
                    if folder:
                        self.view_model.handle_save_as_project(
                            project_name,
                            folder,
                            on_success=lambda name=project_name, item=folder_name: (
                                self.view_model.handle_delete_item(
                                    name,
                                    item,
                                    True,
                                )
                            ),
                        )
                elif action == "DONT_SAVE":
                    self.view_model.handle_delete_item(project_name, folder_name, delete_from_disk=False)
            return
        else:
            dlg = DeleteResourcesDialog(
                self, "Delete Item",
                f"Remove item '{folder_name}' from the project '{project_name}'?",
                full_path, show_checkbox=True
            )
            if dlg.exec() == QDialog.DialogCode.Accepted:
                self.view_model.handle_delete_item(project_name, folder_name, dlg.is_delete_disk_checked())

    def _confirm_delete_file(self, project_name, item_name, media_type, file_name):
        full_path = os.path.join(self.view_model.get_item_path(project_name, item_name), media_type, file_name)
        dlg = DeleteResourcesDialog(
            self, "Delete File",
            f"Delete file '{file_name}'?",
            full_path,
            show_checkbox=True,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.view_model.handle_delete_file(
                project_name,
                item_name,
                media_type,
                file_name,
                dlg.is_delete_disk_checked(),
            )

    def _open_project_dialog(self):
        folder = QFileDialog.getExistingDirectory(self, "Open Project Directory")
        if folder:
            self.view_model.handle_open_project(folder)

    def _open_item_dialog(self, project_name):
        folder = QFileDialog.getExistingDirectory(self, f"Open Item for '{project_name}'")
        if folder:
            self.view_model.handle_open_item(project_name, folder)

    @pyqtSlot(str, str, str)
    def _open_item_media_dialog(
        self,
        project_name,
        item_name,
        media_type,
    ):
        config = self.view_model.get_media_picker_config(
            project_name,
            item_name,
            media_type,
        )
        if config is None:
            QMessageBox.warning(
                self,
                "Error",
                f"Cannot resolve the {media_type} folder for this Item.",
            )
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            config["title"],
            config["directory"],
            config["filter"],
        )
        if file_path:
            self.view_model.handle_open_media_file(
                project_name,
                item_name,
                media_type,
                file_path,
            )

    def _select_folder_save_as(self, project_name):
        folder = QFileDialog.getExistingDirectory(self, "Select Directory to Save Project")
        if folder:
            self.view_model.handle_save_as_project(project_name, folder)

    def action_open_file_in_editor(self, project_name, relative_path):
        if project_name is None or project_name not in self.view_model.get_all_project_names():
            full_path = canonical_path(relative_path)
            project_name = None
            project_path = None
        else:
            project_path = self.view_model.get_project_path(project_name)
            if os.path.isabs(relative_path):
                full_path = canonical_path(relative_path)
            else:
                full_path = self.view_model.get_item_path(
                    project_name,
                    relative_path,
                )
            full_path = canonical_path(full_path)
            if not full_path or not is_path_within(full_path, project_path):
                # Files selected with an editor's Open button may be outside
                # the active Project. Keep them standalone instead of
                # assigning an invalid Project context.
                project_name = None
                project_path = None

        if not full_path:
            QMessageBox.warning(self, "Error", "File not found.")
            self._continue_session_restore()
            return

        if self.editor_workspace.activate_tab_by_path(full_path):
            self._continue_session_restore()
            return

        ext = os.path.splitext(full_path)[1].lower()
        image_exts = ['.png', '.jpg', '.jpeg', '.bmp', '.gif']
        video_exts = ['.mp4', '.avi', '.mov', '.mkv', '.flv']

        if ext in video_exts:
            from App.Presentation.Views.Widgets.FileEditorWorkspace.VideoEditor import VideoEditor

            video_view_model = (
                self.view_model.create_video_editor_view_model(full_path)
            )
            editor = VideoEditor(
                full_path,
                project_name=project_name,
                project_path=project_path,
                view_model=video_view_model,
            )
            self._track_video_editor_loading(editor)
            editor.playback_requested.connect(
                lambda current=editor: self._activate_video_playback(current)
            )
            editor.setProperty("editor_kind", "video")
            editor.setProperty("project_name", project_name)
            editor.setProperty("file_name", os.path.basename(full_path))
            editor.setProperty("full_path", full_path)
            editor.sig_open_video.connect(self.action_open_file_in_editor)
            editor.media_created.connect(self.sidebar.notify_media_created)
            self.editor_workspace.add_editor_tab(editor, os.path.basename(full_path), project_name, full_path)
            self._continue_session_restore()
            return

        if ext in image_exts:
            from App.Presentation.Views.Widgets.FileEditorWorkspace.ImageEditor import ImageEditor

            media_dir = os.path.dirname(full_path)
            if os.path.basename(media_dir).casefold() == "image":
                item_name = os.path.basename(os.path.dirname(media_dir))
            else:
                item_name = os.path.basename(media_dir)
            view_model = self.view_model.create_image_editor_view_model(
                project_name=project_name,
                item_name=item_name,
            )
            view_model.loading_changed.connect(
                self.sidebar.set_loading_source
            )
            editor = ImageEditor(view_model)
            editor.setProperty("project_name", project_name)
            editor.setProperty("file_name", os.path.basename(full_path))
            editor.setProperty("full_path", full_path)
            editor.sig_open_video.connect(self.action_open_file_in_editor)
            editor.set_image_source(full_path)
            self.editor_workspace.add_editor_tab(editor, os.path.basename(full_path), project_name, full_path)
            self._continue_session_restore()
            return

        self.view_model.load_file_confirmed(full_path, project_name)

    # =========================
    # FILEEDITOR TARGET ITEM LOGIC
    # =========================
    def _get_current_selected_item_context(self):
        info = self.sidebar.get_current_selection_info()
        if not info:
            return None, None, None

        project_name, item_name, item_type = info
        if item_type != 'ITEM' or not project_name or not item_name:
            return None, None, None

        item_path = self.view_model.get_item_path(project_name, item_name)
        if not item_path:
            return None, None, None

        return project_name, item_name, item_path

    def _build_file_editor_session_path(self, item_path, item_name):
        return os.path.join(item_path, f"{item_name}.session")

    @pyqtSlot()
    def _on_sidebar_selection_changed(self):
        if self.file_editor_window is None or not self.file_editor_window.isVisible():
            return

        project_name, item_name, item_path = self._get_current_selected_item_context()
        if not item_path:
            return

        self.file_editor_window.view_model.set_storage_target(project_name, item_name, item_path)

    def _create_standalone_file_editor_window(self):
        if self.file_editor_window is not None and self.file_editor_window.isVisible():
            self.file_editor_window.raise_()
            self.file_editor_window.activateWindow()
            self.view_model.set_active_frame_view_model(
                self.file_editor_window.view_model
            )
            return

        project_name, item_name, item_path = self._get_current_selected_item_context()
        if not item_path:
            QMessageBox.information(
                self,
                "Open File Editor",
                "Please select an Item in Project Sidebar first."
            )
            return

        session_path = self._build_file_editor_session_path(item_path, item_name)

        from App.Presentation.Views.Widgets.FileEditorWorkspace.FileEditor import FileEditor

        view_model = self.view_model.create_file_editor_view_model(
            project_name=project_name,
            file_name=f"{item_name}.session",
            content="",
            full_path=session_path,
        )
        view_model.media_created.connect(self.sidebar.notify_media_created)

        editor_widget = FileEditor(view_model)
        editor_widget.setProperty("full_path", session_path)
        editor_widget.setProperty("file_name", f"{item_name}.session")
        editor_widget.setProperty("project_name", project_name)

        window = FileEditorWindow(self, editor_widget, view_model)
        self.file_editor_window = window
        window.show()
        window.raise_()
        window.activateWindow()

    def open_file_editor_from_menu(self):
        self._create_standalone_file_editor_window()

    @pyqtSlot(bool, str, str, str, str)
    def _on_file_loaded(self, success, content, file_name, project_name, full_path):
        if not success:
            QMessageBox.warning(self, "Read Error", f"Cannot read file:\n{content}")
            self._continue_session_restore()
            return

        editor_widget = QTextEdit()
        editor_widget.setReadOnly(True)
        editor_widget.setObjectName("CodeEditor")
        editor_widget.setProperty("full_path", full_path)
        editor_widget.setProperty("file_name", file_name)
        editor_widget.setProperty("project_name", project_name)

        self.editor_workspace.add_editor_tab(editor_widget, file_name, project_name, full_path)
        loading_token = f"text-render:{id(editor_widget)}"
        self.sidebar.set_loading_source(loading_token, True)
        self._pending_text_loads[editor_widget] = {
            "content": content,
            "offset": 0,
            "loading_token": loading_token,
        }
        self._append_text_chunk(editor_widget)

    def _append_text_chunk(self, editor_widget):
        state = self._pending_text_loads.get(editor_widget)
        if state is None:
            return
        content = state["content"]
        start = state["offset"]
        end = min(start + 64 * 1024, len(content))
        try:
            editor_widget.insertPlainText(content[start:end])
        except RuntimeError:
            state = self._pending_text_loads.pop(editor_widget, None)
            if state is not None:
                self.sidebar.set_loading_source(
                    state["loading_token"],
                    False,
                )
            return

        if end < len(content):
            state["offset"] = end
            QTimer.singleShot(0, lambda: self._append_text_chunk(editor_widget))
            return

        editor_widget.setReadOnly(False)
        editor_widget.document().setModified(False)
        self._pending_text_loads.pop(editor_widget, None)
        self.sidebar.set_loading_source(state["loading_token"], False)
        self._continue_session_restore()

    @pyqtSlot(str, str, str, str, str)
    def _on_file_renamed(self, project_name, item_name, media_type, old_name, new_name):
        project_path = self.view_model.get_project_path(project_name)
        if not project_path:
            return

        if media_type and media_type.strip():
            old_full_path = os.path.join(project_path, item_name, media_type, old_name)
            new_full_path = os.path.join(project_path, item_name, media_type, new_name)
        else:
            old_full_path = os.path.join(project_path, item_name, old_name)
            new_full_path = os.path.join(project_path, item_name, new_name)

        tab_widget = self.editor_workspace.tab_widget
        found_widget = None
        for i in range(tab_widget.count()):
            widget = tab_widget.widget(i)
            if widget.property("full_path") == old_full_path:
                found_widget = widget
                tab_widget.setTabText(i, new_name)
                widget.setProperty("file_name", new_name)
                widget.setProperty("full_path", new_full_path)

                if widget in self.tab_view_models:
                    vm = self.tab_view_models[widget]
                    if hasattr(vm, 'full_path'):
                        vm.full_path = new_full_path
                    if hasattr(vm, 'file_name'):
                        vm.file_name = new_name
                break

        if found_widget and self._is_video_editor(found_widget):
            found_widget.reload_video(new_full_path)

    def on_tab_changed(self, index):
        if index >= 0:
            widget = self.editor_workspace.tab_widget.widget(index)
            active_vm = self.tab_view_models.get(widget)
        else:
            active_vm = None

        if active_vm is None or not callable(
            getattr(active_vm, "receive_frame", None)
        ):
            editor_window = self.file_editor_window
            active_vm = (
                editor_window.view_model
                if editor_window is not None and editor_window.isVisible()
                else None
            )
        QTimer.singleShot(
            0,
            lambda target=active_vm: self.view_model.set_active_frame_view_model(
                target
            ),
        )

    def on_tab_close_requested(self, index):
        widget = self.editor_workspace.tab_widget.widget(index)
        if widget in self.tab_view_models:
            vm = self.tab_view_models[widget]
            self.view_model.clear_active_frame_view_model(vm)
        self._close_tab_safely(index)

    def _close_tab_safely(self, index) -> bool:
        widget = self.editor_workspace.tab_widget.widget(index)
        was_loading = widget in self._pending_text_loads
        pending_load = self._pending_text_loads.pop(widget, None)
        if pending_load is not None:
            self.sidebar.set_loading_source(
                pending_load["loading_token"],
                False,
            )
        file_name = widget.property("file_name") if hasattr(widget, "property") else None

        if self._is_video_editor(widget):
            widget.stop_playback()

        if (
            isinstance(widget, QTextEdit)
            and not was_loading
            and widget.document().isModified()
        ):
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                f"File '{file_name}' has been modified.\nDo you want to save changes?",
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel
            )
            if reply == QMessageBox.StandardButton.Cancel:
                self._tab_close_cancelled = True
                return False
            if reply == QMessageBox.StandardButton.Save:
                content = widget.toPlainText()
                project_name = widget.property("project_name")
                full_path = widget.property("full_path")
                self.view_model.handle_save_file_content(content, project_name, file_name, full_path)

        tab_view_model = self.tab_view_models.get(widget)
        if not self.editor_workspace.close_tab(index):
            self._schedule_tab_close_when_ready(widget)
            return False
        if tab_view_model is not None:
            tab_view_model.close()
            self.tab_view_models.pop(widget, None)
        if was_loading and self.restoring_in_progress:
            QTimer.singleShot(0, self._process_next_pending_editor)
        return True

    def _schedule_tab_close_when_ready(self, widget):
        if widget in self._pending_tab_closes:
            return
        close_ready = getattr(widget, "close_ready", None)
        if close_ready is None:
            return
        self._pending_tab_closes.add(widget)
        close_ready.connect(
            lambda current=widget: self._retry_pending_tab_close(current)
        )

    def _retry_pending_tab_close(self, widget):
        self._pending_tab_closes.discard(widget)
        index = self.editor_workspace.tab_widget.indexOf(widget)
        if index >= 0:
            self._close_tab_safely(index)
        if self._close_after_tabs:
            self._close_after_tabs = False
            QTimer.singleShot(0, self.close)

    def _close_all_tabs_safely(self) -> bool:
        self._tab_close_cancelled = False
        for i in range(self.editor_workspace.tab_widget.count() - 1, -1, -1):
            if not self._close_tab_safely(i):
                return False
        return True

    def closeEvent(self, event: QCloseEvent):
        editor_list = []
        tab_widget = self.editor_workspace.tab_widget
        for i in range(tab_widget.count()):
            widget = tab_widget.widget(i)
            full_path = widget.property("full_path")
            project_name = widget.property("project_name")
            if full_path and project_name:
                editor_list.append({"project_name": project_name, "full_path": full_path})

        expanded_paths = self.sidebar.get_expanded_paths()
        sidebar_order = self.sidebar.get_sidebar_order()

        if self.file_editor_window is not None:
            self.file_editor_window.close()
            if self.file_editor_window is not None:
                self._close_after_file_editor = True
                self.system_status_bar.showMessage(
                    "Finishing editor operations before closing.", 5000
                )
                event.ignore()
                return

        if not self._close_all_tabs_safely():
            self._close_after_tabs = not self._tab_close_cancelled
            if self._tab_close_cancelled:
                self.system_status_bar.showMessage(
                    "Application close canceled.",
                    3000,
                )
            else:
                self.system_status_bar.showMessage(
                    "Finishing editor operations before closing.", 5000
                )
            event.ignore()
            return
        if not self.view_model.shutdown_workers():
            self._close_after_background_workers = True
            self.system_status_bar.showMessage(
                "Finishing file saves before closing.",
                5000,
            )
            event.ignore()
            return
        if not self.sidebar.shutdown():
            self._close_after_sidebar = True
            self.system_status_bar.showMessage(
                "Media folders are still being scanned. Closing automatically when ready.",
                3000,
            )
            event.ignore()
            return

        if not self.view_model.begin_application_shutdown(
            editor_list,
            expanded_paths,
            sidebar_order,
        ):
            self._close_after_services = True
            self.system_status_bar.showMessage(
                "Saving the session and releasing devices before closing.",
                5000,
            )
            event.ignore()
            return

        event.accept()

    @pyqtSlot()
    def _on_background_workers_idle(self):
        if self._close_after_background_workers:
            self._close_after_background_workers = False
            QTimer.singleShot(0, self.close)

    @pyqtSlot()
    def _on_sidebar_shutdown_ready(self):
        if self._close_after_sidebar:
            self._close_after_sidebar = False
            QTimer.singleShot(0, self.close)

    @pyqtSlot()
    def _on_services_shutdown_ready(self):
        if self._close_after_services:
            self._close_after_services = False
            QTimer.singleShot(0, self.close)

    def toggle_sidebar(self):
        self.sidebar.setVisible(not self.sidebar.isVisible())

    def new_project(self):
        self.view_model.handle_create_project()

    def open_project(self):
        self._open_project_dialog()

    def save_as_project(self):
        project_name = self.sidebar.get_current_project()
        if project_name:
            self._select_folder_save_as(project_name)
        else:
            QMessageBox.warning(self, "Warning", "No project selected.")

    def new_item(self):
        project_name = self.sidebar.get_current_project()
        if project_name:
            self._input_new_item(project_name)
        else:
            QMessageBox.warning(self, "Warning", "No project selected.")

    def open_item(self):
        project_name = self.sidebar.get_current_project()
        if project_name:
            self._open_item_dialog(project_name)
        else:
            QMessageBox.warning(self, "Warning", "No project selected.")

    def delete_selected(self):
        info = self.sidebar.get_current_selection_info()
        if not info or info[0] is None:
            QMessageBox.warning(self, "Warning", "No item selected.")
            return
        project_name, folder_name, item_type = info
        if item_type == 'PROJECT':
            self._confirm_delete_project(project_name)
        elif item_type == 'ITEM':
            self._confirm_delete_item(project_name, folder_name)

    def rename_selected(self):
        info = self.sidebar.get_current_selection_info()
        if not info or info[0] is None:
            QMessageBox.warning(self, "Warning", "No item selected.")
            return
        project_name, folder_name, item_type = info
        if item_type == 'PROJECT':
            self._input_rename_project(project_name)
        elif item_type == 'ITEM':
            self._input_rename_item(project_name, folder_name)

    def close_current_editor(self):
        self.editor_workspace.close_current_tab()

    def close_all_editors(self):
        self._close_all_tabs_safely()

    @pyqtSlot(str)
    def show_error(self, message):
        self.system_status_bar.showMessage(f"ERROR: {message}")

    @pyqtSlot(str)
    def _update_camera_status(self, message):
        import re

        # While connecting by camera index, show the cached real name immediately when available.
        if "Connecting Camera" in message:
            match = re.search(r'Camera\s+(\d+)', message)
            if match:
                idx = int(match.group(1))
                name = self.view_model.get_camera_name(idx)
                self.status_bar.set_camera_connected(True, name)
            else:
                self.status_bar.set_camera_connected(True, "Camera")
            return

        # Camera acquired while an active camera and cached name are available.
        if "Camera acquired" in message:
            camera_status = self.view_model.get_camera_status()
            active_idx = camera_status["index"]
            if active_idx is not None:
                name = camera_status["name"]
                self.status_bar.set_camera_connected(True, name)
            return

        if "disconnected" in message.lower() or "lost" in message.lower():
            self.status_bar.set_camera_connected(False)

    @pyqtSlot(str)
    def _on_camera_error(self, error_message):
        self.status_bar.set_camera_connected(False)

    @pyqtSlot(bool, str)
    def _update_hardware_status(self, connected, message):
        if connected:
            import re
            match = re.search(r'(COM\d+|/dev/tty\S+)', message, re.IGNORECASE)
            if match:
                port_name = match.group(1)
            else:
                port_name = self.view_model.get_hardware_port()
            self.status_bar.set_hardware_connected(True, port_name)
        else:
            self.status_bar.set_hardware_connected(False)

    @pyqtSlot(list)
    def _on_camera_list_updated(self, cameras):
        self.camera_info = {}
        for cam in cameras:
            if isinstance(cam, dict) and 'index' in cam:
                idx = cam['index']
                name = cam.get('name', f"Camera {idx}")
                self.camera_info[idx] = name

        # If the camera is active, refresh the StatusBar with the real name after scanning.
        camera_status = self.view_model.get_camera_status()
        if camera_status["index"] is not None and camera_status["running"]:
            self.status_bar.set_camera_connected(
                True,
                camera_status["name"],
            )
