# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

block_cipher = None
project_dir = Path(SPECPATH).resolve()

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
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

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
