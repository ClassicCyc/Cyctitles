"""System-wide hotkey via Win32 RegisterHotKey (works without admin rights)."""

from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes
from typing import Callable

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

_VK_NAMES = {
    "space": 0x20,
    "tab": 0x09,
    "enter": 0x0D,
    "return": 0x0D,
    "esc": 0x1B,
    "escape": 0x1B,
    "backspace": 0x08,
    "delete": 0x2E,
    "insert": 0x2D,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
}

_HOTKEY_ID = 0xC1C1


def _vk_for(token: str) -> int | None:
    if len(token) == 1:
        ch = token.upper()
        if ("A" <= ch <= "Z") or ("0" <= ch <= "9"):
            return ord(ch)
    if token.startswith("f") and token[1:].isdigit():
        n = int(token[1:])
        if 1 <= n <= 24:
            return 0x70 + (n - 1)
    return _VK_NAMES.get(token)


def parse_hotkey(spec: str) -> tuple[int, int]:
    """Parse 'ctrl+shift+s' into (modifiers, virtual-key). Raises ValueError."""
    mods = 0
    vk: int | None = None
    for raw in spec.split("+"):
        token = raw.strip().lower()
        if not token:
            continue
        if token in ("ctrl", "control"):
            mods |= MOD_CONTROL
        elif token == "shift":
            mods |= MOD_SHIFT
        elif token == "alt":
            mods |= MOD_ALT
        elif token in ("win", "super", "cmd", "meta"):
            mods |= MOD_WIN
        else:
            vk = _vk_for(token)
    if vk is None:
        raise ValueError(f"Unsupported hotkey: {spec!r}")
    return mods, vk


class GlobalHotkey(threading.Thread):
    """Registers a system-wide hotkey and calls ``callback`` on each press."""

    def __init__(self, spec: str, callback: Callable[[], None]):
        super().__init__(daemon=True, name="cyctitles-hotkey")
        self._spec = spec
        self._callback = callback
        self.error: str | None = None
        self._mods, self._vk = parse_hotkey(spec)

    def run(self) -> None:
        if not hasattr(ctypes, "windll"):
            self.error = "Global hotkeys are only supported on Windows."
            return
        user32 = ctypes.windll.user32
        if not user32.RegisterHotKey(None, _HOTKEY_ID, self._mods | MOD_NOREPEAT, self._vk):
            self.error = f"Could not register hotkey {self._spec!r} (already used?)."
            return
        msg = wintypes.MSG()
        try:
            while True:
                ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if ret in (0, -1):
                    break
                if msg.message == WM_HOTKEY and msg.wParam == _HOTKEY_ID:
                    try:
                        self._callback()
                    except Exception:
                        pass
        finally:
            user32.UnregisterHotKey(None, _HOTKEY_ID)

    def stop(self) -> None:
        if not hasattr(ctypes, "windll"):
            return
        if self.native_id:
            try:
                ctypes.windll.user32.PostThreadMessageW(self.native_id, WM_QUIT, 0, 0)
            except Exception:
                pass
