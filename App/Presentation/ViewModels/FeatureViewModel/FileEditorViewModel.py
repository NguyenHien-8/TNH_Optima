#############################################################################
# @file App/Presentation/ViewModels/FeatureViewModel/FileEditorViewModel.py
# Author: TRAN NGUYEN HIEN
# Email: trannguyenhien29085@gmail.com
#############################################################################
import os
from collections import deque

from PyQt6.QtCore import QObject, pyqtSignal, QTimer
from PyQt6.QtGui import QImage

from App.Models.MediaUtils.MediaManager import MediaManager
from App.Presentation.ViewModels.Workers import FunctionWorker


class FileEditorViewModel(QObject):
    frame_received = pyqtSignal(QImage)               # Camera frame
    video_state_changed = pyqtSignal(str)             # 'idle', 'recording', 'paused'
    recording_time_updated = pyqtSignal(str)          # recorded time (HH:MM:SS)
    error_occurred = pyqtSignal(str)
    motor_moving = pyqtSignal(bool)
    storage_target_changed = pyqtSignal(str, str, str)  # project_name, item_name, item_path
    media_created = pyqtSignal(str, str, str, str)  # project, item, type, full path
    close_ready = pyqtSignal()

    def __init__(self, project_name, file_name, content, full_path,
                 camera_manager, control_panel_manager):
        super().__init__()

        self.project_name = project_name
        self.file_name = file_name
        self.content = content
        self.full_path = full_path

        self.camera_manager = camera_manager
        self.control_panel_manager = control_panel_manager

        self.item_name = os.path.basename(os.path.dirname(full_path))
        item_path = os.path.dirname(full_path)
        self.media_manager = MediaManager(item_path)

        self.recording_timer = QTimer(self)
        self.recording_timer.setInterval(1000)
        self.recording_timer.timeout.connect(self._on_recording_timer_timeout)
        self.elapsed_seconds = 0
        self._workers = set()
        self._hardware_command_queue = deque()
        self._hardware_command_worker = None
        self._closing = False
        self._video_stop_pending = False
        self._video_stop_worker = None
        self._close_ready_emitted = False

    def _on_recording_timer_timeout(self):
        self.elapsed_seconds += 1
        time_str = self._format_time(self.elapsed_seconds)
        self.recording_time_updated.emit(time_str)

    def _format_time(self, total_seconds):
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def receive_frame(self, qimage: QImage):
        if qimage is None or qimage.isNull():
            return
        self.frame_received.emit(qimage)
        if self.media_manager.is_recording():
            self.media_manager.update_video_frame(qimage)

    # =========================
    # STORAGE TARGET MANAGEMENT
    # =========================
    def set_storage_target(self, project_name, item_name, item_path):
        """
        Update where captured images/videos are stored.
        Safe update rule:
        - If currently recording, do not switch target.
        - If target is unchanged, do nothing.
        """
        if not item_path:
            self.error_occurred.emit("Invalid item path for FileEditor storage.")
            return False

        current_item_path = os.path.dirname(self.full_path) if self.full_path else ""
        if os.path.normpath(current_item_path) == os.path.normpath(item_path):
            return True

        if self.media_manager.is_recording():
            self.error_occurred.emit("Cannot change save target while recording video.")
            return False

        try:
            self.media_manager.close()
        except Exception:
            pass

        self.project_name = project_name
        self.item_name = item_name
        self.file_name = f"{item_name}.session"
        self.full_path = os.path.join(item_path, self.file_name)
        self.media_manager = MediaManager(item_path)
        self.storage_target_changed.emit(project_name, item_name, item_path)
        return True

    # --- Motor Control ---
    def move_up(self, height, speed):
        self.motor_moving.emit(True)
        self._enqueue_hardware_command(
            self.control_panel_manager.request_move_up,
            self._on_motor_command_finished,
            height,
            speed,
        )

    def move_down(self, height, speed):
        self.motor_moving.emit(True)
        self._enqueue_hardware_command(
            self.control_panel_manager.request_move_down,
            self._on_motor_command_finished,
            height,
            speed,
        )

    def stop_motor(self):
        self._enqueue_hardware_command(
            self.control_panel_manager.request_stop,
            self._on_command_finished,
            priority=True,
        )

    def _on_motor_command_finished(self, result):
        self.motor_moving.emit(False)
        self._on_command_finished(result)

    def _on_command_finished(self, result):
        success, msg = result
        if not success:
            self.error_occurred.emit(msg)

    def _enqueue_hardware_command(
        self, function, callback, *args, priority=False
    ):
        command = (function, callback, args)
        if priority:
            self._hardware_command_queue.appendleft(command)
        else:
            self._hardware_command_queue.append(command)
        self._start_next_hardware_command()

    def _start_next_hardware_command(self):
        if (
            self._hardware_command_worker is not None
            or not self._hardware_command_queue
        ):
            return
        function, callback, args = self._hardware_command_queue.popleft()
        worker = FunctionWorker(function, *args)
        self._hardware_command_worker = worker
        self._workers.add(worker)
        worker.result_ready.connect(callback)
        worker.error_occurred.connect(self.error_occurred)
        worker.finished.connect(lambda: self._finish_hardware_command(worker))
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _finish_hardware_command(self, worker):
        self._workers.discard(worker)
        if self._hardware_command_worker is worker:
            self._hardware_command_worker = None
        if not self._closing:
            self._start_next_hardware_command()
        self._check_close_ready()

    # --- Image Capture ---
    def capture_image(self, qimage):
        if qimage is None or qimage.isNull():
            self.error_occurred.emit("Camera frame is invalid or corrupted")
            return
        self._run_action(
            self.media_manager.capture_image,
            self._on_media_capture_finished,
            qimage.copy(),
        )

    def _on_media_capture_finished(self, result):
        success, filename, message = result
        if success:
            self.media_created.emit(
                self.project_name,
                self.item_name,
                "Image",
                os.path.join(self.media_manager.image_folder, filename),
            )
        else:
            self.error_occurred.emit(message)

    # --- Video Recording ---
    def start_video(self):
        fps = self.camera_manager.get_fps()
        if fps <= 0:
            fps = 30.0
        success, filename, message = self.media_manager.start_video(fps=fps)
        if success:
            self.elapsed_seconds = 0
            self.recording_time_updated.emit("00:00:00")
            self.recording_timer.start()
            self.video_state_changed.emit('recording')
        else:
            self.error_occurred.emit(message)

    def pause_video(self):
        if self.media_manager.pause_video():
            self.recording_timer.stop()
            self.video_state_changed.emit('paused')
        else:
            self.error_occurred.emit("Cannot pause: not recording")

    def resume_video(self):
        if self.media_manager.resume_video():
            self.recording_timer.start()
            self.video_state_changed.emit('recording')
        else:
            self.error_occurred.emit("Cannot resume: not paused")

    def stop_video(self):
        if self.media_manager.is_recording() and not self._video_stop_pending:
            self._video_stop_pending = True
            self.recording_timer.stop()
            self._video_stop_worker = self._run_action(
                self.media_manager.stop_video,
                self._on_video_stopped,
            )
        elif not self._video_stop_pending:
            self._reset_recording_state()

    def _on_video_stopped(self, result):
        self._video_stop_pending = False
        self._video_stop_worker = None
        success, filename, message = result
        if success:
            self.media_created.emit(
                self.project_name,
                self.item_name,
                "Video",
                os.path.join(self.media_manager.video_folder, filename),
            )
        else:
            self.error_occurred.emit(message)
        self._reset_recording_state()
        self._check_close_ready()

    def _reset_recording_state(self):
        self.recording_timer.stop()
        self.elapsed_seconds = 0
        self.recording_time_updated.emit("00:00:00")
        self.video_state_changed.emit('idle')

    def _run_action(self, function, callback, *args):
        worker = FunctionWorker(function, *args)
        self._workers.add(worker)
        worker.result_ready.connect(callback)
        worker.error_occurred.connect(self.error_occurred)
        worker.finished.connect(lambda: self._finish_worker(worker))
        worker.finished.connect(worker.deleteLater)
        worker.start()
        return worker

    def _finish_worker(self, worker):
        self._workers.discard(worker)
        if worker is self._video_stop_worker:
            self._video_stop_worker = None
            self._video_stop_pending = False
            self._reset_recording_state()
        self._check_close_ready()

    def close(self):
        return self.request_close()

    def request_close(self):
        """Begin cooperative shutdown and report whether closing is safe now."""
        if self._close_ready_emitted:
            return True
        self._closing = True
        self.recording_timer.stop()
        self._hardware_command_queue.clear()
        for worker in list(self._workers):
            if worker is not self._video_stop_worker and worker.isRunning():
                worker.requestInterruption()
        if self.media_manager.is_recording() and not self._video_stop_pending:
            self.stop_video()
        self._check_close_ready()
        return self._close_ready_emitted

    def _check_close_ready(self):
        if not self._closing or self._close_ready_emitted:
            return
        has_running_workers = any(
            worker.isRunning() for worker in self._workers
        )
        if (
            has_running_workers
            or self._video_stop_pending
            or self.media_manager.is_recording()
        ):
            return
        try:
            self.media_manager.close()
        except Exception as exc:
            self.error_occurred.emit(
                f"Could not close media resources: {exc}"
            )
        self._close_ready_emitted = True
        # Emit while this QObject is still alive. Scheduling the bound
        # signal's emit method can leave a callback behind after the
        # FileEditorViewModel has been deleted, which makes PyQt raise:
        # "does not have a signal with the signature close_ready()".
        self.close_ready.emit()
