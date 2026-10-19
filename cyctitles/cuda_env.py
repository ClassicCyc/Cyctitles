"""Locate NVIDIA CUDA runtime DLLs shipped as pip packages (nvidia-*-cu12).

CTranslate2 (used by both whisper and the translator) dynamically loads cuBLAS
and cuDNN. Those come from the ``nvidia-*`` pip wheels, so we register their
``bin`` directories on the DLL search path before importing ctranslate2.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_REGISTERED = False


def _register(path: Path, added: list[str]) -> None:
    text = str(path)
    if text in added:
        return
    try:
        os.add_dll_directory(text)
    except (AttributeError, OSError):
        pass
    os.environ["PATH"] = text + os.pathsep + os.environ.get("PATH", "")
    added.append(text)


def _external_cuda_roots() -> list[Path]:
    """Folders where the installer may unpack an optional CUDA package.

    Checked before the bundled ``nvidia`` package so a user-installed CUDA
    pack (from the setup wizard) is picked up even in a CPU-only build.
    """
    roots: list[Path] = []
    # Next to the running executable (frozen onefile/onedir builds).
    try:
        roots.append(Path(sys.executable).resolve().parent)
    except Exception:  # noqa: BLE001
        pass
    # Next to the package/source tree (dev runs).
    roots.append(Path(__file__).resolve().parent.parent)
    # Explicit override.
    env_dir = os.environ.get("CYCTITLES_CUDA_DIR")
    if env_dir:
        roots.insert(0, Path(env_dir))
    return roots


def _iter_external_bins():
    """Yield candidate bin dirs from external ``cuda`` folders."""
    seen: set[str] = set()
    for root in _external_cuda_roots():
        cuda_dir = root / "cuda"
        if not cuda_dir.is_dir():
            continue
        # A flat cuda/ folder of DLLs, or cuda/<pkg>/bin layout.
        for bin_dir in [cuda_dir]:
            key = str(bin_dir).lower()
            if key not in seen and bin_dir.is_dir() and any(bin_dir.glob("*.dll")):
                seen.add(key)
                yield bin_dir
        for sub in cuda_dir.iterdir():
            if not sub.is_dir():
                continue
            bin_dir = sub / "bin" if (sub / "bin").is_dir() else sub
            key = str(bin_dir).lower()
            if key not in seen and any(bin_dir.glob("*.dll")):
                seen.add(key)
                yield bin_dir


def setup_cuda_dlls() -> list[str]:
    """Register CUDA DLL directories; safe to call repeatedly. Windows only."""
    global _REGISTERED
    if sys.platform != "win32" or _REGISTERED:
        return []
    _REGISTERED = True

    added: list[str] = []

    # 1. Installer-provided CUDA pack (external folder), if present.
    for bin_dir in _iter_external_bins():
        _register(bin_dir, added)

    # 2. Bundled nvidia-*-cu12 wheels (Repair/GPU build).
    try:
        import nvidia  # namespace package from nvidia-*-cu12 wheels
    except Exception:
        return added

    for base in getattr(nvidia, "__path__", []):
        root = Path(base)
        for sub in root.iterdir():
            if sub.is_dir() and sub.name.startswith("cuda_"):
                bin_dir = sub / "bin"
                if bin_dir.is_dir():
                    _register(bin_dir, added)
        for sub in root.iterdir():
            if sub.is_dir() and (sub / "bin").is_dir():
                _register(sub / "bin", added)
    return added


def cuda_runtime_available() -> bool:
    """Whether the cuBLAS/cuDNN runtime needed by CTranslate2 can be located.

    Used to fall back to CPU automatically in a CPU-only ("lite") build that
    has no bundled CUDA and no installer-provided ``cuda`` folder.
    """
    if sys.platform != "win32":
        return False
    setup_cuda_dlls()
    import ctypes

    for dll in ("cublas64_12.dll", "cudnn64_9.dll"):
        try:
            ctypes.WinDLL(dll)
        except OSError:
            return False
    return True
