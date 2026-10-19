# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Cyctitles (onedir build with bundled CUDA libs)."""

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
# Needed for uv-managed Python (and other non-standard layouts), where
# PyInstaller otherwise misses python312.dll / select.pyd etc.
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

# NVIDIA CUDA runtime DLLs (nvidia-*-cu12). Placed once, under the
# nvidia/<pkg>/bin layout that cuda_env.setup_cuda_dlls() registers at startup.
try:
    import nvidia

    for base in nvidia.__path__:
        for pkg_dir in Path(base).iterdir():
            bin_dir = pkg_dir / "bin"
            if not (pkg_dir.is_dir() and bin_dir.is_dir()):
                continue
            for dll in bin_dir.glob("*.dll"):
                binaries.append((str(dll), f"nvidia/{pkg_dir.name}/bin"))
except Exception:
    pass

excludes = [
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
    [],
    exclude_binaries=True,
    name="Cyctitles",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=ICON_ICO,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Cyctitles",
)
