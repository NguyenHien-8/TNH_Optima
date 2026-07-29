########################################################
# @file App/Models/MediaUtils/MediaManager.py
# Author: TRAN NGUYEN HIEN
# Email: trannguyenhien29085@gmail.com
########################################################
import os
from .ImageCaptureManager import ImageCaptureManager, ImageProcessor  
from .VideoRecorderManager import VideoRecorderManager, VideoState


class MediaManager:
 
    def __init__(self, item_path):
        self.item_path = item_path

        self.image_manager = ImageCaptureManager(item_path)
        self.video_manager = VideoRecorderManager(item_path)

    # --- Image Capture Operations ---   
    def capture_image(self, qimage):
        """ Capture an image from QImage and save it to the Image folder. Return a tuple (success, filename, message)."""
        return self.image_manager.capture_image(qimage)

    # --- Video Recording Operations --- 
    def start_video(self, fps=20.0):
        """Start recording video with the given FPS."""
        return self.video_manager.start_video(fps)

    def prepare_video(self, fps=20.0):
        return self.video_manager.prepare_video(fps)

    def start_prepared_video(self, preparation):
        return self.video_manager.start_prepared_video(preparation)

    def pause_video(self):
        """Pause video recording."""
        return self.video_manager.pause_video()

    def resume_video(self):
        """Continue recording the video."""
        return self.video_manager.resume_video()

    def stop_video(self):
        return self.video_manager.stop_video()

    def get_video_state(self):
        """Get the current video state."""
        return self.video_manager.get_video_state()

    def is_recording(self):
        """Check if video is being recorded."""
        return self.video_manager.is_recording()

    def update_video_frame(self, qimage):
        """ Update the frame rate for recording into the video. """
        self.video_manager.update_video_frame(qimage)

    def close(self):
        """Clean up resources when closing."""
        self.video_manager.close()

    # --- Legacy attributes for backward compatibility ---
    @property
    def image_folder(self):
        return self.image_manager.image_folder

    @property
    def video_folder(self):
        return self.video_manager.video_folder
