######################################################
# @file App/Presentation/ViewModels/MainViewModel.py
# Author: TRAN NGUYEN HIEN
# Email: trannguyenhien29085@gmail.com
######################################################
import copy
import os
from typing import List
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer

from App.Models.Vision.CameraManager import CameraManager
from App.Models.Controllers.HardwareManager import HardwareManager
from App.Models.ProjectManager import ProjectManager
from App.Models.ControlPanelManager import ControlPanelManager
from App.Presentation.ViewModels.Workers import (
    FileOperationWorker,
    FileLoaderWorker,
    FileMediaWorker,
    FunctionWorker,
    SessionRestoreWorker,
    write_text_file_atomic,
)
from App.Infrastructure.Repositories.ConfigRepository import ConfigRepository
from App.Infrastructure.Repositories.SessionRepository import SessionRepository
from App.Models.SessionManager import SessionManager
from App.Models.Vision.CameraFrameDispatcher import CameraFrameDispatcher
from App.Infrastructure.CrashHandler import log_exception

class MainViewModel(QObject):
    _EDITOR_DIRECTORY_PURPOSES = (
        "image_open",
        "image_capture",
        "video_open",
        "video_capture",
        "droplet_analysis_save",
        "sidebar_image_open",
        "sidebar_video_open",
    )
    _SIDEBAR_MEDIA_DIRECTORY_PURPOSES = {
        "image": "sidebar_image_open",
        "video": "sidebar_video_open",
    }

    status_message = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    project_added = pyqtSignal(str, str)
    project_removed = pyqtSignal(str)
    project_renamed = pyqtSignal(str, str)
    item_added = pyqtSignal(str, str, str)
    item_removed = pyqtSignal(str, str)
    item_renamed = pyqtSignal(str, str, str)
    file_loaded = pyqtSignal(bool, str, str, str, str)
    camera_error = pyqtSignal(str)
    camera_list_updated = pyqtSignal(list)
    camera_status_changed = pyqtSignal(str)
    hardware_status_changed = pyqtSignal(bool, str)
    open_editor_requested = pyqtSignal(str, str)  # full_path, project_name
    file_renamed = pyqtSignal(str, str, str, str, str)  # project_name, item_name, media_type, old_name, new_name
    file_removed = pyqtSignal(str, str, str, str, bool)
    media_revealed = pyqtSignal(str, str, str, str)
    hidden_media_paths_changed = pyqtSignal(list)
    session_restored = pyqtSignal(list)
    sidebar_loading_changed = pyqtSignal(str, bool)
    background_workers_idle = pyqtSignal()
    shutdown_ready = pyqtSignal()

    # === SIGNAL FOR SPLASH SCREEN ===
    progress_update = pyqtSignal(str)
    
    # Signal to request MainView to close editors and remove watchers before file system operations
    request_close_editors_for_item = pyqtSignal(str, str)  # project_name, folder_name
    request_unwatch_item = pyqtSignal(str, str)  # project_name, folder_name
    request_unwatch_project = pyqtSignal(str)    # project_name
    request_watch_item = pyqtSignal(str, str)
    request_watch_project = pyqtSignal(str)

    # Signal to stop video player before renaming a video file
    request_stop_video_editor = pyqtSignal(str)  # full_path
    request_close_editor_for_file = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.progress_update.emit("Initializing components...")

        self.camera_manager = CameraManager()
        self.hardware_manager = HardwareManager()
        self.control_panel_manager = ControlPanelManager(self.hardware_manager)
        self.project_manager = ProjectManager()
        self.config_repo = ConfigRepository()

        self.active_workers = []
        self._deferred_task_timers = set()
        self._session_restore_started = False
        self._session_ui_operations = []
        self._session_ui_index = 0
        self._session_ui_result = None
        self._session_ui_timer = None
        self._saved_config_load_started = False
        self._deferred_hardware_config = None
        self._editor_directories = {
            purpose: None
            for purpose in self._EDITOR_DIRECTORY_PURPOSES
        }
        self._editor_directories_changed = set()
        self._editor_directories_persisted = {
            purpose: None
            for purpose in self._EDITOR_DIRECTORY_PURPOSES
        }
        self._editor_directory_save_worker = None
        self._editor_directory_save_failed = {}
        self._shutdown_started = False
        self._shutdown_complete = False
        self._shutdown_camera_done = False
        self._shutdown_io_done = False
        self._shutdown_worker = None

        self.camera_dispatcher = CameraFrameDispatcher(self.camera_manager)
        self.camera_dispatcher.dispatch_error.connect(self.camera_error)

        self.untitled_count = 1
        self.clipboard_data = None
        self.file_clipboard = None
        self.opened_items = {}
        self.hidden_media_paths = set()

        # === Initialize Session Management ===
        self.session_repo = SessionRepository()
        self.session_manager = SessionManager(self.session_repo)
        self.camera_manager.error_occurred_signal.connect(self.camera_error)
        self.camera_manager.camera_list_signal.connect(
            self.camera_list_updated
        )
        self.camera_manager.status_message_signal.connect(
            self.camera_status_changed
        )
        self.hardware_manager.connection_status_changed.connect(
            self.hardware_status_changed
        )
        self.camera_manager.shutdown_ready.connect(
            self._on_camera_shutdown_ready
        )

        self.progress_update.emit("Components initialized.")

    def _add_opened_item(self, project_name, item_name):
        if project_name not in self.opened_items:
            self.opened_items[project_name] = set()
        self.opened_items[project_name].add(item_name)

    def _remove_opened_item(self, project_name, item_name):
        if project_name in self.opened_items and item_name in self.opened_items[project_name]:
            self.opened_items[project_name].remove(item_name)
            if not self.opened_items[project_name]:
                del self.opened_items[project_name]

    def _remove_project_items(self, project_name):
        if project_name in self.opened_items:
            del self.opened_items[project_name]

    @staticmethod
    def _normalize_media_path(path):
        if not isinstance(path, str) or not path.strip():
            return None
        return os.path.normcase(os.path.abspath(os.path.normpath(path)))

    def _set_hidden_media_paths(self, paths):
        self.hidden_media_paths = {
            normalized
            for path in paths
            if (normalized := self._normalize_media_path(path)) is not None
        }
        self.hidden_media_paths_changed.emit(
            sorted(self.hidden_media_paths, key=str.casefold)
        )

    def _discard_hidden_media_under(self, root_path):
        normalized_root = self._normalize_media_path(root_path)
        if normalized_root is None:
            return
        root_prefix = normalized_root + os.sep
        retained = {
            path
            for path in self.hidden_media_paths
            if path != normalized_root and not path.startswith(root_prefix)
        }
        if retained != self.hidden_media_paths:
            self.hidden_media_paths = retained
            self.hidden_media_paths_changed.emit(
                sorted(self.hidden_media_paths, key=str.casefold)
            )

    def _remap_hidden_media_under(self, old_root_path, new_root_path):
        old_root = self._normalize_media_path(old_root_path)
        new_root = self._normalize_media_path(new_root_path)
        if old_root is None or new_root is None or old_root == new_root:
            return
        old_prefix = old_root + os.sep
        remapped = set()
        changed = False
        for path in self.hidden_media_paths:
            if path.startswith(old_prefix):
                relative_path = path[len(old_prefix):]
                remapped.add(os.path.join(new_root, relative_path))
                changed = True
            else:
                remapped.add(path)
        if changed:
            self.hidden_media_paths = remapped
            self.hidden_media_paths_changed.emit(
                sorted(self.hidden_media_paths, key=str.casefold)
            )

    def get_camera_dispatcher(self):
        return self.camera_dispatcher

    def set_active_frame_view_model(self, view_model):
        self.camera_dispatcher.set_active_view_model(view_model)

    def clear_active_frame_view_model(self, view_model=None):
        if (
            view_model is None
            or self.camera_dispatcher.is_active_view_model(view_model)
        ):
            self.camera_dispatcher.set_active_view_model(None)

    def is_active_frame_view_model(self, view_model):
        return self.camera_dispatcher.is_active_view_model(view_model)

    def is_project_folder(self, folder_path):
        return self.project_manager.is_folder_project(folder_path)

    def is_item_folder(self, folder_path):
        return self.project_manager.is_folder_item(folder_path)

    def get_camera_name(self, camera_index):
        return self.camera_manager.get_camera_name(camera_index)

    def get_camera_status(self):
        camera_index = self.camera_manager.active_camera_index
        worker = self.camera_manager.current_thread
        return {
            "index": camera_index,
            "name": (
                self.camera_manager.get_camera_name(camera_index)
                if camera_index is not None
                else ""
            ),
            "running": worker is not None and worker.isRunning(),
        }

    def get_hardware_port(self):
        return self.hardware_manager.current_config.get("port", "Unknown")

    def create_file_editor_view_model(
        self,
        project_name,
        file_name,
        content,
        full_path,
    ):
        from App.Presentation.ViewModels.FeatureViewModel.FileEditorViewModel import (
            FileEditorViewModel,
        )

        return FileEditorViewModel(
            project_name=project_name,
            file_name=file_name,
            content=content,
            full_path=full_path,
            camera_manager=self.camera_manager,
            control_panel_manager=self.control_panel_manager,
        )

    def create_image_editor_view_model(
        self,
        project_name=None,
        item_name=None,
    ):
        from App.Presentation.ViewModels.FeatureViewModel.ImageEditorViewModel import (
            ImageEditorViewModel,
        )

        return ImageEditorViewModel(
            project_name=project_name,
            item_name=item_name,
            recent_directory_provider=self.get_editor_directory,
            recent_directory_recorder=self.remember_editor_directory,
        )

    def create_video_editor_view_model(self, file_path=None):
        from App.Presentation.ViewModels.FeatureViewModel.VideoEditorViewModel import (
            VideoEditorViewModel,
        )

        return VideoEditorViewModel(
            file_path=file_path,
            recent_directory_provider=self.get_editor_directory,
            recent_directory_recorder=self.remember_editor_directory,
        )

    def create_hardware_config_view_model(self):
        from App.Presentation.ViewModels.DialogViewModel.ConfigHardwareViewModel import (
            ConfigHardwareViewModel,
        )

        return ConfigHardwareViewModel(self.hardware_manager)

    def create_camera_config_view_model(self):
        from App.Presentation.ViewModels.DialogViewModel.ConfigCameraViewModel import (
            ConfigCameraViewModel,
        )

        return ConfigCameraViewModel(self.camera_manager)

    def create_motor_control_view_model(self):
        from App.Presentation.ViewModels.DialogViewModel.MotorControlViewModel import (
            MotorControlViewModel,
        )

        return MotorControlViewModel(self.control_panel_manager)

    def restore_session(self):
        if self._session_restore_started:
            return
        self._session_restore_started = True
        self.progress_update.emit("Restoring session...")
        worker = SessionRestoreWorker(self.session_manager, self.project_manager.temp_root)
        worker.restored.connect(self._apply_restored_session)
        worker.error_occurred.connect(self.error_occurred)
        self.start_worker(worker, show_sidebar_loading=True)

    @pyqtSlot(object)
    def _apply_restored_session(self, result):
        if not isinstance(result, dict):
            result = {}
        projects = result.get("projects", [])
        saved_opened_items = result.get("opened_items", {})
        ui_operations = []
        self._set_hidden_media_paths(
            result.get("hidden_media_paths", [])
        )

        for project in projects:
            name = project.get("name")
            path = project.get("path")
            if not name or not path:
                continue

            self.project_manager.current_projects[name] = path
            self.project_manager.project_states[name] = project.get("state", "SAVED")
            ui_operations.append(("project", name, path))

            ordered_items = list(project.get("items", []))
            all_items = set(ordered_items)
            visible_items = saved_opened_items.get(name)
            if visible_items is None:
                visible_items = all_items
            else:
                visible_items = all_items.intersection(visible_items)

            for item_name in ordered_items:
                if item_name not in visible_items:
                    continue
                ui_operations.append(
                    ("item", name, item_name, os.path.join(path, item_name))
                )
                self._add_opened_item(name, item_name)

        self._session_ui_operations = ui_operations
        self._session_ui_index = 0
        self._session_ui_result = result
        if ui_operations:
            loading_token = "session-ui-restore"
            self.sidebar_loading_changed.emit(loading_token, True)
            timer = QTimer(self)
            timer.setInterval(0)
            timer.timeout.connect(self._process_session_ui_batch)
            self._session_ui_timer = timer
            self._deferred_task_timers.add(timer)
            timer.start()
            return
        self._finish_restored_session_ui(result)

    @pyqtSlot()
    def _process_session_ui_batch(self):
        if self._shutdown_started:
            return
        end = min(
            self._session_ui_index + 20,
            len(self._session_ui_operations),
        )
        for operation in self._session_ui_operations[
            self._session_ui_index:end
        ]:
            if operation[0] == "project":
                self.project_added.emit(operation[1], operation[2])
            else:
                self.item_added.emit(
                    operation[1],
                    operation[2],
                    operation[3],
                )
        self._session_ui_index = end
        if end < len(self._session_ui_operations):
            return

        timer = self._session_ui_timer
        self._session_ui_timer = None
        if timer is not None:
            timer.stop()
            self._deferred_task_timers.discard(timer)
            timer.deleteLater()
        result = self._session_ui_result or {}
        self._session_ui_operations = []
        self._session_ui_index = 0
        self._session_ui_result = None
        self.sidebar_loading_changed.emit("session-ui-restore", False)
        self._finish_restored_session_ui(result)

    def _finish_restored_session_ui(self, result):
        for editor_info in result.get("editors", []):
            if not isinstance(editor_info, dict):
                continue
            full_path = editor_info.get("full_path")
            project_name = editor_info.get("project_name")
            if (
                isinstance(full_path, str)
                and project_name in self.project_manager.current_projects
            ):
                self.open_editor_requested.emit(full_path, project_name)

        self.session_restored.emit(result.get("expanded_paths", []))
        self.progress_update.emit("Session restored.")

    def get_expanded_paths(self) -> List[str]:
        return self.session_manager.get_expanded_paths()

    def save_session_with_editors(
        self,
        editor_list,
        expanded_paths,
        sidebar_order=None,
    ):
        try:
            current_paths = list(self.project_manager.current_projects.values())
            current_by_norm = {
                os.path.normcase(os.path.normpath(path)): path
                for path in current_paths
            }
            requested_paths = (
                sidebar_order.get("projects", [])
                if isinstance(sidebar_order, dict)
                else []
            )
            project_paths = []
            seen_paths = set()
            for requested_path in requested_paths:
                if (
                    not isinstance(requested_path, str)
                    or not requested_path.strip()
                ):
                    continue
                norm_path = os.path.normcase(os.path.normpath(requested_path))
                actual_path = current_by_norm.get(norm_path)
                if actual_path is not None and norm_path not in seen_paths:
                    project_paths.append(actual_path)
                    seen_paths.add(norm_path)
            for current_path in current_paths:
                norm_path = os.path.normcase(os.path.normpath(current_path))
                if norm_path not in seen_paths:
                    project_paths.append(current_path)
                    seen_paths.add(norm_path)

            self.session_manager.set_open_projects(project_paths)
            self.session_manager.set_open_editors(editor_list)
            self.session_manager.set_expanded_paths(expanded_paths)
            self.session_manager.set_opened_items(self.opened_items)
            self.session_manager.set_sidebar_order(sidebar_order)
            self.session_manager.set_hidden_media_paths(
                sorted(self.hidden_media_paths, key=str.casefold)
            )
            self.session_manager.save_all()
            return True
        except Exception:
            log_exception("Could not save application session")
            self.error_occurred.emit(
                "The workspace session could not be saved. See the application log."
            )
            return False

    def get_project_path(self, project_name: str) -> str:
        return self.project_manager.current_projects.get(project_name, "")

    def get_project_relative_path(self, project_name: str, full_path: str):
        return self.project_manager.get_project_relative_path(
            project_name,
            full_path,
        )

    def is_project_temp(self, project_name: str) -> bool:
        return self.project_manager.is_project_temp(project_name)

    def get_item_path(self, project_name: str, item_name: str) -> str:
        # If project_name is not in current_projects, treat item_name as full_path
        if project_name not in self.project_manager.current_projects:
            return item_name
        return self.project_manager.get_file_path(project_name, item_name)

    def get_media_picker_config(
        self,
        project_name,
        item_name,
        media_type,
    ):
        extensions = self.project_manager.get_media_extensions(media_type)
        project_path = self.get_project_path(project_name)
        if not extensions or not project_path:
            return None
        patterns = " ".join(f"*{extension}" for extension in extensions)
        default_directory = os.path.join(
            project_path,
            item_name,
            media_type,
        )
        purpose = self._sidebar_media_directory_purpose(media_type)
        recent_directory = (
            self.get_editor_directory(purpose) if purpose else ""
        )
        return {
            "title": f"Open {media_type} for '{item_name}'",
            "directory": recent_directory or default_directory,
            "filter": f"{media_type} Files ({patterns})",
        }

    @classmethod
    def _sidebar_media_directory_purpose(cls, media_type):
        if not isinstance(media_type, str):
            return None
        return cls._SIDEBAR_MEDIA_DIRECTORY_PURPOSES.get(
            media_type.casefold()
        )

    def get_all_project_names(self) -> list:
        return list(self.project_manager.current_projects.keys())

    def _load_saved_configurations(self):
        try:
            cam_index = self.config_repo.load_camera_index()
        except Exception:
            log_exception("Could not load saved camera configuration")
            cam_index = None
        try:
            hw_config = self.config_repo.load_hardware_config()
        except Exception:
            log_exception("Could not load saved hardware configuration")
            hw_config = {"port": "", "baud": 115200, "period": 100}
        try:
            editor_directories = (
                self.config_repo.load_editor_directories()
            )
        except Exception:
            log_exception("Could not load recent editor directories")
            editor_directories = {}
        if not isinstance(editor_directories, dict):
            editor_directories = {}
        valid_editor_directories = {}
        for purpose, directory in editor_directories.items():
            valid_editor_directories[purpose] = (
                directory
                if isinstance(directory, str) and os.path.isdir(directory)
                else None
            )
        return cam_index, hw_config, valid_editor_directories

    @pyqtSlot(object)
    def _apply_saved_configurations(self, result):
        if self._shutdown_started:
            return
        cam_index, hw_config, editor_directories = result
        if not isinstance(editor_directories, dict):
            editor_directories = {}
        for purpose in self._EDITOR_DIRECTORY_PURPOSES:
            normalized_directory = self._normalize_editor_directory(
                editor_directories.get(purpose)
            )
            if purpose not in self._editor_directories_changed:
                self._editor_directories[purpose] = (
                    normalized_directory
                )
                self._editor_directories_persisted[purpose] = (
                    normalized_directory
                )
            else:
                # A user selection made while startup configuration was
                # loading is newer than the background result.
                self._start_editor_directory_save()
        self.camera_manager.active_camera_index = cam_index
        port = hw_config.get("port", "")
        baud = hw_config.get("baud", 115200)
        period = hw_config.get("period", 100)

        self.hardware_manager.save_config({
            "port": port,
            "baud": baud,
            "query_period": period
        })

        if port and port.strip():
            self._deferred_hardware_config = (port, baud)
        if cam_index is not None and self.camera_manager._ref_count > 0:
            self.camera_manager.ensure_connected(cam_index)
        self.progress_update.emit("Configuration loaded.")
        self._connect_deferred_hardware()

    @staticmethod
    def _normalize_editor_directory(directory):
        if not isinstance(directory, str) or not directory.strip():
            return None
        return os.path.abspath(os.path.normpath(directory))

    def get_editor_directory(self, purpose):
        if purpose not in self._EDITOR_DIRECTORY_PURPOSES:
            return ""
        return self._editor_directories[purpose] or ""

    def remember_editor_directory(self, purpose, directory):
        if purpose not in self._EDITOR_DIRECTORY_PURPOSES:
            return
        normalized_directory = self._normalize_editor_directory(
            directory
        )
        if normalized_directory is None:
            return
        self._editor_directories[purpose] = normalized_directory
        self._editor_directories_changed.add(purpose)
        self._start_editor_directory_save()

    def _start_editor_directory_save(self):
        if self._editor_directory_save_worker is not None:
            return

        pending = next(
            (
                (purpose, self._editor_directories[purpose])
                for purpose in self._EDITOR_DIRECTORY_PURPOSES
                if (
                    self._editor_directories[purpose] is not None
                    and self._editor_directories[purpose]
                    != self._editor_directories_persisted[purpose]
                    and self._editor_directories[purpose]
                    != self._editor_directory_save_failed.get(purpose)
                )
            ),
            None,
        )
        if pending is None:
            return
        purpose, directory = pending

        worker = FunctionWorker(
            self.config_repo.save_editor_directory,
            purpose,
            directory,
        )
        self._editor_directory_save_worker = worker
        worker.result_ready.connect(
            lambda _result, kind=purpose, saved=directory: (
                self._on_editor_directory_saved(kind, saved)
            )
        )
        worker.error_occurred.connect(
            lambda _message, kind=purpose, failed=directory: (
                self._on_editor_directory_save_failed(kind, failed)
            )
        )
        worker.finished.connect(
            lambda current=worker: (
                self._on_editor_directory_save_finished(current)
            )
        )
        self.start_worker(worker)

    def _on_editor_directory_saved(self, purpose, directory):
        self._editor_directories_persisted[purpose] = directory
        self._editor_directory_save_failed.pop(purpose, None)

    def _on_editor_directory_save_failed(self, purpose, directory):
        self._editor_directory_save_failed[purpose] = directory

    def _on_editor_directory_save_finished(self, worker):
        if self._editor_directory_save_worker is worker:
            self._editor_directory_save_worker = None
        self._start_editor_directory_save()

    @pyqtSlot()
    def start_deferred_initialization(self):
        """Start optional device I/O only after the main window can paint."""
        if self._saved_config_load_started or self._shutdown_started:
            return
        self._saved_config_load_started = True
        self.progress_update.emit("Loading configurations...")
        worker = FunctionWorker(self._load_saved_configurations)
        worker.result_ready.connect(self._apply_saved_configurations)
        worker.error_occurred.connect(self.error_occurred)
        self.start_worker(worker)

    def _connect_deferred_hardware(self):
        if self._deferred_hardware_config is None:
            return
        port, baud = self._deferred_hardware_config
        self._deferred_hardware_config = None
        worker = FunctionWorker(self.hardware_manager.connect_hardware, port, baud)
        worker.error_occurred.connect(self.error_occurred)
        self.start_worker(worker)

    def on_editor_opened(self):
        self.camera_manager.acquire()

    def on_editor_closed(self):
        self.camera_manager.release()

    def start_worker(self, worker, show_sidebar_loading=False):
        self.active_workers.append(worker)
        worker.finished.connect(self.cleanup_worker)
        worker.finished.connect(worker.deleteLater)
        if show_sidebar_loading:
            loading_token = f"main-worker:{id(worker)}"
            self.sidebar_loading_changed.emit(loading_token, True)
            worker.finished.connect(
                lambda token=loading_token: self.sidebar_loading_changed.emit(
                    token,
                    False,
                )
            )
        worker.start()

    def _run_background_task(
        self,
        status_message,
        function,
        callback,
        *args,
        delay_ms=0,
        show_sidebar_loading=False,
    ):
        """Run blocking model/file work and marshal its result back to the UI thread."""
        def launch():
            worker = FunctionWorker(function, *args)
            worker.result_ready.connect(callback)
            worker.error_occurred.connect(self.error_occurred)
            self.start_worker(
                worker,
                show_sidebar_loading=show_sidebar_loading,
            )

        self.status_message.emit(status_message)
        if delay_ms > 0:
            timer = QTimer(self)
            timer.setSingleShot(True)
            self._deferred_task_timers.add(timer)

            def fire():
                self._deferred_task_timers.discard(timer)
                timer.deleteLater()
                launch()

            timer.timeout.connect(fire)
            timer.start(delay_ms)
        else:
            launch()

    @pyqtSlot()
    def cleanup_worker(self):
        worker = self.sender()
        if worker in self.active_workers:
            self.active_workers.remove(worker)
        if not any(current.isRunning() for current in self.active_workers):
            self.background_workers_idle.emit()

    def shutdown_workers(self, wait_ms=0):
        for timer in list(self._deferred_task_timers):
            timer.stop()
            timer.deleteLater()
        self._deferred_task_timers.clear()

        running_workers = []
        for worker in self.active_workers[:]:
            if worker.isRunning():
                worker.requestInterruption()
                worker.quit()
            if worker.isRunning():
                running_workers.append(worker)
                continue
            try:
                worker.finished.disconnect()
            except (TypeError, RuntimeError):
                pass
            if worker in self.active_workers:
                self.active_workers.remove(worker)
            worker.deleteLater()
        return not running_workers

    def begin_application_shutdown(
        self,
        editor_list,
        expanded_paths,
        sidebar_order,
    ):
        """Persist state and release devices without blocking the GUI thread."""
        if self._shutdown_complete:
            return True
        if self._shutdown_started:
            return False

        self._shutdown_started = True
        self._shutdown_camera_done = self.camera_manager.cleanup()

        snapshot_editors = [dict(editor) for editor in editor_list]
        snapshot_expanded = list(expanded_paths)
        snapshot_order = copy.deepcopy(sidebar_order)

        def release_hardware_and_save_session():
            self.hardware_manager.cleanup()
            return self.save_session_with_editors(
                snapshot_editors,
                snapshot_expanded,
                snapshot_order,
            )

        worker = FunctionWorker(release_hardware_and_save_session)
        self._shutdown_worker = worker
        worker.result_ready.connect(self._on_shutdown_io_finished)
        worker.error_occurred.connect(self._on_shutdown_io_error)
        worker.finished.connect(self._on_shutdown_worker_finished)
        worker.finished.connect(worker.deleteLater)
        worker.start()
        self._check_shutdown_complete()
        return self._shutdown_complete

    @pyqtSlot()
    def _on_camera_shutdown_ready(self):
        self._shutdown_camera_done = True
        self._check_shutdown_complete()

    @pyqtSlot(object)
    def _on_shutdown_io_finished(self, _saved):
        self._shutdown_io_done = True
        self._check_shutdown_complete()

    @pyqtSlot(str)
    def _on_shutdown_io_error(self, message):
        self.error_occurred.emit(message)
        self._shutdown_io_done = True
        self._check_shutdown_complete()

    @pyqtSlot()
    def _on_shutdown_worker_finished(self):
        self._shutdown_worker = None
        self._check_shutdown_complete()

    def _check_shutdown_complete(self):
        if (
            self._shutdown_started
            and self._shutdown_camera_done
            and self._shutdown_io_done
            and self._shutdown_worker is None
            and not self._shutdown_complete
        ):
            self._shutdown_complete = True
            self.shutdown_ready.emit()

    def handle_create_project(self):
        name = f"Untitled-{self.untitled_count}"
        def on_created(result):
            success, message = result
            if success:
                self.project_added.emit(name, message)
                self.untitled_count += 1
                self.status_message.emit(f"Project '{name}' created.")
            else:
                self.error_occurred.emit(message)

        self._run_background_task(
            f"Creating project '{name}'...",
            self.project_manager.create_project,
            on_created,
            name,
        )

    def handle_new_item(self, project_name: str, folder_name: str):
        def on_created(result):
            success, message = result
            if success:
                self.item_added.emit(project_name, folder_name, message)
                self._add_opened_item(project_name, folder_name)
                self.status_message.emit(f"Item '{folder_name}' created.")
            else:
                self.error_occurred.emit(message)

        self._run_background_task(
            f"Creating item '{folder_name}'...",
            self.project_manager.create_structure,
            on_created,
            project_name,
            folder_name,
        )

    def handle_open_project(self, folder_path):
        def on_opened(result):
            success, project_name, items = result
            if success:
                project_path = self.project_manager.get_project_path(
                    project_name
                )
                self.project_added.emit(project_name, project_path)
                for item_name in items:
                    item_path = os.path.join(project_path, item_name)
                    self.item_added.emit(project_name, item_name, item_path)
                    self._add_opened_item(project_name, item_name)
                self.status_message.emit(f"Project '{project_name}' loaded.")
            else:
                self.error_occurred.emit(project_name)

        self._run_background_task(
            f"Opening project '{os.path.basename(folder_path)}'...",
            self.project_manager.open_project,
            on_opened,
            folder_path,
            show_sidebar_loading=True,
        )

    def handle_open_item(self, project_name: str, folder_path: str):
        folder_name = os.path.basename(folder_path)
        # Check if item is already open in sidebar
        if project_name in self.opened_items and folder_name in self.opened_items[project_name]:
            self.error_occurred.emit(f"Item '{folder_name}' already exists in sidebar.")
            return

        def on_opened(result):
            success, message, item_name, item_path = result
            if success:
                self.item_added.emit(project_name, item_name, item_path)
                self._add_opened_item(project_name, item_name)
                self.status_message.emit(f"Item '{item_name}' opened.")
            else:
                self.error_occurred.emit(message)

        self._run_background_task(
            f"Opening item '{folder_name}'...",
            self.project_manager.open_item,
            on_opened,
            project_name,
            folder_path,
        )

    def handle_delete_item(self, project_name: str, folder_name: str, delete_from_disk: bool):
        if delete_from_disk:
            self.request_unwatch_item.emit(project_name, folder_name)
            self.request_close_editors_for_item.emit(project_name, folder_name)
            item_path = self.get_item_path(project_name, folder_name)

            def on_deleted(result):
                success, message = result
                if success:
                    self._discard_hidden_media_under(item_path)
                    self._remove_opened_item(project_name, folder_name)
                    self.item_removed.emit(project_name, folder_name)
                    self.status_message.emit(
                        f"Item '{folder_name}' moved to Recycle Bin."
                    )
                else:
                    self.request_watch_item.emit(project_name, folder_name)
                    self.error_occurred.emit(message)

            self._run_background_task(
                f"Moving item '{folder_name}' to Recycle Bin...",
                self.project_manager.delete_item,
                on_deleted,
                project_name,
                folder_name,
                delay_ms=100,
            )
        else:
            # Only remove from tree, do not delete files
            self._remove_opened_item(project_name, folder_name)
            self.item_removed.emit(project_name, folder_name)

    def handle_rename_item(self, project_name: str, old_name: str, new_name: str):
        if new_name and new_name != old_name:
            self.request_unwatch_item.emit(project_name, old_name)
            self.request_close_editors_for_item.emit(project_name, old_name)
            old_item_path = self.get_item_path(project_name, old_name)
            new_item_path = os.path.join(
                self.get_project_path(project_name),
                new_name,
            )

            def on_renamed(result):
                success, message = result
                if success:
                    self._remap_hidden_media_under(
                        old_item_path,
                        new_item_path,
                    )
                    if project_name in self.opened_items and old_name in self.opened_items[project_name]:
                        self.opened_items[project_name].remove(old_name)
                        self.opened_items[project_name].add(new_name)
                    self.item_renamed.emit(project_name, old_name, new_name)
                    self.status_message.emit(f"Item renamed to '{new_name}'.")
                else:
                    self.error_occurred.emit(message)

            self._run_background_task(
                f"Renaming item '{old_name}'...",
                self.project_manager.rename_item,
                on_renamed,
                project_name,
                old_name,
                new_name,
            )

    def handle_save_as_project(
        self,
        project_name: str,
        target_folder: str,
        on_success=None,
    ):
        if not target_folder:
            return
        self.request_unwatch_project.emit(project_name)
        self.request_close_editors_for_item.emit(project_name, "")
        old_project_path = self.get_project_path(project_name)

        def save_project_and_list():
            success, result = self.project_manager.save_project_as(
                project_name, target_folder
            )
            if not success:
                return False, result, [], ""

            try:
                new_path = os.path.abspath(os.fspath(result))
            except (TypeError, ValueError):
                return (
                    False,
                    "Project save returned an invalid destination path.",
                    [],
                    "",
                )
            if not os.path.isdir(new_path):
                return (
                    False,
                    f"Project destination was not created: {new_path}",
                    [],
                    "",
                )

            items = self.project_manager.get_project_items(project_name)
            return True, new_path, items, new_path

        def on_saved(result):
            success, message, items, new_path = result
            if success:
                self._remap_hidden_media_under(
                    old_project_path,
                    new_path,
                )
                self._remove_project_items(project_name)
                self.project_removed.emit(project_name)
                self.project_added.emit(project_name, new_path)
                for item_name in items:
                    self.item_added.emit(
                        project_name, item_name, os.path.join(new_path, item_name)
                    )
                    self._add_opened_item(project_name, item_name)
                self.status_message.emit(f"Project saved to {message}")
                if callable(on_success):
                    QTimer.singleShot(0, on_success)
            else:
                self.request_watch_project.emit(project_name)
                self.error_occurred.emit(message)

        self._run_background_task(
            f"Saving project '{project_name}'...",
            save_project_and_list,
            on_saved,
        )

    def handle_save_as_item(self, project_name: str, item_name: str):
        def on_saved(result):
            success, message = result
            if success:
                self.status_message.emit(f"Item '{item_name}' marked as saved.")
            else:
                self.error_occurred.emit(message)

        self._run_background_task(
            f"Saving item '{item_name}'...",
            self.project_manager.save_item_as,
            on_saved,
            project_name,
            item_name,
        )

    def handle_delete_project(self, project_name: str, delete_from_disk: bool):
        if delete_from_disk:
            self.request_unwatch_project.emit(project_name)
            self.request_close_editors_for_item.emit(project_name, "")
            project_path = self.get_project_path(project_name)

            def on_deleted(result):
                success, message = result
                if success:
                    self._discard_hidden_media_under(project_path)
                    self._remove_project_items(project_name)
                    self.project_removed.emit(project_name)
                    self.status_message.emit(
                        f"Project '{project_name}' moved to Recycle Bin."
                    )
                else:
                    self.request_watch_project.emit(project_name)
                    self.error_occurred.emit(message)

            self._run_background_task(
                f"Moving project '{project_name}' to Recycle Bin...",
                self.project_manager.delete_project,
                on_deleted,
                project_name,
                delay_ms=100,
            )
        else:
            def on_closed(_):
                self._remove_project_items(project_name)
                self.project_removed.emit(project_name)

            self._run_background_task(
                f"Closing project '{project_name}'...",
                self.project_manager.close_project,
                on_closed,
                project_name,
            )

    def handle_rename_project(self, old_name: str, new_name: str):
        if new_name and new_name != old_name:
            self.request_unwatch_project.emit(old_name)
            self.request_close_editors_for_item.emit(old_name, "")
            old_project_path = self.get_project_path(old_name)
            new_project_path = os.path.join(
                os.path.dirname(old_project_path),
                new_name,
            )

            def on_renamed(result):
                success, message = result
                if success:
                    self._remap_hidden_media_under(
                        old_project_path,
                        new_project_path,
                    )
                    if old_name in self.opened_items:
                        self.opened_items[new_name] = self.opened_items.pop(old_name)
                    self.project_renamed.emit(old_name, new_name)
                    self.status_message.emit(f"Project renamed to '{new_name}'.")
                else:
                    self.error_occurred.emit(message)

            self._run_background_task(
                f"Renaming project '{old_name}'...",
                self.project_manager.rename_project,
                on_renamed,
                old_name,
                new_name,
            )

    def handle_copy_item(self, project_name: str, folder_name: str):
        self.clipboard_data = {'project': project_name, 'folder': folder_name, 'action': 'COPY'}
        self.status_message.emit(f"Copied '{folder_name}'.")

    def handle_cut_item(self, project_name: str, folder_name: str):
        self.clipboard_data = {'project': project_name, 'folder': folder_name, 'action': 'CUT'}
        self.status_message.emit(f"Cut '{folder_name}'.")

    def handle_paste_item(self, target_project_name: str):
        if not self.clipboard_data:
            self.error_occurred.emit("Clipboard is empty.")
            return
        src_project = self.clipboard_data['project']
        src_folder = self.clipboard_data['folder']
        action = self.clipboard_data['action']
        worker = FileOperationWorker(
            self.project_manager, src_project, src_folder, target_project_name, action
        )
        worker.sig_finished.connect(self._on_paste_finished)
        self.start_worker(worker)
        self.status_message.emit(f"Started {action} '{src_folder}' in background...")

    @pyqtSlot(bool, str, str, str, str)
    def _on_paste_finished(self, success, msg, new_name, action_type, target_project):
        if success:
            target_project_path = self.get_project_path(target_project)
            new_item_path = os.path.join(target_project_path, new_name)
            self.item_added.emit(target_project, new_name, new_item_path)
            self._add_opened_item(target_project, new_name)
            if action_type == 'CUT' and self.clipboard_data:
                src_project = self.clipboard_data['project']
                src_folder = self.clipboard_data['folder']
                src_item_path = os.path.join(
                    self.get_project_path(src_project),
                    src_folder,
                )
                self._remap_hidden_media_under(
                    src_item_path,
                    new_item_path,
                )
                self.item_removed.emit(src_project, src_folder)
                self._remove_opened_item(src_project, src_folder)
                self.clipboard_data = None
                self.status_message.emit(f"Moved '{new_name}'.")
            else:
                self.status_message.emit(f"Pasted '{new_name}'.")
        else:
            self.error_occurred.emit(msg)

    def handle_copy_file(self, project_name, item_name, media_type, file_name):
        self.file_clipboard = {
            'project': project_name,
            'item': item_name,
            'media': media_type,
            'file': file_name,
            'action': 'COPY'
        }
        self.status_message.emit(f"Copied file '{file_name}'.")

    def handle_cut_file(self, project_name, item_name, media_type, file_name):
        self.file_clipboard = {
            'project': project_name,
            'item': item_name,
            'media': media_type,
            'file': file_name,
            'action': 'CUT'
        }
        self.status_message.emit(f"Cut file '{file_name}'.")

    def handle_rename_file(self, project_name, item_name, media_type, old_name, new_name):
        # Build full old path
        project_path = self.get_project_path(project_name)
        if media_type and media_type.strip():
            old_full_path = os.path.join(project_path, item_name, media_type, old_name)
        else:
            old_full_path = os.path.join(project_path, item_name, old_name)

        # If it's a video file, stop player before renaming
        if old_name.lower().endswith(('.mp4', '.avi', '.mov', '.mkv', '.flv')):
            self.request_stop_video_editor.emit(old_full_path)

        def on_renamed(result):
            success, message = result
            if success:
                self.status_message.emit(f"File renamed to '{new_name}'.")
                self.file_renamed.emit(
                    project_name, item_name, media_type, old_name, new_name
                )
            else:
                self.error_occurred.emit(message)

        self._run_background_task(
            f"Renaming file '{old_name}'...",
            self.project_manager.rename_file,
            on_renamed,
            project_name,
            item_name,
            media_type,
            old_name,
            new_name,
            delay_ms=100,
        )

    def handle_delete_file(
        self,
        project_name,
        item_name,
        media_type,
        file_name,
        delete_from_disk,
    ):
        project_path = self.get_project_path(project_name)
        full_path = os.path.join(
            project_path,
            item_name,
            media_type,
            file_name,
        )
        normalized_path = self._normalize_media_path(full_path)

        if not delete_from_disk:
            if normalized_path is not None:
                self.hidden_media_paths.add(normalized_path)
                self.hidden_media_paths_changed.emit(
                    sorted(self.hidden_media_paths, key=str.casefold)
                )
            self.file_removed.emit(
                project_name,
                item_name,
                media_type,
                file_name,
                True,
            )
            self.status_message.emit(
                f"File '{file_name}' removed from the Sidebar."
            )
            return

        if file_name.lower().endswith(('.mp4', '.avi', '.mov', '.mkv', '.flv')):
            self.request_stop_video_editor.emit(full_path)
        self.request_close_editor_for_file.emit(full_path)

        def on_deleted(result):
            success, message = result
            if success:
                if normalized_path in self.hidden_media_paths:
                    self.hidden_media_paths.discard(normalized_path)
                    self.hidden_media_paths_changed.emit(
                        sorted(self.hidden_media_paths, key=str.casefold)
                    )
                self.file_removed.emit(
                    project_name,
                    item_name,
                    media_type,
                    file_name,
                    False,
                )
                self.status_message.emit(
                    f"File '{file_name}' moved to Recycle Bin."
                )
            else:
                self.error_occurred.emit(message)

        self._run_background_task(
            f"Moving file '{file_name}' to Recycle Bin...",
            self.project_manager.delete_file,
            on_deleted,
            project_name,
            item_name,
            media_type,
            file_name,
            True,
            delay_ms=100,
        )

    def handle_open_media_file(
        self,
        project_name,
        item_name,
        media_type,
        file_path,
    ):
        directory_purpose = self._sidebar_media_directory_purpose(
            media_type
        )
        selected_directory = (
            os.path.dirname(os.path.abspath(file_path))
            if isinstance(file_path, str) and file_path
            else None
        )

        def on_imported(result):
            success, message, file_name, imported_path, was_imported = result
            if not success:
                self.error_occurred.emit(message)
                return
            if directory_purpose and selected_directory:
                self.remember_editor_directory(
                    directory_purpose,
                    selected_directory,
                )

            normalized_path = self._normalize_media_path(imported_path)
            was_hidden = normalized_path in self.hidden_media_paths
            if was_hidden:
                self.hidden_media_paths.discard(normalized_path)
                self.hidden_media_paths_changed.emit(
                    sorted(self.hidden_media_paths, key=str.casefold)
                )

            self.media_revealed.emit(
                project_name,
                item_name,
                media_type,
                imported_path,
            )
            self.open_editor_requested.emit(
                imported_path,
                project_name,
            )
            if was_imported:
                status = (
                    f"{media_type} '{file_name}' imported into "
                    f"Item '{item_name}' and opened."
                )
            elif was_hidden:
                status = (
                    f"{media_type} '{file_name}' restored to the Sidebar."
                )
            else:
                status = f"{media_type} '{file_name}' opened."
            self.status_message.emit(status)

        self._run_background_task(
            f"Importing and opening {media_type.lower()}...",
            self.project_manager.import_media_file_for_open,
            on_imported,
            project_name,
            item_name,
            media_type,
            file_path,
            show_sidebar_loading=True,
        )

    def handle_paste_file(self, target_project, target_item, target_media):
        if not self.file_clipboard:
            self.error_occurred.emit("No file in clipboard.")
            return
        src_project = self.file_clipboard['project']
        src_item = self.file_clipboard['item']
        src_media = self.file_clipboard['media']
        src_file = self.file_clipboard['file']
        action = self.file_clipboard['action']
        if src_media != target_media:
            self.error_occurred.emit("Cannot paste to a different media folder.")
            return
        worker = FileMediaWorker(
            self.project_manager,
            src_project, src_item, src_media, src_file,
            target_project, target_item, target_media,
            action
        )
        worker.sig_finished.connect(self._on_file_paste_finished)
        self.start_worker(worker)
        self.status_message.emit(f"Pasting file '{src_file}'...")

    @pyqtSlot(bool, str, str, str, str, str, str)
    def _on_file_paste_finished(self, success, msg, new_file_name, action_type, target_project, target_item, target_media):
        if success:
            if action_type == 'CUT' and self.file_clipboard:
                self.file_clipboard = None
                self.status_message.emit(f"Moved file to '{new_file_name}'.")
            else:
                self.status_message.emit(f"Pasted file as '{new_file_name}'.")
        else:
            self.error_occurred.emit(msg)

    def load_file_confirmed(self, full_path: str, project_name: str):
        self._load_file(full_path, project_name)

    def _load_file(self, full_path: str, project_name: str):
        worker = FileLoaderWorker(full_path, project_name)
        worker.sig_loaded.connect(self.file_loaded)
        self.start_worker(worker, show_sidebar_loading=True)
        self.status_message.emit(f"Loading file...")

    def handle_save_file_content(self, content: str, project_name: str, file_name: str, full_path: str):
        if not full_path:
            full_path = self.project_manager.get_file_path(project_name, file_name)
        if not full_path:
            self.error_occurred.emit("Could not determine the file save path.")
            return

        def on_saved(_):
            self.status_message.emit(f"Saved changes to '{file_name}'.")

        self._run_background_task(
            f"Saving '{file_name}'...",
            write_text_file_atomic,
            on_saved,
            full_path,
            content,
        )
