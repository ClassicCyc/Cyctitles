"""Post-processing of recognised / translated text.

Turns a raw translation into the caption segment(s) that are shown or typed.
Everything is driven by the ``Config`` so the user can tune it in Settings.
"""

from __future__ import annotations

import re

_WS = re.compile(r"\s+")
_SENTENCE_END = re.compile(r"(?<=[.!?。！？…])\s+")
_REPEAT = re.compile(r"\b(\w+(?:\s+\w+){0,3})(?:\s+\1\b)+", re.IGNORECASE)


def normalize_whitespace(text: str) -> str:
    return _WS.sub(" ", text).strip()


def dedupe_repeats(text: str) -> str:
    """Collapse immediately repeated words/phrases (common Whisper loops)."""
    previous = None
    current = text
    for _ in range(3):
        previous = current
        current = _REPEAT.sub(r"\1", current)
        if current == previous:
            break
    return current


def split_sentences(text: str) -> list[str]:
    """Split on sentence-ending punctuation, keeping the punctuation."""
    parts = [p.strip() for p in _SENTENCE_END.split(text) if p.strip()]
    return parts or ([text.strip()] if text.strip() else [])


def _cap_words(text: str, max_words: int) -> list[str]:
    if max_words <= 0:
        return [text]
    words = text.split()
    if len(words) <= max_words:
        return [text]
    return [" ".join(words[i : i + max_words]) for i in range(0, len(words), max_words)]


def _capitalize(text: str) -> str:
    if not text:
        return text
    return text[0].upper() + text[1:]


# --- profanity filter ---------------------------------------------------------
def _mask_word(word: str) -> str:
    return "*" * max(1, len(word))


def censor_text(text: str, words: list[str]) -> str:
    """Replace any listed word with asterisks (case-insensitive, whole word).

    Works for space-separated scripts via word boundaries and for scripts
    without spaces (Chinese, Thai…) via a plain substring replace.
    """
    if not text or not words:
        return text
    for word in words:
        w = (word or "").strip()
        if not w:
            continue
        masked = _mask_word(w)
        # Space-separated scripts (Latin, Cyrillic): whole-word match only.
        if re.search(r"[0-9A-Za-zА-Яа-я]", w):
            pattern = re.compile(
                r"(?<![0-9A-Za-zА-Яа-я])" + re.escape(w) + r"(?![0-9A-Za-zА-Яа-я])",
                re.IGNORECASE,
            )
            text = pattern.sub(masked, text)
        else:
            # Scripts without word spaces (Chinese, Thai…): plain replace.
            text = text.replace(w, masked)
    return text


def apply_censor(text: str, cfg) -> str:
    """Mask profanity when the filter is enabled in ``cfg``."""
    if not getattr(cfg, "censor_enabled", False):
        return text
    words = getattr(cfg, "censor_words", None) or []
    return censor_text(text, words)


def segments(text: str, cfg) -> list[str]:
    """Split ``text`` into the caption segments to show/type, per ``cfg``."""
    text = normalize_whitespace(text)
    if getattr(cfg, "dedupe_repeats", True):
        text = normalize_whitespace(dedupe_repeats(text))
    if not text:
        return []

    if getattr(cfg, "split_sentences", False):
        parts = split_sentences(text)
    else:
        parts = [text]

    max_words = int(getattr(cfg, "max_words_per_caption", 0) or 0)
    expanded: list[str] = []
    for part in parts:
        expanded.extend(_cap_words(part, max_words))

    min_chars = int(getattr(cfg, "min_caption_chars", 1) or 0)
    kept = [p for p in expanded if len(p) >= min_chars]
    if not kept:
        kept = expanded

    if getattr(cfg, "capitalize_sentences", False):
        kept = [_capitalize(p) for p in kept]
    return kept


def process(text: str, cfg) -> str:
    """Single-string variant (used for dictation, where one paste is best)."""
    return " ".join(segments(text, cfg))
