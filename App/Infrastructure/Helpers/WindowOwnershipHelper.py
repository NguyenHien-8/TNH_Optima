###########################################################
# @file App/Infrastructure/Helpers/WindowOwnershipHelper.py
# Author: TRAN NGUYEN HIEN
# Email: trannguyenhien29085@gmail.com
###########################################################
import ctypes
import logging
import sys


APP_USER_MODEL_ID = "TNH.Optima"

_GWL_EXSTYLE = -20
_WS_EX_TOOLWINDOW = 0x00000080
_WS_EX_APPWINDOW = 0x00040000
_SWP_NOSIZE = 0x0001
_SWP_NOMOVE = 0x0002
_SWP_NOZORDER = 0x0004
_SWP_NOACTIVATE = 0x0010
_SWP_FRAMECHANGED = 0x0020

logger = logging.getLogger(__name__)


def initialize_taskbar_identity(app_user_model_id=APP_USER_MODEL_ID):
    """
    Give every native window in the process one stable Windows taskbar identity.

    The call is intentionally a no-op outside Windows and never prevents the
    application from starting if the shell API is unavailable.
    """
    if not sys.platform.startswith("win"):
        return True

    try:
        set_app_id = ctypes.WinDLL("shell32", use_last_error=True)
        set_app_id = set_app_id.SetCurrentProcessExplicitAppUserModelID
        set_app_id.argtypes = [ctypes.c_wchar_p]
        set_app_id.restype = ctypes.c_long
        result = set_app_id(app_user_model_id)
        if result != 0:
            logger.warning(
                "Could not set Windows AppUserModelID %r (HRESULT=%#x).",
                app_user_model_id,
                result & 0xFFFFFFFF,
            )
            return False
        return True
    except (AttributeError, OSError, TypeError, ValueError, ctypes.ArgumentError):
        logger.exception("Could not initialize the Windows taskbar identity.")
        return False


def resolve_window_owner(widget):
    """Return the root MainView that should coordinate a secondary window."""
    if widget is None:
        return None

    try:
        main_view = getattr(widget, "main_view", None)
        if main_view is not None and main_view is not widget:
            widget = main_view
        owner = widget.window()
    except (AttributeError, RuntimeError):
        return None

    return owner if owner is not None else widget


def configure_secondary_window(window, owner, show_in_taskbar=True):
    """
    Apply the taskbar policy and register a secondary top-level window.

    The owner is deliberately logical rather than a native transient parent.
    Native owned windows are restored automatically when Windows restores their
    owner, which prevents secondary windows from remaining minimized. MainView
    coordinates minimize explicitly instead, while WS_EX_APPWINDOW keeps every
    secondary window eligible for its own grouped taskbar thumbnail.

    The operation is idempotent and safe to repeat from showEvent.
    """
    owner = resolve_window_owner(owner)
    if window is None or owner is None or owner is window:
        return False

    try:
        # winId() creates the native handle before the first show, allowing the
        # taskbar style to be correct from the first visible frame.
        window.winId()
    except (AttributeError, RuntimeError):
        logger.exception("Could not initialize the secondary window.")
        return False

    register_window = getattr(owner, "register_secondary_window", None)
    if callable(register_window):
        register_window(window)

    if show_in_taskbar and sys.platform.startswith("win"):
        return _enable_windows_taskbar_thumbnail(window)
    return True


def fit_window_to_available_screen(
    window,
    preferred_size,
    anchor=None,
    width_ratio=0.92,
    height_ratio=0.88,
    minimum_size=(480, 320),
):
    """Size and center a top-level window inside the current screen work area."""
    if window is None:
        return None

    try:
        from PyQt6.QtCore import QSize
        from PyQt6.QtGui import QGuiApplication

        screen = None
        if anchor is not None:
            try:
                visual_anchor = anchor.window()
            except (AttributeError, RuntimeError):
                visual_anchor = anchor
            screen_getter = getattr(visual_anchor, "screen", None)
            if callable(screen_getter):
                screen = screen_getter()
        owner = resolve_window_owner(anchor)
        if screen is None and owner is not None:
            screen_getter = getattr(owner, "screen", None)
            if callable(screen_getter):
                screen = screen_getter()
        if screen is None:
            screen_getter = getattr(window, "screen", None)
            if callable(screen_getter):
                screen = screen_getter()
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if screen is None:
            return None

        available = screen.availableGeometry()
        preferred_width, preferred_height = preferred_size
        minimum_width, minimum_height = minimum_size
        maximum_width = max(1, int(available.width() * width_ratio))
        maximum_height = max(1, int(available.height() * height_ratio))
        target_width = max(
            1,
            min(int(preferred_width), maximum_width),
        )
        target_height = max(
            1,
            min(int(preferred_height), maximum_height),
        )

        window.setMinimumSize(
            min(int(minimum_width), target_width),
            min(int(minimum_height), target_height),
        )
        target_size = QSize(target_width, target_height)
        window.resize(target_size)
        window.move(
            available.x() + (available.width() - target_width) // 2,
            available.y() + (available.height() - target_height) // 2,
        )
        return target_size
    except (AttributeError, RuntimeError, TypeError, ValueError):
        logger.exception("Could not fit a window to the available screen.")
        return None


# Compatibility for callers outside this package. The policy is no longer
# native ownership; new code should use configure_secondary_window.
configure_owned_window = configure_secondary_window


def _enable_windows_taskbar_thumbnail(window):
    try:
        hwnd = int(window.winId())
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        get_window_long = getattr(user32, "GetWindowLongPtrW", None)
        set_window_long = getattr(user32, "SetWindowLongPtrW", None)
        long_ptr_type = ctypes.c_ssize_t

        if get_window_long is None or set_window_long is None:
            get_window_long = user32.GetWindowLongW
            set_window_long = user32.SetWindowLongW
            long_ptr_type = ctypes.c_long

        get_window_long.argtypes = [ctypes.c_void_p, ctypes.c_int]
        get_window_long.restype = long_ptr_type
        set_window_long.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            long_ptr_type,
        ]
        set_window_long.restype = long_ptr_type

        current_style = int(get_window_long(hwnd, _GWL_EXSTYLE))
        desired_style = (
            current_style | _WS_EX_APPWINDOW
        ) & ~_WS_EX_TOOLWINDOW

        if desired_style != current_style:
            ctypes.set_last_error(0)
            previous_style = set_window_long(
                hwnd,
                _GWL_EXSTYLE,
                desired_style,
            )
            error_code = ctypes.get_last_error()
            if previous_style == 0 and error_code:
                logger.warning(
                    "Could not update taskbar style for HWND=%#x (WinError=%d).",
                    hwnd,
                    error_code,
                )
                return False

            set_window_pos = user32.SetWindowPos
            set_window_pos.argtypes = [
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_uint,
            ]
            set_window_pos.restype = ctypes.c_bool
            flags = (
                _SWP_NOSIZE
                | _SWP_NOMOVE
                | _SWP_NOZORDER
                | _SWP_NOACTIVATE
                | _SWP_FRAMECHANGED
            )
            if not set_window_pos(hwnd, None, 0, 0, 0, 0, flags):
                logger.warning(
                    "Taskbar style changed but frame refresh failed for HWND=%#x.",
                    hwnd,
                )

        return True
    except (
        AttributeError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        ctypes.ArgumentError,
    ):
        logger.exception("Could not enable the owned-window taskbar thumbnail.")
        return False
