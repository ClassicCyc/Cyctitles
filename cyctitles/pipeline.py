"""Pipeline orchestrator: audio -> VAD -> whisper -> translation -> overlay."""

from __future__ import annotations

import queue
import threading
import time
import uuid
from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, Signal

from .audio import AudioCapture, LoopbackCapture
from .config import Config, resolved_models_dir
from .models import TRANSLATION_BY_KEY
from .overlay_server import OverlayServer
from .transcriber import Transcriber, detect_gpu, resolve_device_compute, resolve_model
from .translator import Translator, build_translator
from .vad import SpeechSegmenter


def _parse_index(value) -> int | None:
    if value in ("", None):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class _MultiCapture:
    """Tiny wrapper to start/stop several capture objects together."""

    def __init__(self, captures) -> None:  # noqa: ANN001
        self._captures = captures

    def start(self) -> None:
        for cap in self._captures:
            cap.start()

    def stop(self) -> None:
        for cap in self._captures:
            cap.stop()


class Pipeline(QObject):
    status = Signal(str)
    caption = Signal(dict)
    ready = Signal(dict)
    error = Signal(str)
    stopped = Signal()
    level = Signal(float)

    def __init__(self, cfg: Config, overlay: OverlayServer, parent: QObject | None = None):
        super().__init__(parent)
        self.cfg = cfg
        self.overlay = overlay
        self._running = False
        self._muted = False
        self._paste_mode = cfg.output_mode == "paste"
        self._audio_q: "queue.Queue[np.ndarray | None]" = queue.Queue()
        self._stt_q: "queue.Queue[np.ndarray | None]" = queue.Queue()
        self._mt_q: "queue.Queue[str | None]" = queue.Queue()
        self._workers: list[threading.Thread] = []
        self._loader: threading.Thread | None = None
        self._capture: AudioCapture | None = None
        self._transcriber: Transcriber | None = None
        self._translator: Translator | None = None

    # -- control -------------------------------------------------------------
    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._muted = False
        self._loader = threading.Thread(target=self._run, daemon=True, name="cyctitles-loader")
        self._loader.start()

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._capture is not None:
            self._capture.stop()
        for q in (self._audio_q, self._stt_q, self._mt_q):
            q.put(None)
        self.overlay.set_caption(None)

    def set_muted(self, muted: bool) -> None:
        self._muted = muted
        if muted:
            self.overlay.set_caption(None)

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_muted(self) -> bool:
        return self._muted

    # -- main worker ---------------------------------------------------------
    def _run(self) -> None:
        try:
            models_dir = resolved_models_dir(self.cfg)
            custom_whisper = self.cfg.whisper_model_path
            custom_mt = self.cfg.translation_model_path

            self.status.emit("Detecting hardware…")
            gpu = detect_gpu()
            device, compute = resolve_device_compute("auto", "auto", gpu)

            if custom_whisper:
                model = custom_whisper
            else:
                model = resolve_model(self.cfg.whisper_model, device, gpu)
            info = {
                "model": Path(custom_whisper).name if custom_whisper else model,
                "device": device,
                "compute": compute,
                "gpu": gpu.name if gpu else "CPU",
            }

            self.status.emit(
                f"Loading Whisper '{info['model']}' on {device} ({compute}); first run downloads models…"
            )
            try:
                self._transcriber = Transcriber(model, device, compute, models_dir)
            except Exception as exc:  # noqa: BLE001
                if device == "cuda":
                    self.status.emit(f"GPU whisper failed ({exc}); retrying on CPU…")
                    info["device"], info["compute"] = "cpu", "int8"
                    self._transcriber = Transcriber(model, "cpu", "int8", models_dir)
                else:
                    raise

            self.status.emit("Loading translator (first run downloads the model)…")
            info["translation"] = "off"
            if self.cfg.translate_enabled:
                from .models import find_translation_path, path_description

                path = find_translation_path(self.cfg.src_lang, self.cfg.tgt_lang)
                if not path:
                    raise RuntimeError(
                        f"No translation model for {self.cfg.src_lang} → {self.cfg.tgt_lang}."
                    )
                info["translation"] = path_description(path)
                try:
                    self._translator = build_translator(
                        models_dir,
                        path,
                        device=device,
                        model_dir=custom_mt or None,
                    )
                except Exception as exc:  # noqa: BLE001
                    if device == "cuda":
                        self.status.emit(f"GPU translator failed ({exc}); retrying on CPU…")
                        self._translator = build_translator(
                            models_dir,
                            path,
                            device="cpu",
                            model_dir=custom_mt or None,
                        )
                    else:
                        raise
        except Exception as exc:  # noqa: BLE001
            self.error.emit(f"Failed to load models: {exc}")
            self._finish()
            return

        self.ready.emit(info)
        self._start_workers()

        try:
            if self.cfg.audio_source == "both":
                mic = AudioCapture(_parse_index(self.cfg.device_id), self._audio_q)
                loop = LoopbackCapture(self.cfg.loopback_device_id, self._audio_q)
                mic.start()
                loop.start()
                self._capture = _MultiCapture([mic, loop])
            elif self.cfg.audio_source == "loopback":
                self._capture = LoopbackCapture(self.cfg.loopback_device_id, self._audio_q)
                self._capture.start()
            else:
                self._capture = AudioCapture(_parse_index(self.cfg.device_id), self._audio_q)
                self._capture.start()
        except Exception as exc:  # noqa: BLE001
            self.error.emit(f"Audio capture error: {exc}")
            self._finish()
            return

        self.status.emit("Listening")
        try:
            while self._running:
                time.sleep(0.1)
        finally:
            self._finish()

    def _start_workers(self) -> None:
        self._workers = [
            threading.Thread(target=self._vad_loop, daemon=True, name="cyctitles-vad"),
            threading.Thread(target=self._stt_loop, daemon=True, name="cyctitles-stt"),
            threading.Thread(target=self._mt_loop, daemon=True, name="cyctitles-mt"),
        ]
        for worker in self._workers:
            worker.start()

    def _finish(self) -> None:
        self._running = False
        for worker in self._workers:
            worker.join(timeout=2.0)
        self._workers = []
        self.overlay.set_caption(None)
        self.stopped.emit()

    # -- workers -------------------------------------------------------------
    def _vad_loop(self) -> None:
        from .vad import frame_rms

        segmenter = SpeechSegmenter(
            aggressiveness=self.cfg.vad_aggressiveness,
            min_silence_sec=self.cfg.min_silence_sec,
            min_speech_sec=self.cfg.min_speech_sec,
            max_chunk_sec=self.cfg.max_chunk_sec,
            backend=getattr(self.cfg, "vad_backend", "webrtcvad"),
            energy_threshold=getattr(self.cfg, "vad_energy_threshold", 0.012),
        )
        tick = 0
        while True:
            try:
                frame = self._audio_q.get(timeout=0.2)
            except queue.Empty:
                if not self._running:
                    break
                continue
            if frame is None:
                break
            # Live input level for the VU meter (~10 updates per second).
            tick += 1
            if tick % 3 == 0:
                self.level.emit(frame_rms(frame))
            chunk = segmenter.feed(frame)
            if chunk is not None and len(chunk):
                self._stt_q.put(chunk)

    def _stt_loop(self) -> None:
        assert self._transcriber is not None
        while True:
            try:
                chunk = self._stt_q.get(timeout=0.2)
            except queue.Empty:
                if not self._running:
                    break
                continue
            if chunk is None:
                break
            try:
                result = self._transcriber.transcribe(chunk, self.cfg.src_lang)
            except Exception as exc:  # noqa: BLE001
                self.error.emit(f"Transcription error: {exc}")
                continue
            if result.rejected or not result.text:
                continue
            self._mt_q.put(result.text)

    def _mt_loop(self) -> None:
        assert self._translator is not None or not self.cfg.translate_enabled
        while True:
            try:
                text = self._mt_q.get(timeout=0.2)
            except queue.Empty:
                if not self._running:
                    break
                continue
            if text is None:
                break
            try:
                if self.cfg.translate_enabled and self._translator is not None:
                    translated = self._translator.translate([text])[0]
                else:
                    translated = text
            except Exception as exc:  # noqa: BLE001
                self.error.emit(f"Translation error: {exc}")
                continue
            if not translated:
                continue
            if self._muted:
                continue

            segments = self._process_text(translated)
            if not segments:
                continue

            from .textproc import apply_censor

            clean_src = apply_censor(text, self.cfg)
            segments = [apply_censor(s, self.cfg) for s in segments]

            if self._paste_mode:
                from . import inject

                text_out = " ".join(segments)
                if getattr(self.cfg, "dictation_trailing_space", True):
                    text_out = text_out.rstrip() + " "
                method = getattr(self.cfg, "dictation_method", "paste")
                delay = int(getattr(self.cfg, "dictation_typing_delay_ms", 0) or 0)
                if method == "paste":
                    injected = inject.paste_text(text_out)
                else:
                    injected = inject.type_text(text_out, delay_ms=delay)
                if injected and getattr(self.cfg, "dictation_enter_after", False):
                    inject.press_enter()
                if not injected:
                    self.error.emit("Could not type into the focused window.")
                event = {
                    "id": uuid.uuid4().hex,
                    "src": clean_src,
                    "tgt": text_out,
                    "ts": time.time(),
                }
                self.caption.emit(event)
            else:
                for segment in segments:
                    event = {
                        "id": uuid.uuid4().hex,
                        "src": clean_src,
                        "tgt": segment,
                        "ts": time.time(),
                    }
                    self.overlay.set_caption(event)
                    self.caption.emit(event)

    def _process_text(self, text: str) -> list[str]:
        from .textproc import segments

        return segments(text, self.cfg)
