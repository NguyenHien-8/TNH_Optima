###############################################################################
# @file App/Presentation/ViewModels/FeatureViewModel/SidebarViewModel.py
# Author: TRAN NGUYEN HIEN
# Email: trannguyenhien29085@gmail.com
###############################################################################
import os

from PyQt6.QtCore import QObject, pyqtSignal

from App.Presentation.ViewModels.Workers import FunctionWorker


class SidebarViewModel(QObject):
    """Coordinate media-folder scans without exposing workers to the View."""

    media_scan_completed = pyqtSignal(str, str, str, str, object)
    media_scan_failed = pyqtSignal(str, str)
    loading_changed = pyqtSignal(bool)
    shutdown_ready = pyqtSignal()

    def __init__(self, maximum_concurrent_scans=2, parent=None):
        super().__init__(parent)
        self._maximum_concurrent_scans = max(
            1,
            int(maximum_concurrent_scans),
        )
        self._workers = {}
        self._queue = {}
        self._pending_refreshes = {}
        self._shutting_down = False
        self._loading = False

    def request_media_scan(
        self,
        project_name,
        item_name,
        media_type,
        media_dir,
        valid_extensions,
        hidden_names=(),
    ):
        if self._shutting_down:
            return False

        request = (
            project_name,
            item_name,
            media_type,
            media_dir,
            tuple(valid_extensions),
            tuple(hidden_names),
        )
        worker = self._workers.get(media_dir)
        if worker is not None and worker.isRunning():
            self._pending_refreshes[media_dir] = request
        else:
            self._queue[media_dir] = request
        self._start_queued_scans()
        return True

    def is_scan_pending(self, media_dir):
        worker = self._workers.get(media_dir)
        return (
            media_dir in self._queue
            or media_dir in self._pending_refreshes
            or (worker is not None and worker.isRunning())
        )

    def cancel_media_scan(self, media_dir):
        self._queue.pop(media_dir, None)
        self._pending_refreshes.pop(media_dir, None)
        worker = self._workers.get(media_dir)
        if worker is not None and worker.isRunning():
            worker.requestInterruption()
        self._sync_loading()

    def _start_queued_scans(self):
        while (
            not self._shutting_down
            and self._queue
            and len(self._workers) < self._maximum_concurrent_scans
        ):
            media_dir = next(iter(self._queue))
            request = self._queue.pop(media_dir)
            worker = FunctionWorker(
                self._scan_media_directory,
                request[3],
                request[4],
                request[5],
            )
            self._workers[media_dir] = worker
            worker.result_ready.connect(
                lambda names, path=media_dir, current=request: (
                    self._on_scan_result(path, current, names)
                )
            )
            worker.error_occurred.connect(
                lambda message, path=media_dir: (
                    self._on_scan_error(path, message)
                )
            )
            worker.finished.connect(
                lambda path=media_dir, current=worker: (
                    self._finish_scan(path, current)
                )
            )
            worker.finished.connect(worker.deleteLater)
            worker.start()
        self._sync_loading()

    @staticmethod
    def _scan_media_directory(media_dir, valid_extensions, hidden_names):
        valid_extensions = set(valid_extensions)
        hidden_names = set(hidden_names)
        with os.scandir(media_dir) as entries:
            names = [
                entry.name
                for entry in entries
                if entry.is_file()
                and os.path.splitext(entry.name)[1].lower() in valid_extensions
                and os.path.normcase(entry.name) not in hidden_names
            ]
        return sorted(names, key=str.casefold)

    def _on_scan_result(self, media_dir, request, names):
        if media_dir in self._pending_refreshes or self._shutting_down:
            return
        self.media_scan_completed.emit(
            request[0],
            request[1],
            request[2],
            request[3],
            names,
        )

    def _on_scan_error(self, media_dir, message):
        if media_dir not in self._pending_refreshes and not self._shutting_down:
            self.media_scan_failed.emit(media_dir, message)

    def _finish_scan(self, media_dir, worker):
        if self._workers.get(media_dir) is worker:
            del self._workers[media_dir]
        pending = self._pending_refreshes.pop(media_dir, None)
        if pending is not None and not self._shutting_down:
            self._queue[media_dir] = pending
        self._start_queued_scans()
        self._sync_loading()
        if self._shutting_down and not self._workers:
            self.shutdown_ready.emit()

    def _sync_loading(self):
        loading = bool(self._queue or self._workers)
        if loading != self._loading:
            self._loading = loading
            self.loading_changed.emit(loading)

    def shutdown(self):
        self._shutting_down = True
        self._queue.clear()
        self._pending_refreshes.clear()
        for worker in list(self._workers.values()):
            if worker.isRunning():
                worker.requestInterruption()
        self._sync_loading()
        if not any(worker.isRunning() for worker in self._workers.values()):
            self._workers.clear()
            self.shutdown_ready.emit()
            return True
        return False
