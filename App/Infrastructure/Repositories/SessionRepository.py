############################################################
# @file App/Infrastructure/Repositories/SessionRepository.py
# Author: TRAN NGUYEN HIEN
# Email: trannguyenhien29085@gmail.com
############################################################
import sqlite3
import os
import json
import threading
from contextlib import contextmanager
from typing import Optional, Any
from App.Infrastructure.Repositories.StoragePath import persistent_database_path

class SessionRepository:
    """
    Repository that reads and writes session data in SQLite.
    Uses the 'session' table with a key-value structure.
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize the repository. When db_path is omitted, use the isolated
        data area for either source runtime or the packaged application.
        """
        if db_path is None:
            db_path = persistent_database_path("SessionData.db")

        self.db_path = db_path
        self._init_lock = threading.Lock()
        self._initialized = False

    def _init_db(self):
        """Create the session table if it does not already exist."""
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
                    CREATE TABLE IF NOT EXISTS session (
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

    def save_session(self, key: str, value: Any):
        """
        Store one key-value pair in the session table.
        The value is serialized to a JSON string.
        """
        if not isinstance(key, str) or not key:
            raise ValueError("Session key must be a non-empty string.")
        payload = json.dumps(value, ensure_ascii=False)
        with self._get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO session (key, value) VALUES (?, ?)",
                (key, payload)
            )

    def load_session(self, key: str) -> Optional[Any]:
        """
        Read a key value from the session table.
        Return the decoded JSON data, or None when the key does not exist.
        """
        if not isinstance(key, str) or not key:
            return None
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT value FROM session WHERE key = ?", (key,)
            ).fetchone()
        if row:
            try:
                return json.loads(row[0])
            except (json.JSONDecodeError, TypeError):
                return None
        return None
