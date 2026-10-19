"""Voice activity detection and speech segmentation.

Two VAD backends are available:

* ``webrtcvad`` (default) — WebRTC's robust speech detector on 30 ms frames.
* ``energy`` — a dependency-free RMS threshold, useful when the WebRTC
  detector is too aggressive or the input is very clean.

Emits a completed speech chunk (as float32 audio) when the speaker pauses, or
when the chunk grows too long.
"""

from __future__ import annotations

import collections

import numpy as np
import webrtcvad


def frame_rms(frame: np.ndarray) -> float:
    """Root-mean-square level of a float32 audio frame (0…1 for normal audio)."""
    if frame is None or len(frame) == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(frame, dtype=np.float32))))


def level_fraction(rms: float) -> float:
    """Map an RMS value to a 0…1 meter position on a −60…0 dBFS scale."""
    if rms <= 1e-6:
        return 0.0
    db = 20.0 * float(np.log10(rms))
    return max(0.0, min(1.0, (db + 60.0) / 60.0))


class SpeechSegmenter:
    def __init__(
        self,
        aggressiveness: int = 2,
        sample_rate: int = 16000,
        frame_ms: int = 30,
        min_silence_sec: float = 0.55,
        min_speech_sec: float = 0.30,
        max_chunk_sec: float = 8.0,
        preroll_sec: float = 0.25,
        backend: str = "webrtcvad",
        energy_threshold: float = 0.012,
    ):
        self.sample_rate = sample_rate
        self.frame_ms = frame_ms
        self.backend = backend if backend in ("webrtcvad", "energy") else "webrtcvad"
        self._energy_threshold = max(0.0, float(energy_threshold))
        self._vad = webrtcvad.Vad(aggressiveness) if self.backend == "webrtcvad" else None
        frames_per_sec = 1000.0 / frame_ms
        self._min_silence_frames = max(1, int(round(min_silence_sec * frames_per_sec)))
        self._min_speech_frames = max(1, int(round(min_speech_sec * frames_per_sec)))
        self._max_chunk_frames = max(1, int(round(max_chunk_sec * frames_per_sec)))
        self._preroll = collections.deque(maxlen=max(0, int(round(preroll_sec * frames_per_sec))))
        self._buf: list[np.ndarray] = []
        self._speech_frames = 0
        self._silence_frames = 0
        self._in_speech = False

    def _is_speech(self, frame: np.ndarray) -> bool:
        if self.backend == "energy":
            return frame_rms(frame) >= self._energy_threshold
        pcm = (np.clip(frame, -1.0, 1.0) * 32767.0).astype(np.int16).tobytes()
        try:
            return self._vad.is_speech(pcm, self.sample_rate)
        except Exception:
            return False

    def _emit(self, preserve_tail: bool = False) -> np.ndarray:
        chunk = np.concatenate(self._buf) if self._buf else np.zeros(0, dtype=np.float32)
        tail = self._buf[-1:] if (preserve_tail and self._buf) else []
        self._buf = []
        self._speech_frames = 0
        self._silence_frames = 0
        self._in_speech = False
        if preserve_tail:
            self._preroll.clear()
            for f in tail:
                self._preroll.append(f)
        return chunk.astype(np.float32)

    def reset(self) -> None:
        self._buf = []
        self._speech_frames = 0
        self._silence_frames = 0
        self._in_speech = False
        self._preroll.clear()

    def feed(self, frame: np.ndarray) -> np.ndarray | None:
        """Feed one 30 ms frame; return a finished speech chunk when available."""
        speech = self._is_speech(frame)

        if not self._in_speech:
            if speech:
                self._in_speech = True
                self._buf = list(self._preroll) + [frame]
                self._speech_frames = 1
                self._silence_frames = 0
                self._preroll.clear()
            else:
                self._preroll.append(frame)
            return None

        self._buf.append(frame)
        if speech:
            self._speech_frames += 1
            self._silence_frames = 0
        else:
            self._silence_frames += 1

        # Natural end of utterance.
        if self._silence_frames >= self._min_silence_frames:
            if self._speech_frames >= self._min_speech_frames:
                return self._emit()
            self.reset()
            return None

        # Forced cut on a long monologue: keep a small tail as overlap.
        if len(self._buf) >= self._max_chunk_frames:
            if self._speech_frames >= self._min_speech_frames:
                return self._emit(preserve_tail=True)
            self.reset()
            return None

        return None
