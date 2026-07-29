########################################################
# @file App/Infrastructure/Helpers/PathHelper.py
# Author: TRAN NGUYEN HIEN
# Email: trannguyenhien29085@gmail.com
########################################################
import ctypes
import os
import sys
import uuid
from pathlib import Path
from typing import Optional


class _GUID(ctypes.Structure):
    _fields_ = (
        ("Data1", ctypes.c_uint32),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    )

    @classmethod
    def from_string(cls, value):
        guid_bytes = uuid.UUID(value).bytes_le
        return cls.from_buffer_copy(guid_bytes)


_FOLDERID_DOCUMENTS = _GUID.from_string(
    "FDD39AD0-238F-46AF-ADB4-6C85480369C7"
)


def _get_windows_documents_path() -> Path:
    """Resolve the current user's Documents known folder through Windows."""
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    ole32 = ctypes.WinDLL("ole32", use_last_error=True)
    path_pointer = ctypes.c_wchar_p()

    get_known_folder_path = shell32.SHGetKnownFolderPath
    get_known_folder_path.argtypes = (
        ctypes.POINTER(_GUID),
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_wchar_p),
    )
    get_known_folder_path.restype = ctypes.c_long

    co_task_mem_free = ole32.CoTaskMemFree
    co_task_mem_free.argtypes = (ctypes.c_void_p,)
    co_task_mem_free.restype = None

    result = get_known_folder_path(
        ctypes.byref(_FOLDERID_DOCUMENTS),
        0,
        None,
        ctypes.byref(path_pointer),
    )
    if result != 0:
        raise OSError(
            f"SHGetKnownFolderPath(FOLDERID_Documents) failed: 0x{result & 0xFFFFFFFF:08X}"
        )

    try:
        if not path_pointer.value:
            raise OSError("Windows returned an empty Documents path.")
        return Path(path_pointer.value)
    finally:
        co_task_mem_free(ctypes.cast(path_pointer, ctypes.c_void_p))


def user_documents_path() -> Path:
    """
    Return the current user's Documents directory.

    Windows Known Folder resolution is authoritative because Documents can be
    redirected by Windows, a domain policy, or OneDrive. USERPROFILE is kept as
    a deterministic fallback for older or restricted Windows environments.
    """
    if sys.platform.startswith("win"):
        try:
            return _get_windows_documents_path()
        except (
            AttributeError,
            OSError,
            TypeError,
            ValueError,
            ctypes.ArgumentError,
        ):
            user_profile = os.environ.get("USERPROFILE")
            if user_profile:
                return Path(user_profile) / "Documents"

    return Path.home() / "Documents"


def canonical_path(path) -> Optional[str]:
    """Return one absolute, normalized representation of a filesystem path."""
    try:
        value = os.fspath(path)
    except TypeError:
        return None

    if not isinstance(value, str) or not value:
        return None

    try:
        return os.path.normpath(
            os.path.realpath(os.path.abspath(os.path.expanduser(value)))
        )
    except (OSError, TypeError, ValueError):
        return None


def is_path_within(path, parent) -> bool:
    """Return True when *path* is *parent* itself or one of its descendants."""
    normalized_path = canonical_path(path)
    normalized_parent = canonical_path(parent)
    if normalized_path is None or normalized_parent is None:
        return False

    comparable_path = os.path.normcase(normalized_path)
    comparable_parent = os.path.normcase(normalized_parent)
    try:
        return (
            os.path.commonpath((comparable_path, comparable_parent))
            == comparable_parent
        )
    except (OSError, TypeError, ValueError):
        # ValueError is raised for paths on different Windows drives.
        return False


def relative_path_within(path, parent) -> Optional[str]:
    """Return a relative path only when *path* is contained by *parent*."""
    normalized_path = canonical_path(path)
    normalized_parent = canonical_path(parent)
    if (
        normalized_path is None
        or normalized_parent is None
        or not is_path_within(normalized_path, normalized_parent)
    ):
        return None

    try:
        return os.path.normpath(
            os.path.relpath(normalized_path, normalized_parent)
        )
    except (OSError, TypeError, ValueError):
        return None


def project_media_item_path(
    file_path,
    media_folder,
    project_root=None,
) -> Optional[str]:
    """
    Resolve ``Project/Item/<media_folder>/file`` to its Item directory.

    A supplied Project root also verifies that Item is a direct child of that
    Project. The sibling Image folder is intentionally not required here so an
    older/incomplete Item can be repaired when a captured frame is saved.
    """
    normalized_file = canonical_path(file_path)
    if (
        normalized_file is None
        or not isinstance(media_folder, str)
        or not media_folder
    ):
        return None

    media_path = os.path.dirname(normalized_file)
    if os.path.basename(media_path).casefold() != media_folder.casefold():
        return None

    item_path = os.path.dirname(media_path)

    if project_root is not None:
        normalized_project = canonical_path(project_root)
        if normalized_project is None:
            return None
        item_parent = canonical_path(os.path.dirname(item_path))
        if (
            item_parent is None
            or os.path.normcase(item_parent)
            != os.path.normcase(normalized_project)
        ):
            return None

    return item_path
