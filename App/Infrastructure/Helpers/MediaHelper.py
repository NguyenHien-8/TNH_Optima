########################################################
# @file App/Infrastructure/Helpers/MediaHelper.py
# Author: TRAN NGUYEN HIEN
# Email: trannguyenhien29085@gmail.com
########################################################

MEDIA_EXTENSIONS = {
    "Image": (".jpg", ".jpeg", ".png", ".bmp", ".gif"),
    "Video": (".mp4", ".avi", ".mov", ".mkv", ".flv"),
}


def get_media_extensions(media_type):
    """Return the immutable extension tuple for one supported media type."""
    return tuple(MEDIA_EXTENSIONS.get(media_type, ()))
