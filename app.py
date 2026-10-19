"""Cyctitles entry point."""

from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from cyctitles import __version__
from cyctitles.config import APP_NAME, AUTHOR, data_dir
from cyctitles.ui import MainWindow


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


def main() -> int:
    _setup_logging()

    if "--selftest" in sys.argv:
        from cyctitles.selftest import run_selftest

        return run_selftest()

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

