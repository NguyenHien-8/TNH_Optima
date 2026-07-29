########################################################
# @file App/Models/MediaUtils/ImageCaptureManager.py
# Author: TRAN NGUYEN HIEN
# Email: trannguyenhien29085@gmail.com
########################################################
import os
from datetime import datetime

class ImageProcessor:
    """
    The utility layer handles image format conversion.
    The image conversion logic is separated from the business logic.
    """
    
    @staticmethod
    def qimage_to_bgr_numpy(qimage):
        """
        Converting QImage (RGB) to numpy array (BGR) for OpenCV.
        """
        if qimage is None or qimage.isNull():
            return None
        
        try:
            import cv2
            import numpy as np

            width = qimage.width()
            height = qimage.height()
            ptr = qimage.bits()
            ptr.setsize(height * width * 3)
            
            # QImage format RGB -> numpy RGB
            arr_rgb = np.array(ptr).reshape(height, width, 3)
            
            # RGB -> BGR for OpenCV
            frame_bgr = cv2.cvtColor(arr_rgb, cv2.COLOR_RGB2BGR)
            return frame_bgr
            
        except Exception as e:
            print(f"[ImageProcessor] Error converting QImage to BGR: {e}")
            return None


class FolderManager:
    """
    Folder management class for media files.
    Focuses on logic for checking/creating folders.
    """
    
    @staticmethod
    def ensure_folder_exists(folder_path):
        """
        Check and create the folder if it doesn't already exist.
        """
        try:
            os.makedirs(folder_path, exist_ok=True)
            return True, f"Folder ready: {folder_path}"
        except OSError as e:
            return False, f"Cannot create folder: {str(e)}"
    
    @staticmethod
    def get_media_paths(item_path):
        """
        Get the paths to the media folders from the item path.
        """
        return {
            'image_folder': os.path.join(item_path, "Image"),
            'video_folder': os.path.join(item_path, "Video")
        }

class ImageCaptureManager:
    """
    The manager oversees the photography operations.
    """
    def __init__(self, item_path):
        self.item_path = item_path
        self.image_folder = os.path.join(item_path, "Image")

    def capture_image(self, qimage):
        """
        Take screenshots from QImage and save them to the Image folder.
        """
        # Validation
        if qimage is None or qimage.isNull():
            return False, "", "Camera frame is invalid or corrupted"
        
        if not os.path.exists(self.item_path):
            return False, "", "Item path is invalid or does not exist"
        
        try:
            # Ensure folder exists (again, just in case)
            success, msg = FolderManager.ensure_folder_exists(self.image_folder)
            if not success:
                return False, "", msg
            
            # Generate filename with timestamp - using PNG for lossless quality
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            filename = f"TNH_{timestamp}.png"
            filepath = os.path.join(self.image_folder, filename)
            
            # Save image as PNG (lossless)
            if qimage.save(filepath, "PNG"):
                return True, filename, f"Image saved successfully: {filename}"
            else:
                return False, "", f"Failed to save image at {filepath}"
                
        except Exception as e:
            return False, "", f"Unexpected error during image capture: {str(e)}"
