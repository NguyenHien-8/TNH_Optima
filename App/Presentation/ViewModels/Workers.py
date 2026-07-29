######################################################
# @file App/Presentation/ViewModels/Workers.py
# Author: TRAN NGUYEN HIEN
# Email: trannguyenhien29085@gmail.com
######################################################
import os
import tempfile
from PyQt6.QtCore import QThread, pyqtSignal
from App.Infrastructure.CrashHandler import log_exception


def write_text_file_atomic(full_path, content, encoding="utf-8"):
    """Write text atomically so an interrupted save cannot truncate the target."""
    target_dir = os.path.dirname(os.path.abspath(full_path))
    os.makedirs(target_dir, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding=encoding,
            dir=target_dir,
            prefix=".tnh-optima-",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = handle.name
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, full_path)
        return full_path
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


class FunctionWorker(QThread):
    """Run one blocking callable away from the Qt GUI thread."""

    result_ready = pyqtSignal(object)
    error_occurred = pyqtSignal(str)

    def __init__(self, function, *args, **kwargs):
        super().__init__()
        if not callable(function):
            raise TypeError("function must be callable")
        self._function = function
        self._args = args
        self._kwargs = kwargs

    def run(self):
        if self.isInterruptionRequested():
            return
        try:
            result = self._function(*self._args, **self._kwargs)
        except Exception as exc:
            if self.isInterruptionRequested():
                return
            log_exception(f"Background task failed: {self._function!r}")
            self.error_occurred.emit(f"{type(exc).__name__}: {exc}")
            return
        if not self.isInterruptionRequested():
            self.result_ready.emit(result)


class SessionRestoreWorker(QThread):
    """Load and inspect the saved workspace without blocking first paint."""

    restored = pyqtSignal(object)
    error_occurred = pyqtSignal(str)

    def __init__(self, session_manager, temp_root):
        super().__init__()
        self._session_manager = session_manager
        self._temp_root = os.path.abspath(temp_root)

    def run(self):
        try:
            self._session_manager.load_all()
            projects = []
            sidebar_order = self._session_manager.get_sidebar_order()
            saved_project_paths = sidebar_order.get("projects", [])
            project_rank = {
                os.path.normcase(os.path.normpath(path)): index
                for index, path in enumerate(saved_project_paths)
                if isinstance(path, str)
            }
            saved_item_orders = sidebar_order.get("items", {})
            normalized_item_orders = {
                os.path.normcase(os.path.normpath(project_path)): item_names
                for project_path, item_names in saved_item_orders.items()
                if isinstance(project_path, str) and isinstance(item_names, list)
            }

            for raw_path in self._session_manager.get_open_projects():
                if self.isInterruptionRequested():
                    return
                if not isinstance(raw_path, str) or not os.path.isdir(raw_path):
                    continue

                path = os.path.abspath(raw_path)
                project_name = os.path.basename(os.path.normpath(path))
                try:
                    is_temp = os.path.commonpath((path, self._temp_root)) == self._temp_root
                except ValueError:
                    is_temp = False

                items = []
                try:
                    with os.scandir(path) as entries:
                        for entry in entries:
                            if self.isInterruptionRequested():
                                return
                            if not entry.is_dir():
                                continue
                            image_dir = os.path.join(entry.path, "Image")
                            video_dir = os.path.join(entry.path, "Video")
                            if os.path.isdir(image_dir) and os.path.isdir(video_dir):
                                items.append(entry.name)
                except OSError as exc:
                    self.error_occurred.emit(
                        f"Cannot scan restored project '{project_name}': {exc}"
                    )
                    continue

                saved_item_order = normalized_item_orders.get(
                    os.path.normcase(os.path.normpath(path)),
                    [],
                )
                item_rank = {
                    item_name.casefold(): index
                    for index, item_name in enumerate(saved_item_order)
                    if isinstance(item_name, str)
                }
                items.sort(
                    key=lambda item_name: (
                        item_name.casefold() not in item_rank,
                        item_rank.get(item_name.casefold(), 0),
                        item_name.casefold(),
                    )
                )

                projects.append({
                    "name": project_name,
                    "path": path,
                    "state": "TEMP" if is_temp else "SAVED",
                    "items": items,
                })

            projects.sort(
                key=lambda project: (
                    os.path.normcase(os.path.normpath(project["path"]))
                    not in project_rank,
                    project_rank.get(
                        os.path.normcase(os.path.normpath(project["path"])),
                        0,
                    ),
                )
            )

            result = {
                "projects": projects,
                "opened_items": self._session_manager.get_opened_items(),
                "editors": self._session_manager.get_open_editors(),
                "expanded_paths": self._session_manager.get_expanded_paths(),
                "sidebar_order": sidebar_order,
                "hidden_media_paths": (
                    self._session_manager.get_hidden_media_paths()
                ),
            }
            if not self.isInterruptionRequested():
                self.restored.emit(result)
        except Exception as exc:
            self.error_occurred.emit(
                f"Session restore failed: {type(exc).__name__}: {exc}"
            )


