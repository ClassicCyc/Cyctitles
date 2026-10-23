"""Model registry: where each model comes from, its size, and whether it is
already downloaded.

Whisper models are cached through huggingface_hub in the standard cache layout
(``models--<org>--<repo>/snapshots/<rev>/``) under
``%LOCALAPPDATA%/Cyctitles/models``. The translation model is stored flat under
``models/quickmt-en-ru``.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

# ``progress(downloaded_bytes, total_bytes)`` — called from the download thread.
ProgressFn = Callable[[int, int], None]


class DownloadCancelled(Exception):
    """Raised from the progress callback to abort an in-flight download."""


# Xet routes downloads through a separate CAS CDN (cas-server.xethub.hf.co),
# which is frequently blocked or extremely slow on some networks (notably RU)
# while the main Hugging Face host works fine. The classic HTTP path uses the
# same host as the website, so prefer it for reliable downloads. Set
# HF_HUB_DISABLE_XET=0 to opt back in to Xet.
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

_DEVNULL = open(os.devnull, "w", encoding="utf-8")

# Hugging Face repositories, mirroring faster_whisper.utils._MODELS.
WHISPER_REPOS: dict[str, str] = {
    "tiny": "Systran/faster-whisper-tiny",
    "base": "Systran/faster-whisper-base",
    "small": "Systran/faster-whisper-small",
    "medium": "Systran/faster-whisper-medium",
    "large-v3": "Systran/faster-whisper-large-v3",
    "large-v3-turbo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
}

# Approximate download sizes (bytes) of the CTranslate2 weights.
WHISPER_SIZES: dict[str, int] = {
    "tiny": 75_000_000,
    "base": 145_000_000,
    "small": 484_000_000,
    "medium": 1_530_000_000,
    "large-v3": 3_090_000_000,
    "large-v3-turbo": 1_620_000_000,
}

# Files that define a complete Whisper download.
WHISPER_REQUIRED_FILE = "model.bin"

QUICKMT_REPO = "quickmt/quickmt-en-ru"
QUICKMT_SIZE = 402_000_000
QUICKMT_DIRNAME = "quickmt-en-ru"
QUICKMT_REQUIRED_FILE = "model.bin"

QUICKMT_IGNORE = [
    "eole-model/*",
    "eole_model/*",
    "pytorch_model/*",
    ".ipynb_checkpoints/*",
    "*.eole.vocab",
    "*.spm.vocab",
]

# Files faster-whisper actually needs (mirrors faster_whisper.utils.download_model).
WHISPER_ALLOW_PATTERNS = [
    "config.json",
    "preprocessor_config.json",
    "model.bin",
    "tokenizer.json",
    "vocabulary.*",
]


def progress_tqdm_class(progress: ProgressFn):
    """Build a tqdm class that reports real byte progress from huggingface_hub.

    ``faster_whisper`` forces ``tqdm_class=disabled_tqdm``, so its downloads show
    no progress at all, and with Xet the destination folder stays empty until the
    very end. Passing this class to ``snapshot_download`` gives us the live
    network byte counter instead.
    """

    from tqdm.auto import tqdm as _tqdm

    lock = threading.Lock()
    bars: dict[int, tuple[int, int]] = {}
    last = {"done": -1, "total": -1, "at": 0.0}

    def _report() -> None:
        with lock:
            done = max((n for n, _ in bars.values()), default=0)
            total = max((t for _, t in bars.values()), default=0)
            if done == last["done"] and total == last["total"]:
                return
            now = time.monotonic()
            if done < total and now - last["at"] < 0.1 and abs(done - last["done"]) < 131072:
                return
            last["done"], last["total"], last["at"] = done, total, now
            try:
                progress(done, total)
            except DownloadCancelled:
                raise
            except Exception:  # noqa: BLE001 - a UI callback must never break a download
                pass

    class _ProgressTqdm(_tqdm):
        def __init__(self, *args, **kwargs):  # noqa: ANN002, ANN003
            kwargs["file"] = _DEVNULL
            kwargs["disable"] = False
            kwargs["mininterval"] = 0.5
            kwargs["miniters"] = 1 << 20
            super().__init__(*args, **kwargs)
            self._track()

        def _track(self) -> None:
            if self.unit != "B":
                return
            with lock:
                bars[id(self)] = (int(self.n or 0), int(self.total or 0))
            _report()

        def update(self, n: int = 1):  # noqa: ANN201
            result = super().update(n)
            self._track()
            return result

        def close(self) -> None:
            # ``close`` also runs from ``tqdm.__del__``: never let a cancellation
            # (or a UI callback error) escape while the GC is collecting.
            try:
                if self.unit == "B":
                    with lock:
                        total = int(self.total or 0)
                        bars[id(self)] = (total or int(self.n or 0), total)
                    _report()
            except Exception:  # noqa: BLE001
                pass
            try:
                super().close()
            except Exception:  # noqa: BLE001
                pass

    return _ProgressTqdm

LANGUAGE_NAMES: dict[str, str] = {
    "en": "English",
    "ru": "Russian",
    "zh": "Chinese",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
    "ja": "Japanese",
    "ko": "Korean",
    "pt": "Portuguese",
    "it": "Italian",
    "pl": "Polish",
    "tr": "Turkish",
    "ar": "Arabic",
    "uk": "Ukrainian",
    "cs": "Czech",
    "bn": "Bengali",
    "da": "Danish",
    "el": "Greek",
    "fa": "Persian",
    "he": "Hebrew",
    "hi": "Hindi",
    "hu": "Hungarian",
    "id": "Indonesian",
    "is": "Icelandic",
    "lv": "Latvian",
    "ro": "Romanian",
    "sv": "Swedish",
    "th": "Thai",
    "ur": "Urdu",
    "vi": "Vietnamese",
}


@dataclass(frozen=True)
class TranslationSpec:
    """A downloadable CTranslate2 quickmt translation model (one language pair)."""

    key: str
    src: str
    tgt: str
    repo_id: str
    size_bytes: int

    @property
    def label(self) -> str:
        src = LANGUAGE_NAMES.get(self.src, self.src.upper())
        tgt = LANGUAGE_NAMES.get(self.tgt, self.tgt.upper())
        return f"{src} → {tgt}"


# quickmt's model zoo: one CTranslate2 + SentencePiece model per language pair.
# Every quickmt model is either X->en or en->X (there are no direct cross pairs
# such as ru->zh; those are served through pivot translation via English).

# Exact download sizes (bytes) of the needed files, measured from the HF repos.
_QUICKMT_SIZES: dict[str, int] = {
    "ja-en": 410_004_153,
    "zh-en": 409_701_170,
    "en-zh": 412_640_484,
    "fr-en": 409_839_689,
    "en-fr": 383_388_468,
    "de-en": 362_710_858,
    "en-de": 362_710_858,
    "ko-en": 362_694_751,
    "en-ko": 362_694_751,
    "en-ar": 363_145_818,
    "ar-en": 410_561_306,
    "en-ja": 403_634_505,
    "it-en": 403_566_349,
    "en-it": 403_566_349,
    "hi-en": 404_064_201,
    "en-hi": 404_064_201,
    "en-es": 403_601_069,
    "es-en": 403_601_069,
    "ru-en": 413_932_149,
    "en-ru": 404_357_590,
    "pt-en": 403_590_246,
    "en-pt": 403_590_246,
    "bn-en": 404_203_830,
    "en-bn": 404_203_830,
    "id-en": 403_547_860,
    "en-id": 403_547_860,
    "fa-en": 410_503_273,
    "en-fa": 403_985_032,
    "vi-en": 403_496_493,
    "en-vi": 403_496_493,
    "tr-en": 403_632_993,
    "en-tr": 403_632_993,
    "ur-en": 403_912_235,
    "en-ur": 403_912_235,
    "en-hu": 403_644_196,
    "hu-en": 403_644_196,
    "th-en": 404_276_535,
    "en-th": 404_276_535,
    "el-en": 808_470_494,
    "en-el": 404_235_247,
    "pl-en": 403_604_461,
    "en-pl": 403_604_461,
    "en-lv": 412_783_548,
    "lv-en": 412_783_548,
    "cs-en": 412_757_970,
    "ro-en": 412_713_854,
    "en-ro": 412_713_854,
    "en-cs": 412_757_970,
    "he-en": 413_304_483,
    "en-he": 413_304_483,
    "da-en": 412_641_734,
    "en-da": 412_641_734,
    "en-sv": 412_656_076,
    "en-is": 412_699_737,
    "sv-en": 412_656_076,
    "is-en": 402_396_775,
    "uk-en": 205_917_157,
    "en-uk": 205_917_157,
}

# Most common pairs first, then the rest alphabetically.
_PRIORITY_PAIRS = [
    "en-ru", "ru-en", "en-zh", "zh-en", "en-fr", "fr-en", "en-de", "de-en",
    "en-es", "es-en", "en-ja", "ja-en", "en-ko", "ko-en", "en-pt", "pt-en",
]


def _spec(src: str, tgt: str, size_bytes: int) -> TranslationSpec:
    key = f"quickmt-{src}-{tgt}"
    return TranslationSpec(key, src, tgt, f"quickmt/{key}", size_bytes)


def _build_translation_models() -> list[TranslationSpec]:
    ordered: list[str] = [p for p in _PRIORITY_PAIRS if p in _QUICKMT_SIZES]
    ordered += sorted(k for k in _QUICKMT_SIZES if k not in _PRIORITY_PAIRS)
    out: list[TranslationSpec] = []
    for pair in ordered:
        src, tgt = pair.split("-")
        out.append(_spec(src, tgt, _QUICKMT_SIZES[pair]))
    return out


TRANSLATION_MODELS: list[TranslationSpec] = _build_translation_models()
TRANSLATION_BY_KEY: dict[str, TranslationSpec] = {s.key: s for s in TRANSLATION_MODELS}
DEFAULT_TRANSLATION_KEY = "quickmt-en-ru"


def direct_translation_key(src: str, tgt: str) -> str | None:
    """The direct model for ``src`` -> ``tgt`` if one exists (else None)."""
    if not src or not tgt or src == tgt or src == "auto":
        return None
    key = f"quickmt-{src}-{tgt}"
    return key if key in TRANSLATION_BY_KEY else None


def find_translation_key(src: str, tgt: str) -> str | None:
    """Direct model key for ``src`` -> ``tgt`` (legacy helper)."""
    return direct_translation_key(src, tgt)


def find_translation_path(src: str, tgt: str) -> list[str]:
    """Ordered model keys to translate ``src`` -> ``tgt``.

    Returns a direct model when available; otherwise falls back to a pivot
    through English (e.g. ru -> zh becomes ru -> en -> zh). Empty when the
    pair cannot be handled at all.
    """
    if src == tgt or src == "auto":
        return []
    direct = direct_translation_key(src, tgt)
    if direct:
        return [direct]
    if src == "en":
        return [k for k in (direct_translation_key("en", tgt),) if k]
    if tgt == "en":
        return [k for k in (direct_translation_key(src, "en"),) if k]
    step1 = direct_translation_key(src, "en")
    step2 = direct_translation_key("en", tgt)
    if step1 and step2:
        return [step1, step2]
    return []


def path_description(keys: list[str]) -> str:
    """Human label for a translation path, e.g. "Russian → English → Chinese"."""
    langs: list[str] = []
    if not keys:
        return "off"
    langs.append(LANGUAGE_NAMES.get(TRANSLATION_BY_KEY[keys[0]].src, keys[0]))
    for key in keys:
        langs.append(LANGUAGE_NAMES.get(TRANSLATION_BY_KEY[key].tgt, key))
    return " → ".join(langs)


def missing_keys_for_path(keys: list[str], models_dir: Path) -> list[str]:
    """Subset of ``keys`` that still need downloading."""
    return [k for k in keys if not is_translation_downloaded(k, models_dir)]


def human_size(num_bytes: int) -> str:
    """Format a byte count compactly (e.g. ``1.5 GB``)."""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}".replace(".0 ", " ")
        size /= 1024
    return f"{size:.1f} GB"


def whisper_cache_dir(models_dir: Path, name: str) -> Path:
    """Directory huggingface_hub uses to cache a Whisper model."""
    repo = WHISPER_REPOS.get(name, name)
    return Path(models_dir) / ("models--" + repo.replace("/", "--"))


def is_whisper_downloaded(name: str, models_dir: Path) -> bool:
    """True if the CTranslate2 weights for ``name`` are present on disk."""
    cache_dir = whisper_cache_dir(models_dir, name)
    snapshots = cache_dir / "snapshots"
    if not snapshots.is_dir():
        # Allow a plain directory layout too (custom repo id / manual install).
        return (cache_dir / WHISPER_REQUIRED_FILE).is_file()
    return any(
        (snapshot / WHISPER_REQUIRED_FILE).is_file()
        for snapshot in snapshots.iterdir()
        if snapshot.is_dir()
    )


def translation_model_dir(key: str, models_dir: Path) -> Path:
    return Path(models_dir) / key


def _has_quickmt_tokenizers(d: Path) -> bool:
    return ((d / "src.spm.model").is_file() and (d / "tgt.spm.model").is_file()) or (
        d / "joint.spm.model"
    ).is_file()


def _has_quickmt_vocab(d: Path) -> bool:
    """CTranslate2 needs the vocabulary JSON next to model.bin.

    Some quickmt models store it as ``source_vocabulary.json`` +
    ``target_vocabulary.json``, others as a single ``shared_vocabulary.json``.
    Without it CTranslate2 raises "Cannot load the target vocabulary".
    """
    return (d / "shared_vocabulary.json").is_file() or (
        (d / "source_vocabulary.json").is_file() and (d / "target_vocabulary.json").is_file()
    )


def is_translation_downloaded(key: str, models_dir: Path) -> bool:
    d = translation_model_dir(key, models_dir)
    return (
        (d / QUICKMT_REQUIRED_FILE).is_file()
        and _has_quickmt_tokenizers(d)
        and _has_quickmt_vocab(d)
    )


def is_quickmt_downloaded(models_dir: Path) -> bool:
    return is_translation_downloaded(DEFAULT_TRANSLATION_KEY, models_dir)


@dataclass
class ModelInfo:
    """Everything the UI needs to describe a single downloadable model."""

    key: str
    kind: str  # "whisper" | "translation"
    label: str
    repo_id: str
    size_bytes: int
    directory: Path
    downloaded: bool

    @property
    def size_text(self) -> str:
        return human_size(self.size_bytes)

    @property
    def url(self) -> str:
        return f"https://huggingface.co/{self.repo_id}"


def whisper_model_info(name: str, models_dir: Path) -> ModelInfo:
    return ModelInfo(
        key=name,
        kind="whisper",
        label=f"Whisper {name}",
        repo_id=WHISPER_REPOS.get(name, name),
        size_bytes=WHISPER_SIZES.get(name, 0),
        directory=whisper_cache_dir(models_dir, name),
        downloaded=is_whisper_downloaded(name, models_dir),
    )


def translation_model_info(key: str, models_dir: Path) -> ModelInfo:
    spec = TRANSLATION_BY_KEY.get(key)
    if spec is None:
        spec = TRANSLATION_BY_KEY[DEFAULT_TRANSLATION_KEY]
    return ModelInfo(
        key=spec.key,
        kind="translation",
        label=f"Translation {spec.label}",
        repo_id=spec.repo_id,
        size_bytes=spec.size_bytes,
        directory=translation_model_dir(spec.key, models_dir),
        downloaded=is_translation_downloaded(spec.key, models_dir),
    )


def quickmt_model_info(models_dir: Path) -> ModelInfo:
    return translation_model_info(DEFAULT_TRANSLATION_KEY, models_dir)


CUSTOM_REPO = "(custom folder)"


def custom_whisper_info(path: str | Path) -> ModelInfo:
    p = Path(path)
    return ModelInfo(
        key=str(p),
        kind="whisper",
        label=f"Whisper (custom: {p.name or p})",
        repo_id=CUSTOM_REPO,
        size_bytes=directory_size(p),
        directory=p,
        downloaded=(p / WHISPER_REQUIRED_FILE).is_file(),
    )


def custom_translation_info(path: str | Path) -> ModelInfo:
    p = Path(path)
    required = (p / QUICKMT_REQUIRED_FILE).is_file() and _has_quickmt_tokenizers(p)
    return ModelInfo(
        key=str(p),
        kind="translation",
        label=f"Translation (custom: {p.name or p})",
        repo_id=CUSTOM_REPO,
        size_bytes=directory_size(p),
        directory=p,
        downloaded=required,
    )


# -- downloads (blocking; run these off the GUI thread) ------------------------
def download_whisper(
    name: str, models_dir: Path, force: bool = False, progress: ProgressFn | None = None
) -> None:
    import shutil

    from huggingface_hub import snapshot_download

    if force:
        shutil.rmtree(whisper_cache_dir(models_dir, name), ignore_errors=True)
    snapshot_download(
        repo_id=WHISPER_REPOS.get(name, name),
        cache_dir=str(models_dir),
        allow_patterns=WHISPER_ALLOW_PATTERNS,
        tqdm_class=progress_tqdm_class(progress) if progress is not None else None,
    )


def download_quickmt(models_dir: Path, progress: ProgressFn | None = None) -> None:
    download_translation(DEFAULT_TRANSLATION_KEY, models_dir, progress=progress)


def download_translation(
    key: str, models_dir: Path, force: bool = False, progress: ProgressFn | None = None
) -> None:
    if force:
        force_download_translation(key, models_dir, progress=progress)
        return
    from .translator import Translator

    Translator._ensure_model(Path(models_dir), key, progress=progress)


def force_download_translation(
    key: str, models_dir: Path, progress: ProgressFn | None = None
) -> None:
    """Re-fetch a translation model from scratch (repair / integrity reset)."""
    from huggingface_hub import snapshot_download

    spec = TRANSLATION_BY_KEY.get(key)
    if spec is None:
        raise ValueError(f"Unknown translation model: {key}")
    model_dir = translation_model_dir(key, models_dir)
    snapshot_download(
        repo_id=spec.repo_id,
        local_dir=str(model_dir),
        ignore_patterns=QUICKMT_IGNORE,
        force_download=True,
        tqdm_class=progress_tqdm_class(progress) if progress is not None else None,
    )


def download_model_info(
    info: ModelInfo,
    models_dir: Path,
    force: bool = False,
    progress: ProgressFn | None = None,
) -> None:
    if info.kind == "whisper":
        download_whisper(info.key, models_dir, force=force, progress=progress)
    else:
        download_translation(info.key, models_dir, force=force, progress=progress)


# -- disk usage / deletion -----------------------------------------------------
def directory_size(path: Path) -> int:
    """Total size on disk of everything under ``path`` (bytes)."""
    total = 0
    path = Path(path)
    if not path.exists():
        return 0
    for item in path.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
            except OSError:
                pass
    return total


def model_disk_usage(info: ModelInfo) -> int:
    return directory_size(info.directory)


def delete_model(info: ModelInfo) -> None:
    """Remove a downloaded model from disk."""
    import shutil

    path = info.directory
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def move_models_dir(old: Path, new: Path) -> int:
    """Move every entry from ``old`` into ``new``. Returns how many moved."""
    import shutil

    old = Path(old)
    new = Path(new)
    if not old.exists() or old.resolve() == new.resolve():
        return 0
    new.mkdir(parents=True, exist_ok=True)
    moved = 0
    for item in old.iterdir():
        if item.name in (".locks", "CACHEDIR.TAG"):
            continue
        dest = new / item.name
        if dest.exists():
            continue
        try:
            shutil.move(str(item), str(dest))
            moved += 1
        except Exception:  # noqa: BLE001
            pass
    return moved


