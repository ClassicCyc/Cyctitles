"""Audio capture: device enumeration + 16 kHz mono streams.

Two capture backends are provided:

* :class:`AudioCapture` — a normal input device (microphone) via ``sounddevice``
  (PortAudio).
* :class:`LoopbackCapture` — the WASAPI *loopback* of **any output device**
  (speakers, HDMI, an audio interface's Main out …) via ``soundcard``.

Both deliver fixed 30 ms float32 frames into a queue, which is what the VAD
segmenter expects.
"""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass

import numpy as np
import sounddevice as sd

try:  # soundcard is Windows/macOS/Linux; keep the app usable if it is missing.
    import soundcard as _sc
except Exception:  # noqa: BLE001
    _sc = None

SAMPLE_RATE = 16000
FRAME_MS = 30
FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000  # 480


@dataclass
class DeviceInfo:
    index: int  # ordinal shown in the combo (inputs: sounddevice index)
    name: str
    is_default: bool
    key: str = ""  # value stored in the config (input index / soundcard id)


class _LinearResampler:
    """Small streaming linear resampler (16 kHz target)."""

    def __init__(self, src_rate: int, dst_rate: int = SAMPLE_RATE) -> None:
        self.step = src_rate / dst_rate
        self.phase = 0.0

    def process(self, data: np.ndarray) -> np.ndarray:
        if self.step == 1.0 or len(data) == 0:
            return data.astype(np.float32)
        pos = self.phase
        positions: list[float] = []
        while pos < len(data):
            positions.append(pos)
            pos += self.step
        self.phase = pos - len(data)
        if not positions:
            return np.zeros(0, dtype=np.float32)
        out = np.interp(np.asarray(positions), np.arange(len(data)), data)
        return out.astype(np.float32)


def _hostapi_name(dev, hostapis) -> str:  # noqa: ANN001
    try:
        return hostapis[dev.get("hostapi", -1)].get("name", "")
    except Exception:  # noqa: BLE001
        return ""


def list_input_devices() -> list[DeviceInfo]:
    try:
        default_in = sd.default.device[0]
    except Exception:  # noqa: BLE001
        default_in = None

    try:
        hostapis = sd.query_hostapis()
    except Exception:  # noqa: BLE001
        hostapis = ()

    devices: list[DeviceInfo] = []
    for index, dev in enumerate(sd.query_devices()):
        if dev.get("max_input_channels", 0) <= 0:
            continue
        name = dev.get("name", f"Device {index}")
        if _hostapi_name(dev, hostapis) == "WASAPI":
            name = f"{name} [WASAPI]"
        devices.append(
            DeviceInfo(index=index, name=name, is_default=index == default_in, key=str(index))
        )
    return devices


def output_capture_available() -> bool:
    """Whether we can capture an output device's loopback on this machine."""
    return _sc is not None


def list_output_devices() -> list[DeviceInfo]:
    """Every output (speaker) device, each of which can be captured via loopback."""
    if _sc is None:
        return []
    try:
        default_name = _sc.default_speaker().name
    except Exception:  # noqa: BLE001
        default_name = None
    devices: list[DeviceInfo] = []
    try:
        speakers = _sc.all_speakers()
    except Exception:  # noqa: BLE001
        return []
    for ordinal, speaker in enumerate(speakers):
        devices.append(
            DeviceInfo(
                index=ordinal,
                name=speaker.name,
                is_default=speaker.name == default_name,
                key=speaker.id,
            )
        )
    return devices


def list_loopback_devices() -> list[DeviceInfo]:
    """Output devices that can be captured (WASAPI loopback)."""
    return list_output_devices()


def has_loopback_device() -> bool:
    return bool(list_loopback_devices())


