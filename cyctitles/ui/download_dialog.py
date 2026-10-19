"""Dialogs for warning about missing models and downloading them."""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from ..i18n import tr
from ..models import ModelInfo, directory_size, download_model_info, human_size


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


class ModelDownloadWorker(QThread):
    progress = Signal(str)
    failed = Signal(str)
    finished_ok = Signal()

    def __init__(
        self,
        infos: list[ModelInfo],
        models_dir: Path,
        parent: QWidget | None = None,
        force: bool = False,
    ) -> None:
        super().__init__(parent)
        self._infos = infos
        self._models_dir = models_dir
        self._force = force

    def run(self) -> None:  # noqa: D102
        try:
            for info in self._infos:
                self.progress.emit(info.label)
                download_model_info(info, self._models_dir, force=self._force)
            self.finished_ok.emit()
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class _DownloadDialog(QDialog):
    """Modal, non-cancellable dialog with a live progress bar."""

    def __init__(self, total_bytes: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("dl_downloading_title"))
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setMinimumWidth(480)
        self._total = max(1, total_bytes)
        self._allow_close = False

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

    def set_file(self, label: str) -> None:
        self.file_label.setText(tr("dl_downloading_file", label=label))

    def set_busy(self) -> None:
        """Show an indeterminate bar (used for repair/force re-downloads)."""
        self.bar.setRange(0, 0)

    def set_progress(self, downloaded: int, speed: float, eta: float | None) -> None:
        fraction = min(0.99, downloaded / self._total)
        self.bar.setValue(int(fraction * 100))
        parts = [
            f"{human_size(downloaded)} / {human_size(self._total)}",
            f"{fraction * 100:.0f}%",
        ]
        if speed > 1:
            parts.append(f"{human_size(int(speed))}/s")
        if eta is not None and eta > 0 and speed > 1:
            parts.append(tr("dl_eta_left", eta=_format_eta(eta)))
        self.detail_label.setText("  ·  ".join(parts))

    def finish(self) -> None:
        if self.bar.maximum() == 0:
            self.bar.setRange(0, 100)
        self.bar.setValue(100)
        self._allow_close = True
        self.close()

    def keyPressEvent(self, event) -> None:  # noqa: N802, ANN001
        if event.key() == Qt.Key.Key_Escape:
            return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802, ANN001
        if self._allow_close:
            super().closeEvent(event)
        else:
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
    directories = [Path(info.directory) for info in infos]
    baseline = sum(directory_size(d) for d in directories)

    progress = _DownloadDialog(total_bytes, parent)
    if force:
        progress.set_busy()
    state = {"ok": False, "error": "", "last_bytes": 0, "last_time": time.monotonic()}

    worker = ModelDownloadWorker(infos, models_dir, parent, force=force)

    timer = QTimer(progress)
    timer.setInterval(300)

    def tick() -> None:
        now = time.monotonic()
        downloaded = max(0, sum(directory_size(d) for d in directories) - baseline)
        elapsed = max(1e-3, now - state["last_time"])
        speed = max(0.0, (downloaded - state["last_bytes"]) / elapsed)
        state["last_bytes"] = downloaded
        state["last_time"] = now
        remaining = total_bytes - downloaded
        eta = remaining / speed if speed > 1 else None
        progress.set_progress(downloaded, speed, eta)

    timer.timeout.connect(tick)

    def _ok() -> None:
        timer.stop()
        state["ok"] = True
        progress.finish()

    def _err(message: str) -> None:
        timer.stop()
        state["error"] = message
        progress.finish()

    worker.progress.connect(progress.set_file)
    worker.finished_ok.connect(_ok)
    worker.failed.connect(_err)
    timer.start()
    worker.start()
    progress.exec()
    worker.wait(5000)
    timer.stop()
    return state["ok"], state["error"]
