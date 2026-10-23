"""Cyctitles entry point."""

from __future__ import annotations

import logging
import os
import sys

# --- Fix windowed-build streams BEFORE importing anything that may print ----
# PyInstaller builds with console=False have sys.stdout/sys.stderr == None.
# huggingface_hub (tqdm) writes progress bars to sys.stderr and otherwise dies
# with "'NoneType' object has no attribute 'write'".
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")
# Progress bars are the crash source and useless in a GUI; disable them.
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from cyctitles import __version__  # noqa: E402
from cyctitles.config import APP_NAME, AUTHOR, data_dir  # noqa: E402
from cyctitles.ui import MainWindow  # noqa: E402

log = logging.getLogger("cyctitles.app")

_SINGLE_INSTANCE_MUTEX = "Local\\Cyctitles-SingleInstance"
_ERROR_ALREADY_EXISTS = 183


def _setup_logging() -> None:
    log_path = data_dir() / "cyctitles.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(log_path),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        encoding="utf-8",
    )

    def _hook(exc_type, exc, tb):  # noqa: ANN001
        logging.error("Unhandled exception", exc_info=(exc_type, exc, tb))
        try:
            QMessageBox.critical(None, f"{APP_NAME} error", str(exc))
        except Exception:
            pass

    sys.excepthook = _hook


def _acquire_single_instance() -> bool:
    """Return False if another Cyctitles instance already owns the mutex."""
    if sys.platform != "win32":
        return True
    try:
        import ctypes

        handle = ctypes.windll.kernel32.CreateMutexW(None, False, _SINGLE_INSTANCE_MUTEX)
        if ctypes.windll.kernel32.GetLastError() == _ERROR_ALREADY_EXISTS:
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
            return False
        # Keep the handle alive for the whole process; the OS frees it on exit.
        globals()["_MUTEX_HANDLE"] = handle
        return True
    except Exception:  # noqa: BLE001
        return True


def _focus_existing_window() -> None:
    """Bring the already-running Cyctitles window to the front (best effort)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, APP_NAME)
        if hwnd:
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            user32.SetForegroundWindow(hwnd)
    except Exception:  # noqa: BLE001
        pass


def main() -> int:
    _setup_logging()
    log.info("Cyctitles %s starting (frozen=%s)", __version__, getattr(sys, "frozen", False))

    if "--selftest" in sys.argv:
        from cyctitles.selftest import run_selftest

        return run_selftest()

    if not _acquire_single_instance():
        log.info("Another instance is already running; focusing it and exiting.")
        _focus_existing_window()
        return 0

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName(AUTHOR)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
