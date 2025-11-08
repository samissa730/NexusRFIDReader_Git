# -*- mode: python ; coding: utf-8 -*-

"""
PyInstaller build specification for the Nexus RFID Reader kiosk application.

This spec bundles the PySide6 UI, resource assets, and Python modules into a
self-contained distribution. It purposefully excludes the Azure IoT helper
tooling which is shipped separately for development flows.
"""

import pathlib
from PyInstaller.utils.hooks import collect_submodules

project_root = pathlib.Path(__file__).resolve().parent

datas = [
    (str(project_root / "ui"), "ui"),
    (str(project_root / "font"), "font"),
]

binaries = []
hiddenimports = collect_submodules("PySide6")

block_cipher = None

a = Analysis(
    ["main.py"],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["Azure-IoT-Connection"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="NexusRFIDReader",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="NexusRFIDReader",
)

