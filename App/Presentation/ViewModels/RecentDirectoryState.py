#############################################################################
# @file App/Presentation/ViewModels/RecentDirectoryState.py
# Author: TRAN NGUYEN HIEN
# Email: trannguyenhien29085@gmail.com
#############################################################################
import os

from App.Infrastructure.CrashHandler import log_exception


class RecentDirectoryState:
    """Keep independent recent directories without performing file I/O."""

    def __init__(self, purposes, provider=None, recorder=None):
        self._purposes = frozenset(purposes)
        self._directories = {
            purpose: None for purpose in self._purposes
        }
        self._provider = provider
        self._recorder = recorder

    def _require_purpose(self, purpose):
        if purpose not in self._purposes:
            raise ValueError(f"Unknown editor directory purpose: {purpose}")

    @staticmethod
    def _normalize_directory(directory):
        if not isinstance(directory, str) or not directory.strip():
            return None
        return os.path.abspath(os.path.normpath(directory))

    @classmethod
    def _containing_directory(cls, file_path):
        if not isinstance(file_path, str) or not file_path.strip():
            return None
        return cls._normalize_directory(os.path.dirname(file_path))

    def get(self, purpose, current_path=None, fallback_path=None):
        self._require_purpose(purpose)
        candidates = []
        if callable(self._provider):
            try:
                candidates.append(self._provider(purpose))
            except Exception:
                log_exception(
                    f"Could not read the recent {purpose} directory"
                )
        candidates.append(self._directories[purpose])

        for candidate in candidates:
            directory = self._normalize_directory(candidate)
            if directory is not None:
                return directory

        for file_path in (current_path, fallback_path):
            directory = self._containing_directory(file_path)
            if directory is not None:
                return directory
        return ""

    def remember(self, purpose, file_path):
        self._require_purpose(purpose)
        directory = self._containing_directory(file_path)
        if directory is None:
            return
        self._directories[purpose] = directory
        if not callable(self._recorder):
            return
        try:
            self._recorder(purpose, directory)
        except Exception:
            # A preference failure must never break a valid media operation.
            log_exception(f"Could not remember the recent {purpose} directory")
