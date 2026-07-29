#############################################################################
# @file App/Infrastructure/Helpers/RecycleBinHelper.py
# Author: TRAN NGUYEN HIEN
# Email: trannguyenhien29085@gmail.com
#############################################################################
import os
import sys


class RecycleBinUnavailableError(RuntimeError):
    """Raised when the native Windows Recycle Bin integration is unavailable."""


def move_to_recycle_bin(path):
    """Move one existing path to Recycle Bin without a hard-delete fallback."""
    if sys.platform != "win32":
        raise RecycleBinUnavailableError(
            "Windows Recycle Bin is unavailable on this platform."
        )
    if not isinstance(path, (str, os.PathLike)):
        raise TypeError("path must be a string or path-like object")

    absolute_path = os.path.abspath(os.fspath(path))
    if not os.path.lexists(absolute_path):
        raise FileNotFoundError(absolute_path)

    try:
        from send2trash import send2trash
    except ImportError as exc:
        raise RecycleBinUnavailableError(
            "Send2Trash is not installed; refusing to delete permanently."
        ) from exc

    send2trash(absolute_path)
    if os.path.lexists(absolute_path):
        raise OSError(
            f"Windows did not move the path to Recycle Bin: {absolute_path}"
        )
    return absolute_path

