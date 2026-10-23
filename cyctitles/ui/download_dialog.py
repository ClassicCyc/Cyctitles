"""Dialogs for warning about missing models and downloading them."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..i18n import tr
from ..models import DownloadCancelled, ModelInfo, download_model_info, human_size

log = logging.getLogger("cyctitles.download")


class MissingModelsDialog(QDialog):
    """'Model is not downloaded. Install it?' with size, folder and source."""

    def __init__(self, infos: list[ModelInfo], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        plural = len(infos) != 1
        self.setWindowTitle(tr("dl_missing_title_many" if plural else "dl_missing_title_one"))
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        heading = QLabel(tr("dl_missing_head_many" if plural else "dl_missing_head_one"))
        heading.setStyleSheet("font-size: 15px; font-weight: 600;")
        heading.setWordWrap(True)
        layout.addWidget(heading)

        for info in infos:
            layout.addWidget(self._model_box(info))

        note = QLabel(tr("dl_missing_note"))
        note.setStyleSheet("color: gray; font-size: 11px;")
        note.setWordWrap(True)
        layout.addWidget(note)

        buttons = QDialogButtonBox()
        install = buttons.addButton(tr("btn_install"), QDialogButtonBox.ButtonRole.AcceptRole)
        install.setDefault(True)
        buttons.addButton(tr("btn_cancel"), QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _model_box(info: ModelInfo) -> QGroupBox:
        box = QGroupBox(info.label)
        form = QFormLayout(box)

        size = QLabel(tr("dl_size_download", size=info.size_text))
        form.addRow(tr("dl_size"), size)

        directory = QLabel(str(info.directory))
        directory.setWordWrap(True)
        directory.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        directory.setStyleSheet("font-family: Consolas, monospace; font-size: 11px;")
        form.addRow(tr("dl_folder"), directory)

        source = QLabel(f'<a href="{info.url}">{info.repo_id} — Hugging Face</a>')
        source.setOpenExternalLinks(True)
        form.addRow(tr("dl_source"), source)
        return box


class _DownloadSignals(QObject):
    progress = Signal(str)
    bytes_progress = Signal(int, int)
    failed = Signal(str)
    finished_ok = Signal()


class ModelDownloadWorker:
    """Downloads models on a **daemon** thread.

    A daemon thread (unlike a QThread) never keeps the process alive, so a
    stalled network download can no longer leave a zombie Cyctitles process
    behind after the window is closed.
    """

    def __init__(
        self,
        infos: list[ModelInfo],
        models_dir: Path,
        parent: QWidget | None = None,
        force: bool = False,
    ) -> None:
        self._infos = infos
        self._models_dir = Path(models_dir)
        self._force = force
        self._cancelled = False
        self._thread: threading.Thread | None = None
        self._last_emit = 0.0
        self._last_done = -1
        self.signals = _DownloadSignals()

    def cancel(self) -> None:
        self._cancelled = True

    def _emit_bytes(self, done: int, total: int) -> None:
        """Forward byte progress to the GUI, throttled to avoid signal flooding."""
        now = time.monotonic()
        if (
            done < total
            and now - self._last_emit < 0.1
            and abs(done - self._last_done) < 131072
        ):
            return
        self._last_emit = now
        self._last_done = done
        self.signals.bytes_progress.emit(max(0, int(done)), max(0, int(total)))

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="cyctitles-download"
        )
        self._thread.start()

    def wait(self, timeout_ms: int = 0) -> bool:
        if self._thread is None:
            return True
        self._thread.join(timeout_ms / 1000.0 if timeout_ms else None)
        return not self._thread.is_alive()

    def _run(self) -> None:
        try:
            base = 0
            grand_total = sum(max(int(i.size_bytes or 0), 0) for i in self._infos) or 1
            for info in self._infos:
                if self._cancelled:
                    log.info("Download cancelled by user")
                    return
                log.info("Downloading %s from %s -> %s", info.label, info.repo_id, info.directory)
                self.signals.progress.emit(info.label)
                current = {"total": int(info.size_bytes or 0)}

                def report(
                    done: int,
                    total: int,
                    _base: int = base,
                    _cur: dict = current,
                    _grand: int = grand_total,
                ) -> None:
                    if self._cancelled:
                        raise DownloadCancelled
                    # HF briefly reports a tiny total while probing small files;
                    # keep the expected model size as a lower bound so the bar
                    # never jumps to 100% and back.
                    if total > int(_cur["total"]):
                        _cur["total"] = int(total)
                    self._emit_bytes(_base + int(done), _grand)

                download_model_info(
                    info, self._models_dir, force=self._force, progress=report
                )
                base += current["total"]
                self._emit_bytes(base, grand_total)
                log.info("Downloaded %s", info.label)
            self.signals.finished_ok.emit()
        except DownloadCancelled:
            log.info("Download cancelled by user")
        except Exception as exc:  # noqa: BLE001
            log.exception("Download failed: %s", exc)
            self.signals.failed.emit(str(exc))


class _DownloadDialog(QDialog):
    """Modal dialog with a live progress bar and a Cancel button."""

    def __init__(self, total_bytes: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("dl_downloading_title"))
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setMinimumWidth(480)
        self._total = max(1, total_bytes)
        self._last_bytes = 0
        self._last_time = time.monotonic()
        self._speed = 0.0
        self._allow_close = False
        self.was_cancelled = False

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        self.file_label = QLabel(tr("dl_preparing"))
        self.file_label.setWordWrap(True)
        layout.addWidget(self.file_label)

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        layout.addWidget(self.bar)

        self.detail_label = QLabel(tr("dl_starting"))
        self.detail_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(self.detail_label)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.cancel_button = QPushButton(tr("btn_cancel"))
        self.cancel_button.clicked.connect(self._on_cancel)
        buttons.addWidget(self.cancel_button)
        layout.addLayout(buttons)

    def set_file(self, label: str) -> None:
        self.file_label.setText(tr("dl_downloading_file", label=label))

    def set_bytes(self, done: int, total: int) -> None:
        if total > 0:
            self._total = total
        now = time.monotonic()
        elapsed = now - self._last_time
        if elapsed >= 0.25:
            self._speed = max(0.0, (done - self._last_bytes) / elapsed)
            self._last_bytes = done
            self._last_time = now
        fraction = min(1.0, done / self._total) if self._total > 0 else 0.0
        if done < self._total:
            fraction = min(fraction, 0.99)
        self.bar.setRange(0, 100)
        self.bar.setValue(int(fraction * 100))
        remaining = max(0, self._total - done)
        eta = remaining / self._speed if self._speed > 1 else None
        parts = [
            f"{human_size(done)} / {human_size(self._total)}",
            f"{fraction * 100:.0f}%",
        ]
        if self._speed > 1:
            parts.append(f"{human_size(int(self._speed))}/s")
        if eta is not None and eta > 0:
            parts.append(tr("dl_eta_left", eta=_format_eta(eta)))
        self.detail_label.setText("  ·  ".join(parts))

    def finish(self) -> None:
        if self.bar.maximum() == 0:
            self.bar.setRange(0, 100)
        self.bar.setValue(100)
        self._allow_close = True
        self.close()

    def _on_cancel(self) -> None:
        self.was_cancelled = True
        self._allow_close = True
        self.close()

    def keyPressEvent(self, event) -> None:  # noqa: N802, ANN001
        if event.key() == Qt.Key.Key_Escape:
            self._on_cancel()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802, ANN001
        if self._allow_close:
            super().closeEvent(event)
        else:
            self._on_cancel()
            event.ignore()


def _format_eta(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m{sec:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m"


def run_download(
    infos: list[ModelInfo],
    models_dir: Path,
    parent: QWidget | None = None,
    force: bool = False,
) -> tuple[bool, str]:
    """Download ``infos`` with a live progress dialog. Returns (ok, error)."""
    if not infos:
        return True, ""

    total_bytes = sum(max(info.size_bytes, 0) for info in infos) or 1

    progress = _DownloadDialog(total_bytes, parent)
    state = {"ok": False, "error": ""}

    worker = ModelDownloadWorker(infos, models_dir, parent, force=force)

    def _ok() -> None:
        state["ok"] = True
        progress.finish()

    def _err(message: str) -> None:
        state["error"] = message
        progress.finish()

    worker.signals.progress.connect(progress.set_file)
    worker.signals.bytes_progress.connect(progress.set_bytes)
    worker.signals.finished_ok.connect(_ok)
    worker.signals.failed.connect(_err)
    worker.start()
    progress.exec()

    # The dialog is gone. If the user cancelled, ask the worker to stop (the
    # thread is a daemon, so it can never keep the process alive either way).
    if progress.was_cancelled:
        worker.cancel()
    else:
        worker.wait(5000)
    return state["ok"], state["error"]
