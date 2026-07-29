########################################################
# @file App/Models/SessionManager.py
# Author: TRAN NGUYEN HIEN
# Email: trannguyenhien29085@gmail.com
########################################################
from typing import List, Dict, Set
from App.Infrastructure.Repositories.SessionRepository import SessionRepository

class SessionManager:
    """
    Quản lý phiên làm việc: lưu và khôi phục danh sách project, editor, trạng thái expanded, và các item đang mở.
    """

    SESSION_KEY_OPEN_PROJECTS = "open_projects"
    SESSION_KEY_OPEN_EDITORS = "open_editors"
    SESSION_KEY_EXPANDED_PATHS = "expanded_paths"
    SESSION_KEY_OPENED_ITEMS = "opened_items"
    SESSION_KEY_SIDEBAR_ORDER = "sidebar_order"
    SESSION_KEY_HIDDEN_MEDIA_PATHS = "hidden_media_paths"

    def __init__(self, repo: SessionRepository):
        self.repo = repo
        self._open_projects: List[str] = []
        self._open_editors: List[Dict[str, str]] = []
        self._expanded_paths: List[str] = []
        self._opened_items_serializable: Dict[str, List[str]] = {}
        self._sidebar_order = {"projects": [], "items": {}}
        self._hidden_media_paths: List[str] = []

    # --- Projects ---
    def set_open_projects(self, project_paths: List[str]):
        self._open_projects = project_paths[:]

    def get_open_projects(self) -> List[str]:
        return self._open_projects[:]

    def save_projects(self):
        self.repo.save_session(self.SESSION_KEY_OPEN_PROJECTS, self._open_projects)

    def load_projects(self) -> List[str]:
        data = self.repo.load_session(self.SESSION_KEY_OPEN_PROJECTS)
        if isinstance(data, list):
            self._open_projects = data
        else:
            self._open_projects = []
        return self.get_open_projects()

    # --- Editors ---
    def set_open_editors(self, editor_list: List[Dict[str, str]]):
        self._open_editors = editor_list[:]

    def get_open_editors(self) -> List[Dict[str, str]]:
        return self._open_editors[:]

    def save_editors(self):
        self.repo.save_session(self.SESSION_KEY_OPEN_EDITORS, self._open_editors)

    def load_editors(self) -> List[Dict[str, str]]:
        data = self.repo.load_session(self.SESSION_KEY_OPEN_EDITORS)
        if isinstance(data, list):
            self._open_editors = data
        else:
            self._open_editors = []
        return self.get_open_editors()

    # --- Expanded paths ---
    def set_expanded_paths(self, paths: List[str]):
        self._expanded_paths = paths[:]

    def get_expanded_paths(self) -> List[str]:
        return self._expanded_paths[:]

    def save_expanded_paths(self):
        self.repo.save_session(self.SESSION_KEY_EXPANDED_PATHS, self._expanded_paths)

    def load_expanded_paths(self) -> List[str]:
        data = self.repo.load_session(self.SESSION_KEY_EXPANDED_PATHS)
        if isinstance(data, list):
            self._expanded_paths = data
        else:
            self._expanded_paths = []
        return self.get_expanded_paths()

    # --- Opened items ---
    def set_opened_items(self, opened_items: Dict[str, Set[str]]):
        """Convert the set into a list to save it."""
        self._opened_items_serializable = {}
        for proj, items_set in opened_items.items():
            self._opened_items_serializable[proj] = list(items_set)

    def get_opened_items(self) -> Dict[str, Set[str]]:
        """Returns a dict with a value of set."""
        return {proj: set(items) for proj, items in self._opened_items_serializable.items()}

    def save_opened_items(self):
        self.repo.save_session(self.SESSION_KEY_OPENED_ITEMS, self._opened_items_serializable)

    def load_opened_items(self) -> Dict[str, Set[str]]:
        data = self.repo.load_session(self.SESSION_KEY_OPENED_ITEMS)
        if isinstance(data, dict):
            self._opened_items_serializable = data
            return self.get_opened_items()
        return {}

    # --- Sidebar order ---
    def set_sidebar_order(self, order):
        if not isinstance(order, dict):
            self._sidebar_order = {"projects": [], "items": {}}
            return

        projects = order.get("projects", [])
        items = order.get("items", {})
        clean_projects = self._unique_nonempty_strings(projects)
        clean_items = {}
        if isinstance(items, dict):
            for project_path, item_names in items.items():
                if (
                    not isinstance(project_path, str)
                    or not project_path.strip()
                    or not isinstance(item_names, list)
                ):
                    continue
                clean_items[project_path] = self._unique_nonempty_strings(
                    item_names
                )

        self._sidebar_order = {
            "projects": clean_projects,
            "items": clean_items,
        }

    @staticmethod
    def _unique_nonempty_strings(values):
        if not isinstance(values, list):
            return []
        result = []
        seen = set()
        for value in values:
            if not isinstance(value, str) or not value.strip() or value in seen:
                continue
            result.append(value)
            seen.add(value)
        return result

    def get_sidebar_order(self):
        return {
            "projects": list(self._sidebar_order["projects"]),
            "items": {
                project_path: list(item_names)
                for project_path, item_names in self._sidebar_order["items"].items()
            },
        }

    def save_sidebar_order(self):
        self.repo.save_session(
            self.SESSION_KEY_SIDEBAR_ORDER,
            self._sidebar_order,
        )

    def load_sidebar_order(self):
        self.set_sidebar_order(
            self.repo.load_session(self.SESSION_KEY_SIDEBAR_ORDER)
        )
        return self.get_sidebar_order()

    # --- Media files removed from the Sidebar but kept on disk ---
    def set_hidden_media_paths(self, paths):
        self._hidden_media_paths = self._unique_nonempty_strings(paths)

    def get_hidden_media_paths(self):
        return list(self._hidden_media_paths)

    def save_hidden_media_paths(self):
        self.repo.save_session(
            self.SESSION_KEY_HIDDEN_MEDIA_PATHS,
            self._hidden_media_paths,
        )

    def load_hidden_media_paths(self):
        self.set_hidden_media_paths(
            self.repo.load_session(self.SESSION_KEY_HIDDEN_MEDIA_PATHS)
        )
        return self.get_hidden_media_paths()

    # --- Combined save/load ---
    def save_all(self):
        self.save_projects()
        self.save_editors()
        self.save_expanded_paths()
        self.save_opened_items()
        self.save_sidebar_order()
        self.save_hidden_media_paths()

    def load_all(self):
        self.load_projects()
        self.load_editors()
        self.load_expanded_paths()
        self.load_opened_items()
        self.load_sidebar_order()
        self.load_hidden_media_paths()
