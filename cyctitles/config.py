"""Application configuration: defaults, load/save to %LOCALAPPDATA%/Cyctitles."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

# Keep the HuggingFace hub quiet on Windows (no symlink support / telemetry).
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

APP_NAME = "Cyctitles"
AUTHOR = "ClassicCyc"


def data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if base:
        return Path(base) / APP_NAME
    return Path.home() / f".{APP_NAME.lower()}"


CONFIG_PATH = data_dir() / "config.json"
MODELS_DIR = data_dir() / "models"


def resource_path(relative: str) -> Path:
    """Resolve a bundled resource, both in source and PyInstaller builds."""
    import sys

    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / relative


OVERLAY_DIR = resource_path("overlay")
ICON_ICO = resource_path("cyctitles/assets/cycicon.ico")
ICON_PNG = resource_path("cyctitles/assets/cycicon.png")
ICON_CYC = resource_path("cyctitles/assets/cycicon.ico")

# Languages offered in the UI, derived from the translation-model registry.
from .models import LANGUAGE_NAMES  # noqa: E402  (models has no config import)

_LANG_ORDER = [
    "en", "ru", "zh", "fr", "de", "es", "ja", "ko", "pt", "it",
    "pl", "tr", "ar", "uk", "cs", "bn", "da", "el", "fa", "he",
    "hi", "hu", "id", "is", "lv", "ro", "sv", "th", "ur", "vi",
]
_SOURCE_ORDER = ["auto"] + _LANG_ORDER
_SOURCE_ORDER = [c for c in _SOURCE_ORDER]
# but keep auto first
SOURCE_LANGUAGES = [(LANGUAGE_NAMES[c], c) for c in _LANG_ORDER if c in LANGUAGE_NAMES]
SOURCE_LANGUAGES += [("Auto-detect", "auto")]
TARGET_LANGUAGES = [(LANGUAGE_NAMES[c], c) for c in _LANG_ORDER if c in LANGUAGE_NAMES]

# Whisper model choices; "auto" resolves from detected hardware.
WHISPER_MODELS = ["auto", "tiny", "base", "small", "medium", "large-v3-turbo", "large-v3"]

TRANSLATOR_BACKENDS = ["quickmt"]


@dataclass
class OverlayConfig:
    """Everything the browser overlay needs to render itself."""

    opacity: float = 0.75
    font_scale: float = 1.0
    show_original: bool = False
    original_scale: float = 0.6
    auto_hide_sec: float = 6.0
    font_family: str = "Inter"
    bottom_margin: float = 6.0
    position: str = "bottom"  # "bottom" | "top"
    text_color: str = "#ffffff"
    background: str = "#000000"
    max_lines: int = 2
    # Text legibility over busy video.
    outline_width: float = 0.0  # 0 = off; in em units (e.g. 0.04)
    outline_color: str = "#000000"
    shadow: bool = False
    font_weight: int = 600  # 400 regular / 600 semi-bold
    animation: str = "fade"  # fade | slide-up | slide-down
    animation_duration: float = 0.25
    preset: str = "default"  # default | minimal | bold | cinematic

    def to_payload(self) -> dict:
        return asdict(self)


@dataclass
class Config:
    device_id: str = ""  # sounddevice input device index as str; "" = system default
    src_lang: str = "en"
    tgt_lang: str = "ru"
    whisper_model: str = "auto"
    translator_backend: str = "quickmt"
    translation_model: str = "quickmt-en-ru"  # key in models.TRANSLATION_MODELS
    translate_enabled: bool = True

    # Audio source: "mic" (default) or "loopback" (translate system output).
    audio_source: str = "mic"
    loopback_device_id: str = ""

    # Where the result goes: "overlay" (OBS) or "paste" (dictation into focused window).
    output_mode: str = "overlay"

    # On-screen overlay (frameless always-on-top window for video calls) — independent of OBS.
    screen_overlay_enabled: bool = False

    # Text-to-speech of the (translated) text through the system default voice.
    tts_enabled: bool = False
    tts_rate: int = 0  # SAPI rate: -10..10
    tts_volume: int = 100  # 0..100

    # Storage. Empty strings mean "use the default / built-in choice".
    models_dir: str = ""  # folder for all downloaded models; "" = %LOCALAPPDATA%/Cyctitles/models
    whisper_model_path: str = ""  # optional custom Whisper model folder (overrides the dropdown)
    translation_model_path: str = ""  # optional custom translation model folder

    overlay: OverlayConfig = None  # type: ignore[assignment]

    overlay_port: int = 8765
    hotkey: str = "ctrl+shift+s"

    auto_start: bool = False
    minimize_to_tray: bool = True

    vad_aggressiveness: int = 2
    min_silence_sec: float = 0.55
    min_speech_sec: float = 0.30
    max_chunk_sec: float = 8.0

    # Text post-processing (Settings → Text processing).
    dictation_method: str = "paste"  # "paste" (clipboard + Ctrl+V) | "type"
    dictation_trailing_space: bool = True  # append a space so sentences don't merge
    dictation_enter_after: bool = False  # press Enter after each dictation chunk
    dictation_typing_delay_ms: int = 0  # per-char delay for the "type" method (ms)
    max_words_per_caption: int = 0  # 0 = no limit
    split_sentences: bool = False
    capitalize_sentences: bool = False
    dedupe_repeats: bool = True
    min_caption_chars: int = 1

    # Voice activity detection backend.
    vad_backend: str = "webrtcvad"  # "webrtcvad" | "energy"
    vad_energy_threshold: float = 0.012  # RMS threshold for the "energy" backend

    # Optional profanity filter (asterisks in both the original and translation).
    censor_enabled: bool = False
    censor_words: list[str] = field(default_factory=list)

    # Interface language.
    theme: str = "auto"  # "auto" | "light" | "dark"
    ui_language: str = "en"  # "en" | "ru" | …

    window_geometry: str = ""

    # Performance override.
    device_mode: str = "auto"  # "auto" | "cpu" (force CPU for transcription/translation)
    compute_mode: str = "auto"  # "auto" | "int8" | "float16" | "int8_float16" | "default"

    def __post_init__(self) -> None:
        if self.overlay is None:
            self.overlay = OverlayConfig()


def resolved_models_dir(cfg: Config) -> Path:
    """Where models live for this config (custom folder or the default)."""
    value = getattr(cfg, "models_dir", "")
    if value:
        return Path(value)
    return MODELS_DIR


def load_config(path: Path | None = None) -> Config:
    path = path or CONFIG_PATH
    cfg = Config()
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cfg
        overlay_raw = raw.pop("overlay", None)
        valid = {f.name for f in fields(Config)}
        for key, value in raw.items():
            if key in valid and key != "overlay":
                setattr(cfg, key, value)
        if isinstance(overlay_raw, dict):
            for key, value in overlay_raw.items():
                if hasattr(cfg.overlay, key):
                    setattr(cfg.overlay, key, value)
    return cfg


def save_config(cfg: Config, path: Path | None = None) -> None:
    path = path or CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    data = asdict(cfg)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
