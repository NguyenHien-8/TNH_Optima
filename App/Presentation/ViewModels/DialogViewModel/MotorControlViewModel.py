###############################################################################
# @file App/Presentation/ViewModels/DialogViewModel/MotorControlViewModel.py
# Author: TRAN NGUYEN HIEN
# Email: trannguyenhien29085@gmail.com
###############################################################################
from collections import deque

from PyQt6.QtCore import QObject, pyqtSignal

from App.Presentation.ViewModels.Workers import FunctionWorker


class MotorControlViewModel(QObject):
    motor_state_changed = pyqtSignal(bool, bool)
    command_completed = pyqtSignal(bool, str)
    workers_idle = pyqtSignal()

    def __init__(self, control_manager):
        super().__init__()
        self.control_manager = control_manager
        self._command_queue = deque()
        self._command_worker = None
        self._closing = False

    def move_up(self, height, speed):
        self._enqueue_command("up", height, speed)

    def move_down(self, height, speed):
        self._enqueue_command("down", height, speed)

    def stop(self):
        self._enqueue_command("stop", priority=True)

    def _enqueue_command(self, command, *args, priority=False):
        item = (command, args)
        if priority:
            self._command_queue.appendleft(item)
        else:
            self._command_queue.append(item)
        self._start_next_command()

    def _start_next_command(self):
        if self._command_worker is not None or not self._command_queue:
            return

        command, args = self._command_queue.popleft()
        moving_up = command == "up"

        def execute():
            if command == "up":
                return self.control_manager.request_move_up(*args)
            if command == "down":
                return self.control_manager.request_move_down(*args)
            return self.control_manager.request_stop()

        if command in {"up", "down"}:
            self.motor_state_changed.emit(True, moving_up)

        worker = FunctionWorker(execute)
        self._command_worker = worker
        worker.result_ready.connect(
            lambda result: self.command_completed.emit(*result)
        )
        worker.error_occurred.connect(
            lambda message: self.command_completed.emit(False, message)
        )
        worker.finished.connect(
            lambda: self._finish_command(worker, command, moving_up)
        )
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _finish_command(self, worker, command, moving_up):
        if self._command_worker is worker:
            self._command_worker = None
        if command in {"up", "down"}:
            self.motor_state_changed.emit(False, moving_up)
        if self._command_queue and not self._closing:
            self._start_next_command()
        elif self._command_worker is None:
            self.workers_idle.emit()

    def request_close(self):
        self._closing = True
        self._command_queue.clear()
        if self._command_worker is not None and self._command_worker.isRunning():
            self._command_worker.requestInterruption()
            return False
        return True
