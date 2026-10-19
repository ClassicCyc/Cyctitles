"""Speech-to-text via faster-whisper, with automatic device/model selection."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# Whisper hallucination phrases that appear on non-speech audio.
_HALLUCINATION_PHRASES = (
    "thank you for watching",
    "thanks for watching",
    "please subscribe",
    "subscribe to my channel",
    "like and subscribe",
    "see you next time",
    "you",
    "bye",
    ".",
    "..",
    "...",
    "music",
    "♪",
    "！",
    "字幕由 amara.org 社群提供",
    "subtitles by the amara.org community",
)


@dataclass
class GpuInfo:
    name: str
    vram_mb: int
    cc_major: int


@dataclass
class TranscribeResult:
    text: str
    avg_logprob: float
    no_speech_prob: float
    rejected: bool = False
    reason: str = ""


def detect_gpu() -> GpuInfo | None:
    """Query the first NVIDIA GPU via nvidia-smi (no heavyweight deps).

    Returns ``None`` when no NVIDIA GPU is present *or* when the CUDA runtime
    (cuBLAS/cuDNN) cannot be loaded — e.g. a CPU-only ("lite") build without a
    bundled or installer-provided CUDA package. This makes the app fall back to
    CPU automatically instead of failing later.
    """
    try:
        from .cuda_env import cuda_runtime_available

        if not cuda_runtime_available():
            return None
    except Exception:  # noqa: BLE001
        pass
    try:
        out = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,compute_cap",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=6,
            creationflags=_CREATE_NO_WINDOW,
        )
        if out.returncode != 0 or not out.stdout.strip():
            return None
        line = out.stdout.strip().splitlines()[0]
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 3:
            return None
        name, vram, cc = parts[0], parts[1], parts[2]
        return GpuInfo(name=name, vram_mb=int(float(vram)), cc_major=int(float(cc)))
    except Exception:
        return None


def resolve_device_compute(requested_device: str, requested_compute: str, gpu: GpuInfo | None) -> tuple[str, str]:
    """Decide (device, compute_type). Blackwell (sm_120) must use float16."""
    device = requested_device
    if requested_device == "auto":
        device = "cuda" if gpu else "cpu"
    if device != "cuda":
        return "cpu", requested_compute if requested_compute != "auto" else "int8"

    if requested_compute != "auto":
        return "cuda", requested_compute

    if gpu is None:
        return "cpu", "int8"
    # INT8 is broken on Blackwell pre-fix; float16 is the guaranteed path there.
    if gpu.cc_major >= 10:
        return "cuda", "float16"
    if gpu.cc_major >= 7:
        return "cuda", "int8_float16"
    return "cuda", "float16"


def resolve_model(requested_model: str, device: str, gpu: GpuInfo | None) -> str:
    if requested_model != "auto":
        return requested_model
    if device == "cpu":
        return "base"
    vram = gpu.vram_mb if gpu else 0
    if vram >= 10000:
        return "large-v3-turbo"
    if vram >= 6000:
        return "medium"
    return "small"


class Transcriber:
    def __init__(self, model_name: str, device: str, compute_type: str, download_root: Path):
        from .cuda_env import setup_cuda_dlls

        setup_cuda_dlls()
        from faster_whisper import WhisperModel

        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self._model = WhisperModel(
            model_name,
            device=device,
            compute_type=compute_type,
            download_root=str(download_root),
        )

    def transcribe(self, audio: np.ndarray, language: str = "en") -> TranscribeResult:
        lang = None if language == "auto" else language
        segments, _info = self._model.transcribe(
            audio,
            language=lang,
            beam_size=1,
            temperature=0.0,
            condition_on_previous_text=False,
            vad_filter=False,
            no_speech_threshold=0.6,
            log_prob_threshold=-1.5,
            compression_ratio_threshold=2.4,
        )
        texts: list[str] = []
        logprobs: list[float] = []
        no_speech: list[float] = []
        for seg in segments:
            text = seg.text.strip()
            if text:
                texts.append(text)
            logprobs.append(getattr(seg, "avg_logprob", 0.0))
            no_speech.append(getattr(seg, "no_speech_prob", 0.0))

        text = " ".join(texts).strip()
        result = TranscribeResult(
            text=text,
            avg_logprob=min(logprobs) if logprobs else -99.0,
            no_speech_prob=max(no_speech) if no_speech else 1.0,
        )
        self._apply_filters(result)
        return result

    @staticmethod
    def _apply_filters(result: TranscribeResult) -> None:
        text = result.text
        if not text:
            result.rejected = True
            result.reason = "empty"
            return
        # Very short noise blips (one or two characters) are not sentences.
        stripped = text.strip(" .,!?:;-—–\"'()[]♪")
        if len(stripped) <= 1:
            result.rejected = True
            result.reason = "too-short"
            return
        lowered = text.lower().strip(" .!?,\"'")
        if lowered in _HALLUCINATION_PHRASES:
            result.rejected = True
            result.reason = "hallucination-blacklist"
            return
        if result.no_speech_prob > 0.85 and result.avg_logprob < -1.0:
            result.rejected = True
            result.reason = "no-speech"
            return
