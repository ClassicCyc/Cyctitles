# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Cyctitles - single-file CPU-only ("lite") build.

No NVIDIA CUDA runtime is bundled, so the file is much smaller. Users with an
NVIDIA GPU get CUDA from the installer, which unpacks an optional ``cuda``
folder next to the executable (picked up by cyctitles.cuda_env).
"""

import os
from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_all

HOOKS_DIR = os.path.join(SPECPATH, "pyinstaller_hooks")
ICON_ICO = os.path.join(SPECPATH, "cyctitles", "assets", "cycicon.ico")

datas = [
    ("overlay", "overlay"),
    ("cyctitles/assets", "cyctitles/assets"),
]
binaries = []
hiddenimports = []

# Bundle the interpreter's own DLL and stdlib extension modules explicitly.
_pyver = f"python{sys.version_info.major}{sys.version_info.minor}.dll"
for _cand in (
    Path(sys.base_prefix) / _pyver,
    Path(sys.executable).parent / _pyver,
    Path(sys.base_prefix) / "DLLs" / _pyver,
):
    if _cand.exists():
        binaries.append((str(_cand), "."))
        break
_dlls = Path(sys.base_prefix) / "DLLs"
if _dlls.is_dir():
    for _lib in list(_dlls.glob("*.pyd")) + list(_dlls.glob("*.dll")):
        binaries.append((str(_lib), "."))

for pkg in [
    "ctranslate2",
    "faster_whisper",
    "sentencepiece",
    "onnxruntime",
    "av",
    "tokenizers",
    "sounddevice",
    "soundcard",
    "cffi",
    "huggingface_hub",
    "aiohttp",
    "yarl",
    "multidict",
    "frozenlist",
    "aiosignal",
    "charset_normalizer",
]:
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

# NOTE: intentionally NO nvidia-*-cu12 bundling here (CPU-only build).
# ctranslate2 still ships its own CPU runtime.

excludes = [
    "nvidia",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel",
    "PySide6.QtQuick",
    "PySide6.QtQuickWidgets",
    "PySide6.QtQml",
    "PySide6.QtQuick3D",
    "PySide6.Qt3DCore",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtBluetooth",
    "PySide6.QtNfc",
    "PySide6.QtPositioning",
    "PySide6.QtSerialPort",
    "PySide6.QtSql",
    "PySide6.QtTest",
    "PySide6.QtDesigner",
    "PySide6.QtHelp",
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
    "tkinter",
    "matplotlib",
    "pandas",
    "scipy",
    "IPython",
    "pytest",
]

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[HOOKS_DIR],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Cyctitles",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    icon=ICON_ICO,
)
