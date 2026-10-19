"""Windows text-to-speech via PowerShell System.Speech (no extra Python deps)."""

from __future__ import annotations

import subprocess
import sys
from threading import Lock

_LOCK = Lock()
_PROC: subprocess.Popen | None = None


def _create(text: str, rate: int, volume: int) -> subprocess.Popen:
    ps = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.Rate = {rate}; $s.Volume = {max(0, min(100, volume))}; "
        f"$s.Speak([Console]::In.ReadToEnd())"
    )
    return subprocess.Popen(
        ["powershell", "-NoProfile", "-Command", ps],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def speak(text: str, rate: int = 0, volume: int = 100) -> bool:
    if sys.platform != "win32" or not text:
        return False
    global _PROC
    try:
        with _LOCK:
            if _PROC is not None and _PROC.poll() is None:
                _PROC.kill()
            _PROC = _create(text, rate, volume)
            _PROC.stdin.write(text.encode("utf-8"))
            _PROC.stdin.close()
        return True
    except Exception:  # noqa: BLE001
        return False


def available() -> bool:
    return sys.platform == "win32"


def stop() -> None:
    global _PROC
    with _LOCK:
        if _PROC is not None and _PROC.poll() is None:
            try:
                _PROC.kill()
            except Exception:  # noqa: BLE001
                pass
        _PROC = None
