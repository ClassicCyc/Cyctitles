"""In-app "How to use" guide."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..config import MODELS_DIR
from ..i18n import tr

_HELP_STYLE_LIGHT = """
  body { color: #1e1e1e; }
  code { background:#f0f0f0; color:#202020; padding:1px 4px; border-radius:3px;
         font-family: Consolas, monospace; font-size: 11px; }
  .muted { color:#808080; font-size:11px; }
  a { color:#0a66c2; }
"""

_HELP_STYLE_DARK = """
  body { color: #e6e6e6; }
  code { background:#2d2d30; color:#e6e6e6; padding:1px 4px; border-radius:3px;
         font-family: Consolas, monospace; font-size: 11px; }
  .muted { color:#9a9a9a; font-size:11px; }
  a { color:#4da3ff; }
"""

_HELP_HTML = """
<style>
  h2 { margin-top: 14px; }
  h3 { margin-top: 12px; margin-bottom: 4px; }
  ol, ul { margin-top: 4px; }
  li { margin-bottom: 3px; }
%%THEME%%
</style>

<h2>How to use Cyctitles <span class="muted">vVERSION</span></h2>
<p>Cyctitles listens to your microphone (or to any input device), transcribes your
speech and can show a translated subtitle in OBS Studio in real time — or type the
text straight into any window (dictation). Everything runs <b>offline</b> on your PC
after the models are downloaded once.</p>

<h3>1. First run — download the models</h3>
<ol>
  <li>Press <b>Start</b>. If the models are missing you will be asked to install them.</li>
  <li>Accept the download (Whisper speech model ≈ 1.5 GB for <i>medium</i>,
      translation model ≈ 300–400 MB). A progress bar shows MB, percentage, speed and
      time remaining. This happens only once.</li>
  <li>When the status shows <b>● Listening</b>, speak — the preview in the window
      updates live.</li>
</ol>
<p class="muted">Small disk on C:? See "Choosing where models are stored" below.</p>

<h3>2. Add the overlay to OBS Studio</h3>
<ol>
  <li>In OBS open a scene, click <b>+</b> in <b>Sources</b> → <b>Browser</b>.</li>
  <li>Paste the URL shown in Cyctitles (default <code>http://127.0.0.1:8765</code>).</li>
  <li>Set <b>Width</b> 1920, <b>Height</b> 1080. The page is transparent by default,
      so the game shows through.</li>
</ol>
<p class="muted">Tip: use <b>Send test subtitle</b> to preview the styling without
talking into the mic.</p>

<h3>3. Styling &amp; text processing</h3>
<p>The main window keeps only the essentials; open <b>Settings → Settings…</b> for the
rest. On the <b>Subtitles</b> tab, changes apply instantly to the OBS overlay:
<b>Position</b> (top/bottom), <b>Max lines</b> (1–3), <b>Font size</b>,
<b>Background opacity</b>, <b>Text color</b> and <b>Box color</b>.</p>
<p>Also on the <b>Subtitles</b> tab you can make captions readable over busy video
(<b>Text outline</b> + <b>Outline color</b>, <b>Font weight</b>) and choose an
<b>Animation</b> (<i>Fade</i>, <i>Slide up</i>, <i>Slide down</i>) with its speed.
For a one-click look, pick a <b>Preset</b>: <i>Default</i>, <i>Minimal</i> (no box,
outline), <i>Bold</i> or <i>Cinematic</i> — then fine-tune the individual controls
(picking any control marks the preset as <i>Custom</i>).</p>
<p>On the <b>Text processing</b> tab you decide how the recognised text is cut before it
is shown or typed: <b>Max words per caption</b>, <b>Split sentences</b>,
<b>Capitalize sentences</b>, <b>Dedupe repeats</b> (hallucination filter),
<b>Drop captions shorter than</b> N characters, and the phrase-cut timing
(<i>cut long speech after</i>, <i>end a phrase after silence of</i>). You can also
enable the optional <b>profanity filter</b> to mask words with asterisks in both the
original and the translation.</p>

<h3>4. Output modes</h3>
<ul>
  <li><b>Subtitles → OBS overlay</b> — the normal stream mode, everything appears in OBS.</li>
  <li><b>Dictation → type into the focused window</b> — press <b>Start</b>, click into any
      text field (chat, notepad, browser…), then speak: Cyctitles <i>types</i> what you
      said into that window. Uncheck <b>Translate before output</b> to type the spoken
      language as-is (English → English), or leave it on to type the translation. If
      typing fails in some app, switch <b>Settings → Text processing → Dictation method</b>
      to <b>Paste</b> (clipboard + Ctrl+V) instead of synthetic keystrokes.</li>
</ul>

<h3>5. Audio source — microphone, system output or both</h3>
<p>By default Cyctitles listens to your <b>microphone</b>. Switch to
<b>System output (loopback)</b> to translate what your PC is <i>playing</i>, or pick
<b>Both (mic + system output)</b> to capture your voice <i>and</i> the computer audio at
the same time (e.g. your voice and the meeting audio on one call).</p>
<p>Under <b>Microphone</b> choose your mic; under <b>Output device</b> choose <i>any</i>
speaker or interface whose loopback should be captured. No virtual audio cable is
required — Cyctitles taps the Windows WASAPI loopback directly. If the system exposes no
output device the loopback options are disabled.</p>

<h3>6. On-screen captions &amp; text-to-speech (calls)</h3>
<p>For video calls and conferences (no OBS needed) enable:</p>
<ul>
  <li><b>Show a caption window on this screen</b> — a small always-on-top, click-through
      caption strip on your own screen. It hides itself after the same delay as the OBS
      overlay.</li>
  <li><b>Speak the translated text out loud</b> — reads the translation through the
      Windows system voice (text-to-speech).</li>
</ul>

<h3>7. Languages &amp; translation models</h3>
<p>Pick the spoken language and the target language. Cyctitles then shows the
<b>translation route</b> it will use under <b>Translation</b> — e.g.
<i>Russian → Chinese</i>, and it tells you if any part still needs downloading.</p>
<p>The translation registry covers the whole X↔English family (EN↔RU, EN↔ZH, EN↔FR,
EN↔DE, EN↔ES, EN↔JA, EN↔KO, EN↔IT, EN↔PL, EN↔PT, EN↔TR, EN↔AR, EN↔UK, EN↔CS and
many more). When no direct model exists between two non-English languages,
Cyctitles <b>pivots through English</b> automatically (e.g. RU→EN→ZH). Learn or
download any pair in <b>Manage models…</b>.</p>
<p class="muted">Long sentences are handled automatically: a chunk is cut when you pause
(or every 8&nbsp;s during a long monologue), and long lines wrap and shrink to fit.</p>

<h3>8. Appearance — theme &amp; app language</h3>
<p>Open <b>Settings → Appearance</b> to switch the app <b>Theme</b>
(<i>System/Auto</i>, <i>Light</i>, <i>Dark</i>) and the <b>App language</b> of the
interface itself (English, Русский, Українська, Français, Español, 中文, 日本語 and
more). These are saved and restored on the next launch.</p>

<h3>9. Performance mode</h3>
<p>Leave <b>Performance</b> on <b>Auto (GPU preferred)</b> to use your NVIDIA GPU, or pick
<b>Force CPU</b> on a machine without a usable GPU. <b>Compute</b> controls the precision
(int8 / int8_float16 / float16); <b>auto</b> picks the best for your hardware.</p>

<h3>10. Choosing where models are stored</h3>
<p>By default models are downloaded to
<code>%LOCALAPPDATA%\\Cyctitles\\models</code> on your C: drive. %%MODELS_NOTE%%</p>
<p>To store them somewhere else (e.g. another drive):</p>
<ol>
  <li>Open <b>Manage models…</b>.</li>
  <li>Click <b>Change folder…</b> and pick a folder (e.g. <code>D:\\ModelStore</code>).</li>
  <li>When asked, choose <b>Yes</b> to move the models you already downloaded.</li>
</ol>

<h3>11. Using your own models</h3>
<p>In <b>Manage models…</b> → <b>Custom models</b> you can point Cyctitles at model
folders you already have, instead of the built-in ones:</p>
<ul>
  <li><b>Whisper</b> — a CTranslate2 Whisper folder containing <code>model.bin</code>.</li>
  <li><b>Translation</b> — a CTranslate2 folder containing <code>model.bin</code> and
      either <code>src.spm.model</code> + <code>tgt.spm.model</code> or a
      <code>joint.spm.model</code>.</li>
</ul>
<p>Use <b>Clear</b> to go back to the built-in models.</p>

<h3>12. Mute hotkey &amp; system tray</h3>
<ul>
  <li>The global hotkey (default <b>Ctrl+Shift+S</b>) mutes/unmutes output without
      touching the window — the status bar shows <b>● Muted</b>.</li>
  <li>Closing the window keeps Cyctitles running in the <b>system tray</b>. Right-click
      the tray icon for Start/Stop, Mute, Show window and Quit.</li>
</ul>

<h3>13. Troubleshooting</h3>
<ul>
  <li><b>No subtitles in OBS</b> — check the URL matches and the source is visible.</li>
  <li><b>Download fails (SSL/DNS)</b> — a VPN or firewall may block huggingface.co;
      allow it or copy the models folder from another machine.</li>
  <li><b>Slow / wrong device</b> — an NVIDIA GPU with recent drivers is used
      automatically; pick <b>Force CPU</b> if you have no usable GPU, or change
      <b>Compute</b> if the GPU is unstable.</li>
  <li><b>Nothing is typed in Dictation mode</b> — click the target text field first;
      some full-screen games ignore synthetic input.</li>
  <li><b>Diagnostics</b> — run <code>Cyctitles.exe --selftest</code> or read the log at
      <code>%%LOG%%</code>.</li>
</ul>

<h3>Files &amp; folders</h3>
<ul>
  <li>Config: <code>%%CONFIG%%</code></li>
  <li>Models: <code>%%MODELS%%</code></li>
  <li>Log: <code>%%LOG%%</code></li>
</ul>

<p class="muted">
  Made by ClassicCyc · Telegram <a href="https://t.me/classiccyc">t.me/classiccyc</a> ·
  YouTube <a href="https://youtube.com/@ClassicCyc">youtube.com/@ClassicCyc</a>
</p>
"""


def _build_html(current_models_dir: str, dark: bool = False) -> str:
    default_display = r"%LOCALAPPDATA%\Cyctitles\models"
    models_note = "No custom folder is set right now."
    if current_models_dir and Path(current_models_dir) != MODELS_DIR:
        models_note = (
            f"You have set a custom folder: <code>{current_models_dir}</code>."
        )
    theme_css = _HELP_STYLE_DARK if dark else _HELP_STYLE_LIGHT
    return (
        _HELP_HTML.replace("VERSION", __version__)
        .replace("%%THEME%%", theme_css)
        .replace("%%MODELS_NOTE%%", models_note)
        .replace("%%MODELS%%", default_display)
        .replace("%%CONFIG%%", r"%LOCALAPPDATA%\Cyctitles\config.json")
        .replace("%%LOG%%", r"%LOCALAPPDATA%\Cyctitles\cyctitles.log")
    )


class HowToUseDialog(QDialog):
    def __init__(self, current_models_dir: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("menu_howto").replace("&", "").rstrip("…"))
        self.resize(720, 680)

        from ..config import load_config

        try:
            dark = (load_config().theme or "auto").lower() == "dark"
        except Exception:  # noqa: BLE001
            dark = False

        layout = QVBoxLayout(self)
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        if dark:
            browser.setStyleSheet(
                "QTextBrowser { background-color: #252526; color: #e6e6e6; "
                "border: 1px solid #3e3e42; }"
            )
        browser.setHtml(_build_html(current_models_dir, dark=dark))
        layout.addWidget(browser)

        buttons = QDialogButtonBox()
        ok = buttons.addButton(tr("btn_close"), QDialogButtonBox.ButtonRole.AcceptRole)
        ok.setDefault(True)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
