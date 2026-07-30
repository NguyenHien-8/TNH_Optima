#############################################################################
# @file App/Infrastructure/Helpers/RecycleBinHelper.py
# Author: TRAN NGUYEN HIEN
# Email: trannguyenhien29085@gmail.com
#############################################################################
import os
import sys
import time


_COPYENGINE_E_ACCESS_DENIED_SRC = 0x80270021
_RETRYABLE_WINDOWS_ERRORS = {
    5,   # ERROR_ACCESS_DENIED
    32,  # ERROR_SHARING_VIOLATION
    33,  # ERROR_LOCK_VIOLATION
    _COPYENGINE_E_ACCESS_DENIED_SRC,
}
_RECYCLE_RETRY_DELAYS = (0.1, 0.2, 0.4, 0.8, 1.0)


class RecycleBinUnavailableError(RuntimeError):
    """Raised when the native Windows Recycle Bin integration is unavailable."""


def _is_retryable_windows_error(error):
    if isinstance(error, PermissionError):
        return True

    error_codes = [
        getattr(error, "winerror", None),
        getattr(error, "errno", None),
    ]
    error_codes.extend(
        value
        for value in getattr(error, "args", ())
        if isinstance(value, int) and not isinstance(value, bool)
    )
    for error_code in error_codes:
        if not isinstance(error_code, int):
            continue
        if error_code in _RETRYABLE_WINDOWS_ERRORS:
            return True
        if error_code & 0xFFFFFFFF in _RETRYABLE_WINDOWS_ERRORS:
            return True
    return False


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

    for attempt in range(len(_RECYCLE_RETRY_DELAYS) + 1):
        try:
            send2trash(absolute_path)
        except OSError as exc:
            # IFileOperation can report an error after the Shell has already
            # completed the move. Treat the filesystem result as authoritative.
            if not os.path.lexists(absolute_path):
                return absolute_path
            if (
                attempt >= len(_RECYCLE_RETRY_DELAYS)
                or not _is_retryable_windows_error(exc)
            ):
                raise
            time.sleep(_RECYCLE_RETRY_DELAYS[attempt])
            continue

        if not os.path.lexists(absolute_path):
            return absolute_path
        raise OSError(
            f"Windows did not move the path to Recycle Bin: {absolute_path}"
        )

    raise OSError(
        f"Windows did not move the path to Recycle Bin: {absolute_path}"
    )