class FileOperationWorker(QThread):
    """
    Worker handling heavy file operations (Copy/Paste/Move Folder).
    Supports parallel execution via the list management in MainWindow.
    """
    # Signal: (success, message, new_item_name, action_type, target_project)
    sig_finished = pyqtSignal(bool, str, str, str, str)

    def __init__(self, project_manager, src_project, src_folder, target_project, action_type):
        super().__init__()
        self.pm = project_manager
        self.src_project = src_project
        self.src_folder = src_folder
        self.target_project = target_project
        self.action_type = action_type 

    def run(self):
        try:
            if self.action_type == 'COPY':
                success, msg, new_name = self.pm.copy_item_structure(
                    self.src_project, self.src_folder, self.target_project
                )
            elif self.action_type == 'CUT':
                success, msg, new_name = self.pm.move_item_structure(
                    self.src_project, self.src_folder, self.target_project
                )
            else:
                success, msg, new_name = False, "Unknown Action", ""

            self.sig_finished.emit(success, msg, new_name, self.action_type, self.target_project)
            
        except Exception as e:
            self.sig_finished.emit(False, str(e), "", self.action_type, self.target_project)

class FileMediaWorker(QThread):
    """
    Worker handling copy/cut of media files.
    """
    # Signal: (success, message, new_file_name, action_type, target_project, target_item, target_media)
    sig_finished = pyqtSignal(bool, str, str, str, str, str, str)

    def __init__(self, project_manager,
                 src_project, src_item, src_media, src_file,
                 dst_project, dst_item, dst_media, action_type):
        super().__init__()
        self.pm = project_manager
        self.src_project = src_project
        self.src_item = src_item
        self.src_media = src_media
        self.src_file = src_file
        self.dst_project = dst_project
        self.dst_item = dst_item
        self.dst_media = dst_media
        self.action_type = action_type  # 'COPY' or 'CUT'

    def run(self):
        try:
            if self.action_type == 'COPY':
                success, msg, new_name = self.pm.copy_file(
                    self.src_project, self.src_item, self.src_media, self.src_file,
                    self.dst_project, self.dst_item, self.dst_media
                )
            elif self.action_type == 'CUT':
                success, msg, new_name = self.pm.move_file(
                    self.src_project, self.src_item, self.src_media, self.src_file,
                    self.dst_project, self.dst_item, self.dst_media
                )
            else:
                success, msg, new_name = False, "Unknown Action", ""

            self.sig_finished.emit(success, msg, new_name, self.action_type,
                                   self.dst_project, self.dst_item, self.dst_media)
        except Exception as e:
            self.sig_finished.emit(False, str(e), "", self.action_type,
                                   self.dst_project, self.dst_item, self.dst_media)

class FileLoaderWorker(QThread):
    """
    Worker for reading large text/code file contents.
    """
    sig_loaded = pyqtSignal(bool, str, str, str, str) # success, content, file_name, project_name, full_path

    def __init__(self, full_path, project_name):
        super().__init__()
        self.full_path = full_path
        self.project_name = project_name

    def run(self):
        try:
            file_size = os.path.getsize(self.full_path)
            # Limit to 20MB for text files to avoid memory overflow when loading many files simultaneously
            if file_size > 20 * 1024 * 1024: 
                self.sig_loaded.emit(False, "File too large (>20MB)", "", "", "")
                return

            with open(self.full_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            file_name = os.path.basename(self.full_path)
            self.sig_loaded.emit(True, content, file_name, self.project_name, self.full_path)
            
        except UnicodeDecodeError:
             self.sig_loaded.emit(False, "Binary or non-UTF8 file detected.", "", "", "")
        except Exception as e:
             self.sig_loaded.emit(False, str(e), "", "", "")

class VisionWorker(QThread):
    """
    Worker for Vision algorithm processing.
    Use this class to receive raw images, process them, and return results without freezing the UI.
    """
    sig_result_ready = pyqtSignal(object)

    def __init__(self, image_data, algorithm_params):
        super().__init__()
        self.image = image_data
        self.params = algorithm_params

    def run(self):
        # --- VISION ALGORITHM HERE ---    
        result = {"status": "done", "data": []}
        self.sig_result_ready.emit(result)
