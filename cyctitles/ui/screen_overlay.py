"""Frameless, always-on-top on-screen caption window (for video calls)."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import QLabel, QWidget


class ScreenOverlay(QWidget):
    """A small transparent caption strip pinned to the bottom of the screen."""

    def __init__(self, auto_hide_sec: float = 6.0) -> None:
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAutoFillBackground(False)

        self._label = QLabel(self)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setWordWrap(True)
        self._label.setStyleSheet(
            "background: rgba(0,0,0,140); color: white; border-radius:8px; padding:8px 14px;"
        )
        self._label.setMargin(4)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.clear)
        self._auto_hide_sec = auto_hide_sec

        self._position()
        self.hide()

    def _position(self) -> None:
        screen = self.screen() or None
        if screen is None:
            return
        geo = screen.availableGeometry()
        width = int(geo.width() * 0.7)
        height = 120
        x = geo.x() + (geo.width() - width) // 2
        y = geo.y() + geo.height() - height - 60
        self.setGeometry(x, y, width, height)
        self._label.setGeometry(self.rect())

    def show_caption(self, text: str, font_scale: float = 1.0, max_chars: int = 200) -> None:
        if not text:
            self.clear()
            return
        if len(text) > max_chars:
            text = text[: max_chars - 1] + "…"
        font = QFont("Segoe UI", int(20 * font_scale))
        self._label.setFont(font)
        self._label.setText(text)
        self._position()
        self.show()
        self.raise_()
        self._hide_timer.start(int(self._auto_hide_sec * 1000))

    def clear(self) -> None:
        self._hide_timer.stop()
        self._label.clear()
        self.hide()

    def set_auto_hide(self, sec: float) -> None:
        self._auto_hide_sec = sec