class AudioCapture:
    """Opens an input device and pushes 30 ms mono float32 frames to ``frame_queue``."""

    def __init__(self, device_index: int | None, frame_queue: "queue.Queue[np.ndarray]"):
        self._device_index = device_index
        self._queue = frame_queue
        self._stream: sd.InputStream | None = None
        self._lock = threading.Lock()
        self._native_rate = SAMPLE_RATE
        self._pending = np.zeros(0, dtype=np.float32)
        self._resampler = _LinearResampler(SAMPLE_RATE)

    def _device_default_rate(self) -> int:
        try:
            info = sd.query_devices(self._device_index, "input")
            return int(info["default_samplerate"])
        except Exception:  # noqa: BLE001
            return 48000

    def start(self) -> None:
        with self._lock:
            if self._stream is not None:
                return
            self._pending = np.zeros(0, dtype=np.float32)
            try:
                self._open(SAMPLE_RATE)
            except Exception:  # noqa: BLE001
                # Some devices refuse 16 kHz; capture natively and resample.
                self._native_rate = self._device_default_rate()
                self._resampler = _LinearResampler(self._native_rate)
                self._open(self._native_rate)
            self._stream.start()  # type: ignore[union-attr]

    def _device_channels(self) -> int:
        try:
            info = sd.query_devices(self._device_index, "input")
            return max(1, min(2, int(info["max_input_channels"])))
        except Exception:  # noqa: BLE001
            return 1

    def _open(self, samplerate: int) -> None:
        self._stream = sd.InputStream(
            device=self._device_index,
            channels=self._device_channels(),
            samplerate=samplerate,
            blocksize=0,
            dtype="float32",
            callback=self._callback,
        )

    def _callback(self, indata, frames, time_info, status) -> None:  # noqa: ANN001
        if status:
            print(f"[audio] {status}")
        mono = (
            indata.mean(axis=1).astype(np.float32)
            if indata.shape[1] > 1
            else indata[:, 0].astype(np.float32)
        )
        mono = self._resampler.process(mono)
        _emit_frames(mono, self._pending, self._queue)
        self._pending = _pending_tail(mono)

    def stop(self) -> None:
        with self._lock:
            if self._stream is not None:
                try:
                    self._stream.stop()
                    self._stream.close()
                except Exception:  # noqa: BLE001
                    pass
                self._stream = None


class LoopbackCapture:
    """Captures the WASAPI loopback of an output device via ``soundcard``.

    ``device_id`` is the soundcard id of the speaker; empty = the default output.
    """

    def __init__(
        self,
        device_id: str | None,
        frame_queue: "queue.Queue[np.ndarray]",
        samplerate: int = SAMPLE_RATE,
    ):
        self._device_id = device_id or ""
        self._queue = frame_queue
        self._target_rate = samplerate
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._recorder = None
        self._pending = np.zeros(0, dtype=np.float32)
        self._resampler = _LinearResampler(samplerate)

    def _speaker(self):  # noqa: ANN202
        assert _sc is not None
        if self._device_id:
            try:
                return _sc.get_speaker(self._device_id)
            except Exception:  # noqa: BLE001
                pass
        return _sc.default_speaker()

    def start(self) -> None:
        if _sc is None:
            raise RuntimeError("Output capture is not available (soundcard missing).")
        if self._thread is not None:
            return
        speaker = self._speaker()
        mic = _sc.get_microphone(speaker.id, include_loopback=True)
        channels = max(1, min(2, getattr(mic, "channels", None) or 2))
        recorder = None
        native = 48000
        for rate in (48000, 44100, 16000):
            try:
                recorder = mic.recorder(samplerate=rate, channels=channels)
                recorder.__enter__()
                native = rate
                break
            except Exception:  # noqa: BLE001
                recorder = None
                continue
        if recorder is None:
            raise RuntimeError(f"Could not open loopback capture on '{speaker.name}'.")
        self._recorder = recorder
        self._resampler = _LinearResampler(native, self._target_rate)
        self._pending = np.zeros(0, dtype=np.float32)
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="cyctitles-loopback")
        self._thread.start()

    def _loop(self) -> None:
        block = int(self._resampler.step * FRAME_SAMPLES) or FRAME_SAMPLES
        while not self._stop.is_set():
            try:
                data = self._recorder.record(numframes=block)
            except Exception:  # noqa: BLE001
                _ = self._stop.wait(0.1)
                continue
            if data is None or len(data) == 0:
                continue
            mono = (
                data.mean(axis=1).astype(np.float32)
                if getattr(data, "ndim", 1) > 1
                else np.asarray(data, dtype=np.float32).reshape(-1)
            )
            mono = self._resampler.process(mono)
            _emit_frames(mono, self._pending, self._queue)
            self._pending = _pending_tail(mono)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        if self._recorder is not None:
            try:
                self._recorder.__exit__(None, None, None)
            except Exception:  # noqa: BLE001
                pass
            self._recorder = None


def _emit_frames(mono: np.ndarray, pending: np.ndarray, out: "queue.Queue[np.ndarray]") -> None:
    data = np.concatenate((pending, mono)) if len(pending) else mono
    usable = (len(data) // FRAME_SAMPLES) * FRAME_SAMPLES
    for start in range(0, usable, FRAME_SAMPLES):
        out.put(data[start : start + FRAME_SAMPLES].copy())


def _pending_tail(mono: np.ndarray) -> np.ndarray:
    usable = (len(mono) // FRAME_SAMPLES) * FRAME_SAMPLES
    return mono[usable:].copy()
