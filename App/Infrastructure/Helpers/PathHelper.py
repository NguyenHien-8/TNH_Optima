########################################################
# @file App/Infrastructure/Helpers/PathHelper.py
# Author: TRAN NGUYEN HIEN
# Email: trannguyenhien29085@gmail.com
########################################################
import os
from typing import Optional


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
    if not os.path.isdir(item_path):
        return None

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
