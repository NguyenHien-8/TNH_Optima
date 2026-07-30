###########################################################
# @file App/Infrastructure/Repositories/ConfigRepository.py
# Author: TRAN NGUYEN HIEN
# Email: trannguyenhien29085@gmail.com
###########################################################
import sqlite3
import os
import threading
from contextlib import contextmanager
from typing import Optional, Dict, Any
from App.Infrastructure.Repositories.StoragePath import persistent_database_path

class ConfigRepository:
    """
    Repository that reads and writes application configuration in SQLite.
    Uses the 'app_config' table with a key-value structure.
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize the repository. When db_path is omitted, use the isolated
        data area for either source runtime or the packaged application.
        """
        if db_path is None:
            db_path = persistent_database_path("ConfigStorage.db")
        
        self.db_path = db_path
        self._init_lock = threading.Lock()
        self._initialized = False

    def _init_db(self):
        """Create the table if it does not already exist."""
        if self._initialized:
            return
        with self._init_lock:
            if self._initialized:
                return
            os.makedirs(
                os.path.dirname(os.path.abspath(self.db_path)),
                exist_ok=True,
            )
            connection = sqlite3.connect(self.db_path, timeout=5.0)
            try:
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS app_config (
                        key TEXT PRIMARY KEY,
                        value TEXT
                    )
                """)
                connection.commit()
            finally:
                connection.close()
            self._initialized = True

    @contextmanager
    def _get_connection(self):
        """Return a database connection for internal use."""
        self._init_db()
        connection = sqlite3.connect(self.db_path, timeout=5.0)
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    # --- Generic methods ---
    def set_config(self, key: str, value: Any):
        """Store one key-value pair, converting the value to a string."""
        if not isinstance(key, str) or not key:
            raise ValueError("Configuration key must be a non-empty string.")
        with self._get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO app_config (key, value) VALUES (?, ?)",
                (key, str(value))
            )

    def get_config(self, key: str) -> Optional[str]:
        """Return the key value, or None when the key does not exist."""
        if not isinstance(key, str) or not key:
            return None
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT value FROM app_config WHERE key = ?", (key,)
            ).fetchone()
        return row[0] if row else None

    def delete_config(self, key: str):
        """Delete a key from the database."""
        if not isinstance(key, str) or not key:
            return
        with self._get_connection() as conn:
            conn.execute("DELETE FROM app_config WHERE key = ?", (key,))

    # --- Camera config ---
    def save_camera_index(self, index: Optional[int]):
        """Save the active camera index."""
        if index is None:
            self.delete_config("camera_index")
        else:
            self.set_config("camera_index", index)

    def load_camera_index(self) -> Optional[int]:
        """Load the camera index, returning None when it has not been saved."""
        val = self.get_config("camera_index")
        if val is not None:
            try:
                return int(val)
            except ValueError:
                return None
        return None

    # --- Hardware config ---
    def save_hardware_config(self, port: str, baud: int, period: int):
        """Save the hardware configuration."""
        values = (
            ("hardware_port", str(port)),
            ("hardware_baud", str(baud)),
            ("hardware_period", str(period)),
        )
        with self._get_connection() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO app_config (key, value) VALUES (?, ?)",
                values,
            )

    def load_hardware_config(self) -> Dict[str, Any]:
        """Load hardware configuration with 'port', 'baud', and 'period' keys."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT key, value FROM app_config "
                "WHERE key IN ('hardware_port', 'hardware_baud', 'hardware_period')"
            ).fetchall()
        values = dict(rows)
        port = values.get("hardware_port") or ""
        baud_str = values.get("hardware_baud")
        period_str = values.get("hardware_period")
        try:
            baud = int(baud_str) if baud_str is not None else 115200
            if baud <= 0:
                raise ValueError
        except (TypeError, ValueError):
            baud = 115200
        try:
            period = int(period_str) if period_str is not None else 100
            if period <= 0:
                raise ValueError
        except (TypeError, ValueError):
            period = 100
        return {
            "port": port,
            "baud": baud,
            "period": period
        }

    def clear_hardware_config(self):
        """Clear all hardware configuration values on disconnect."""
        with self._get_connection() as conn:
            conn.execute(
                "DELETE FROM app_config WHERE key IN "
                "('hardware_port', 'hardware_baud', 'hardware_period')"
            )

    # --- Image editor config ---
    _EDITOR_DIRECTORY_KEYS = {
        "image_open": "image_editor_open_directory",
        "image_capture": "image_editor_capture_directory",
        "video_open": "video_editor_open_directory",
        "video_capture": "video_editor_capture_directory",
        "droplet_analysis_save": "droplet_analysis_save_directory",
        "sidebar_image_open": "sidebar_item_open_image_directory",
        "sidebar_video_open": "sidebar_item_open_video_directory",
    }

    def save_editor_directory(self, purpose: str, directory: str):
        """Save one independent editor file-dialog directory."""
        key = self._EDITOR_DIRECTORY_KEYS.get(purpose)
        if key is None:
            raise ValueError(f"Unknown editor directory purpose: {purpose}")
        if not isinstance(directory, str) or not directory.strip():
            raise ValueError("Editor directory must be a non-empty string.")
        self.set_config(key, directory)

    def load_editor_directories(self) -> Dict[str, Optional[str]]:
        """Load all independent editor directories with legacy migration."""
        keys = tuple(self._EDITOR_DIRECTORY_KEYS.values())
        placeholders = ", ".join("?" for _key in keys)
        with self._get_connection() as conn:
            rows = conn.execute(
                f"SELECT key, value FROM app_config WHERE key IN "
                f"({placeholders}, ?)",
                (*keys, "image_editor_last_directory"),
            ).fetchall()
        values = dict(rows)
        legacy_value = values.get("image_editor_last_directory")
        return {
            purpose: (
                values.get(key)
                or (
                    legacy_value
                    if purpose in ("image_open", "image_capture")
                    else None
                )
            )
            for purpose, key in self._EDITOR_DIRECTORY_KEYS.items()
        }

    def save_image_editor_directory(self, purpose: str, directory: str):
        """Compatibility wrapper for ImageEditor directory settings."""
        mapped_purpose = {
            "open": "image_open",
            "capture": "image_capture",
        }.get(purpose)
        if mapped_purpose is None:
            raise ValueError(f"Unknown ImageEditor directory purpose: {purpose}")
        self.save_editor_directory(mapped_purpose, directory)

    def load_image_editor_directories(self) -> Dict[str, Optional[str]]:
        """Compatibility view of the two ImageEditor directory settings."""
        values = self.load_editor_directories()
        return {
            "open": values["image_open"],
            "capture": values["image_capture"],
        }
