# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

block_cipher = None
project_dir = Path(SPECPATH).resolve()
excluded_database_names = {
    'configstorage.db',
    'sessiondata.db',
}


def is_runtime_database_path(path):
    """Return True for a runtime DB or one of its SQLite sidecar files."""
    file_name = Path(path).name.casefold()
    return any(
        file_name == database_name
        or file_name.startswith(f'{database_name}-')
        or file_name.startswith(f'{database_name}.')
        for database_name in excluded_database_names
    )


def without_runtime_databases(entries):
    """Prevent runtime/test databases from entering the frozen application."""
    return [
        entry
        for entry in entries
        if not is_runtime_database_path(entry[0])
        and not is_runtime_database_path(entry[1])
    ]

# PyInstaller's standard hooks collect the native libraries and Qt plugins for
# the modules imported by the application. Do not collect the whole PyQt6
# package: doing so adds unused QML, Qt3D, Bluetooth, WebEngine and .sip sources.
datas = [
    (str(project_dir / 'App/ReSource'), 'App/ReSource'),
]

a = Analysis(
    [str(project_dir / 'main.py')],
    pathex=[str(project_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'cv2',
        'numpy',
        'scipy.optimize',
        'scipy.linalg',
        'serial',
        'serial.tools.list_ports',
        'PIL.Image',
        'PIL.ImageQt',
        'matplotlib.backends.backend_qt5agg',
        'sqlite3',
        'PyQt6.QtMultimedia',
        'PyQt6.QtMultimediaWidgets',
        'send2trash.win.legacy',
        'send2trash.win.modern',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

# Hooks added by future dependencies must not be able to collect development
# or user databases implicitly.
a.datas = without_runtime_databases(a.datas)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='TNH Optima',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(project_dir / 'App/ReSource/Icon/app_icon.ico')
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='TNH Optima',
)
