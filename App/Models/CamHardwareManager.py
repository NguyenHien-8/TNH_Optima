########################################################
# @file App/Models/CamHardwareManager.py
# Author: TRAN NGUYEN HIEN
# Email: trannguyenhien29085@gmail.com
########################################################
from App.Infrastructure.Repositories.ConfigRepository import ConfigRepository

class CameraConfigBackend:
    def __init__(self, camera_manager):
        self.camera_manager = camera_manager      
        self.original_camera_id = self.camera_manager.active_camera_index
        self.selected_camera_id = self.original_camera_id       
        self.first_load = True
        self.config_repo = ConfigRepository()

    def scan_cameras(self):
        self.camera_manager.scan_cameras()

    def set_selected_camera(self, index):
        self.selected_camera_id = index

    def get_selected_camera(self):
        return self.selected_camera_id

    def connect_preview(self, cam_idx):
        self.camera_manager.set_preview_mode(True)
        if (self.camera_manager.active_camera_index != cam_idx) or \
           (self.camera_manager.current_thread is None or not self.camera_manager.current_thread.isRunning()):
            self.camera_manager.change_camera(cam_idx)

    def stop_preview(self):
        self.camera_manager.set_preview_mode(False)
        self.camera_manager.stop_current_camera()

    def save_selected_camera(self, selected_camera_id):
        self.config_repo.save_camera_index(selected_camera_id)
        return selected_camera_id

    def apply_runtime_changes(self, connect_now=False):
        self.camera_manager.set_preview_mode(False) 
        self.camera_manager.active_camera_index = self.selected_camera_id

        if self.selected_camera_id is not None and (connect_now or self.camera_manager._ref_count > 0):
            self.camera_manager.change_camera(self.selected_camera_id)
        else:
            self.camera_manager.stop_current_camera()

    def apply_changes(self, connect_now=False):
        """Compatibility API for non-UI callers."""
        self.save_selected_camera(self.selected_camera_id)
        self.apply_runtime_changes(connect_now)

    def revert_changes(self):
        self.camera_manager.set_preview_mode(False)
        self.camera_manager.active_camera_index = self.original_camera_id
        
        if self.original_camera_id is not None and self.camera_manager._ref_count > 0:
             self.camera_manager.change_camera(self.original_camera_id)
        else:
             self.camera_manager.stop_current_camera()

class HardwareConfigBackend: 
    def __init__(self, hardware_manager):
        self.hardware_manager = hardware_manager
        self.config_repo = ConfigRepository()

    def get_current_config(self):
        return self.hardware_manager.get_config()

    def scan_ports(self):
        return self.hardware_manager.scan_ports()

    def apply_connection(self, port_name, baud_rate, query_period):
        try:
            period_int = int(query_period) if query_period else 100
            if period_int <= 0:
                raise ValueError
        except (TypeError, ValueError):
            period_int = 100

        new_config = {
            "port": str(port_name).strip(),
            "baud": int(baud_rate),
            "query_period": period_int
        }
        self.hardware_manager.save_config(new_config)
        self.config_repo.save_hardware_config(port_name, baud_rate, period_int)
        
        if port_name:
            return self.hardware_manager.connect_hardware(port_name, baud_rate)
        else:
            return self.hardware_manager.disconnect_hardware()
