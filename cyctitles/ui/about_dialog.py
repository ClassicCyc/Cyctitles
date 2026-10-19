"""About dialog with author links."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout, QWidget

from .. import __version__
from ..i18n import tr


ABOUT_HTML = """
<h2>Cyctitles <span style="font-size:12px;color:gray">v{version}</span></h2>
<p>Real-time, <b>100% offline</b> subtitles and dictation for OBS Studio and any Windows app.</p>
<p>Speech recognition (<b>faster-whisper</b>) and translation (<b>quickmt</b>) run entirely on
your PC after the models are downloaded once — no cloud, no API keys, no monthly cost.</p>
<p>Made by <b>ClassicCyc</b>. Specially for <b>CraftingVegeto</b>.</p>
<p>
  GitHub:&nbsp;<a href="https://github.com/ClassicCyc/Cyctitles">github.com/ClassicCyc/Cyctitles</a><br>
  Telegram:&nbsp;<a href="https://t.me/classiccyc">t.me/classiccyc</a><br>
  YouTube:&nbsp;<a href="https://youtube.com/@ClassicCyc">youtube.com/@ClassicCyc</a>
</p>
<p style="color:gray;font-size:11px">
  License: MIT. Bundled components keep their own licenses (see LICENSE).
</p>
"""


class AboutDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("about_title"))
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)
        label = QLabel(AboutDialog.get_about_html(__version__))
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setOpenExternalLinks(True)
        label.setWordWrap(True)
        layout.addWidget(label)

        buttons = QDialogButtonBox()
        ok = buttons.addButton(tr("btn_close"), QDialogButtonBox.ButtonRole.AcceptRole)
        ok.setDefault(True)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    @classmethod
    def get_about_html(cls, version: str) -> str:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtGui import QIcon
        from ..config import ICON_CYC

        icon_html = ""
        try:
            app = QApplication.instance()
            if app is not None:
                qicon = QIcon(str(ICON_CYC))
                if not qicon.isNull():
                    size = 64
                    pix = qicon.pixmap(size, size)
                    if not pix.isNull():
                        from PySide6.QtCore import QBuffer
                        buf = QBuffer()
                        buf.open(QBuffer.OpenModeFlag.ReadWrite)
                        pix.save(buf, "PNG")
                        import base64
                        icon_html = f'<p style="text-align:center"><img src="data:image/png;base64,{base64.b64encode(buf.data().data()).decode()}" width="{size}" height="{size}" /></p>'
        except Exception:
            pass
        html = ABOUT_HTML.format(version=version)
        return icon_html + html
