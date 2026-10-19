"""Light/dark theme for PySide6 app."""
from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


def _dark_palette() -> QPalette:
    p = QPalette()
    base = QColor("#1e1e1e")
    alt = QColor("#2d2d2d")
    text = QColor("#e6e6e6")
    accent = QColor("#264f78")
    p.setColor(QPalette.ColorRole.Window, base)
    p.setColor(QPalette.ColorRole.WindowText, text)
    p.setColor(QPalette.ColorRole.Base, QColor("#252526"))
    p.setColor(QPalette.ColorRole.AlternateBase, alt)
    p.setColor(QPalette.ColorRole.ToolTipBase, alt)
    p.setColor(QPalette.ColorRole.ToolTipText, text)
    p.setColor(QPalette.ColorRole.Text, text)
    p.setColor(QPalette.ColorRole.Button, QColor("#2d2d30"))
    p.setColor(QPalette.ColorRole.ButtonText, text)
    p.setColor(QPalette.ColorRole.BrightText, QColor("#ff5555"))
    p.setColor(QPalette.ColorRole.Link, QColor("#4da3ff"))
    p.setColor(QPalette.ColorRole.Highlight, accent)
    p.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    p.setColor(QPalette.ColorRole.PlaceholderText, QColor("#9a9a9a"))
    return p


def _qss_dark() -> str:
    return """
QWidget {
    color: #e6e6e6;
}
QMainWindow, QDialog, QWidget#qt_scrollarea_viewport {
    background-color: #1e1e1e;
}
QPushButton {
    background-color: #2d2d30;
    border: 1px solid #3e3e42;
    padding: 4px 8px;
    border-radius: 4px;
}
QPushButton:hover { background-color: #3e3e42; }
QPushButton:pressed { background-color: #252526; }
QLineEdit, QComboBox, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox {
    background-color: #252526;
    color: #e6e6e6;
    border: 1px solid #3e3e42;
    padding: 2px;
    border-radius: 3px;
}
QTextBrowser, QTextEdit, QPlainTextEdit {
    background-color: #252526;
    color: #e6e6e6;
    border: 1px solid #3e3e42;
}
QComboBox QAbstractItemView {
    background-color: #252526;
    color: #e6e6e6;
    selection-background-color: #264f78;
}
QTableWidget, QTableView {
    background-color: #252526;
    color: #e6e6e6;
    gridline-color: #3e3e42;
    selection-background-color: #264f78;
}
QHeaderView::section {
    background-color: #2d2d30;
    color: #e6e6e6;
    padding: 4px;
    border: 1px solid #3e3e42;
}
QTabWidget::pane {
    background-color: #1e1e1e;
    border: 1px solid #3e3e42;
}
QTabBar {
    background-color: #1e1e1e;
}
QTabBar::tab {
    background-color: #2d2d30;
    color: #e6e6e6;
    border: 1px solid #3e3e42;
    padding: 6px 12px;
    border-bottom: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}
QTabBar::tab:selected {
    background-color: #1e1e1e;
    color: #ffffff;
}
QTabBar::tab:hover:!selected {
    background-color: #3e3e42;
}
QGroupBox {
    border: 1px solid #3e3e42;
    border-radius: 4px;
    margin-top: 8px;
    padding-top: 6px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 3px;
    color: #e6e6e6;
}
QCheckBox, QRadioButton, QLabel {
    background: transparent;
}
QScrollBar:vertical, QScrollBar:horizontal {
    background: #1e1e1e;
    border: none;
}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background: #3e3e42;
    border-radius: 4px;
    min-height: 24px;
    min-width: 24px;
}
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QMenuBar {
    background-color: #1e1e1e;
    color: #e6e6e6;
}
QMenuBar::item:selected { background: #264f78; }
QMenu {
    background-color: #252526;
    color: #e6e6e6;
    border: 1px solid #3e3e42;
}
QMenu::item:selected { background: #264f78; }
QProgressBar {
    background-color: #252526;
    color: #e6e6e6;
    border: 1px solid #3e3e42;
    border-radius: 3px;
    text-align: center;
}
QProgressBar::chunk {
    background-color: #264f78;
    border-radius: 3px;
}
QStatusBar {
    background-color: #1e1e1e;
    color: #e6e6e6;
}
QToolTip {
    background-color: #2d2d2d;
    color: #e6e6e6;
    border: 1px solid #3e3e42;
}
"""


def apply_theme(name: str) -> None:
    app = QApplication.instance()
    if app is None:
        return
    name = (name or "auto").lower()
    if name == "dark":
        app.setPalette(_dark_palette())
        app.setStyleSheet(_qss_dark())
    elif name == "light":
        app.setStyleSheet("")
        app.setPalette(app.style().standardPalette())
    else:  # auto - keep light as safe default
        app.setStyleSheet("")
        app.setPalette(app.style().standardPalette())
