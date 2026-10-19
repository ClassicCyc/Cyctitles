"""Small audio UX helpers: an input level meter and a short "test input" probe."""

from __future__ import annotations

import queue
import threading
import time

import numpy as np
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPaintEvent
from PySide6.QtWidgets import QWidget

from ..audio import AudioCapture, LoopbackCapture
from ..vad import level_fraction


def _parse_index(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


class LevelMeter(QWidget):
    """A slim gradient VU bar driven by RMS values (0…1)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._level = 0.0
        self._peak = 0.0
        self._peak_frames = 0
        self.setMinimumWidth(120)
        self.setFixedHeight(14)
        self.setToolTip("Live input level")

    def set_level(self, rms: float) -> None:
        frac = level_fraction(float(rms))
        if frac >= self._peak:
            self._peak = frac
            self._peak_frames = 30
        elif self._peak_frames > 0:
            self._peak_frames -= 1
        else:
            self._peak = max(0.0, self._peak - 0.01)
        self._level = frac
        self.update()

    def reset(self) -> None:
        self._level = 0.0
        self._peak = 0.0
        self._peak_frames = 0
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.rect().adjusted(0, 1, 0, -1)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 40))
        painter.drawRoundedRect(rect, 4, 4)

        width = int(rect.width() * self._level)
        if width > 0:
            grad = QLinearGradient(rect.left(), 0, rect.right(), 0)
            grad.setColorAt(0.0, QColor("#2ecc71"))
            grad.setColorAt(0.65, QColor("#f1c40f"))
            grad.setColorAt(0.9, QColor("#e74c3c"))
            painter.setBrush(grad)
            painter.drawRoundedRect(
                rect.left(), rect.top(), max(2, width), rect.height(), 4, 4
            )

        if self._peak > 0:
            x = rect.left() + int(rect.width() * self._peak)
            painter.setBrush(QColor(255, 255, 255, 180))
            painter.drawRect(max(rect.left(), x - 1), rect.top(), 2, rect.height())
        painter.end()


class InputMonitor(QObject):
    """Captures the configured source for a few seconds and reports its level.

    Runs the capture on a worker thread and emits Qt signals, so it is safe to
    use from the UI while the main pipeline is stopped.
    """

    level = Signal(float)
    finished = Signal(bool, float)  # (signal_detected, peak_rms)

    def __init__(self, cfg) -> None:  # noqa: ANN001
        super().__init__()
        self._cfg = cfg
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._captures: list[object] = []

    def start(self, seconds: float = 3.0) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, args=(float(seconds),), daemon=True, name="cyctitles-input-test"
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None

    def _run(self, seconds: float) -> None:
        q: "queue.Queue[np.ndarray]" = queue.Queue()
        captures: list[object] = []
        peak = 0.0
        try:
            source = getattr(self._cfg, "audio_source", "mic")
            if source in ("mic", "both"):
                captures.append(AudioCapture(_parse_index(self._cfg.device_id), q))
            if source in ("loopback", "both"):
                captures.append(LoopbackCapture(self._cfg.loopback_device_id, q))
            if not captures:
                captures.append(AudioCapture(None, q))

            self._captures = captures
            for capture in captures:
                capture.start()  # type: ignore[attr-defined]

            deadline = time.monotonic() + seconds
            while not self._stop.is_set() and time.monotonic() < deadline:
                try:
                    frame = q.get(timeout=0.2)
                except queue.Empty:
                    continue
                rms = float(np.sqrt(np.mean(np.square(frame, dtype=np.float32))))
                peak = max(peak, rms)
                self.level.emit(rms)
            self.finished.emit(peak > 0.01, peak)
        except Exception:  # noqa: BLE001
            self.finished.emit(False, peak)
        finally:
            for capture in captures:
                try:
                    capture.stop()  # type: ignore[attr-defined]
                except Exception:  # noqa: BLE001
                    pass
            self._captures = []
            self._thread = None
