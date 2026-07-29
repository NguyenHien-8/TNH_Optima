#######################################################
# @file App/Infrastructure/Repositories/StoragePath.py
# Author: TRAN NGUYEN HIEN
# Email: trannguyenhien29085@gmail.com
#######################################################
import os
from pathlib import Path
import sys


APPLICATION_STORAGE_NAME = "TNH Optima"
DEVELOPMENT_STORAGE_NAME = "TNH Optima Development"


def persistent_database_path(file_name):
    """Return a writable DB path isolated by application runtime."""
    if not isinstance(file_name, str) or not file_name:
        raise ValueError("Database file name must be a non-empty string.")

    app_data = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    root = Path(app_data) if app_data else Path.home() / ".tnh_optima"
    storage_name = (
        APPLICATION_STORAGE_NAME
        if getattr(sys, "frozen", False)
        else DEVELOPMENT_STORAGE_NAME
    )
    storage_dir = root / storage_name / "Data"
    return str(storage_dir / file_name)
