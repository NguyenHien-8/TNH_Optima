###############################################################################
# @file App/Presentation/ViewModels/DialogViewModel/ConfigHardwareViewModel.py
# Author: TRAN NGUYEN HIEN
# Email: trannguyenhien29085@gmail.com
###############################################################################
from PyQt6.QtCore import QObject, pyqtSignal

from App.Models.CamHardwareManager import HardwareConfigBackend
from App.Presentation.ViewModels.Workers import FunctionWorker


class ConfigHardwareViewModel(QObject):
    ports_scanned = pyqtSignal(list)
    connection_completed = pyqtSignal(str, object)
    error_occurred = pyqtSignal(str)
    workers_idle = pyqtSignal()

    def __init__(self, hardware_manager):
        super().__init__()
        self.backend = HardwareConfigBackend(hardware_manager)
        self._workers = set()

    def get_current_config(self):
        return self.backend.get_current_config()

    def scan_ports(self):
        self._start_worker(self.backend.scan_ports, self.ports_scanned.emit)

    def apply_connection(self, port, baud, period):
        self._start_worker(
            self.backend.apply_connection,
            lambda result: self.connection_completed.emit(port, result),
            port,
            baud,
            period,
        )

    def _start_worker(self, function, callback, *args):
        worker = FunctionWorker(function, *args)
        self._workers.add(worker)
        worker.result_ready.connect(callback)
        worker.error_occurred.connect(self.error_occurred)
        worker.finished.connect(lambda: self._finish_worker(worker))
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _finish_worker(self, worker):
        self._workers.discard(worker)
        if not self._workers:
            self.workers_idle.emit()

    def is_busy(self):
        return any(worker.isRunning() for worker in self._workers)

    def request_close(self):
        running_workers = [worker for worker in self._workers if worker.isRunning()]
        for worker in running_workers:
            worker.requestInterruption()
        return not running_workers
