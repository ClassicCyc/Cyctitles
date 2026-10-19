"""Windows text injection for the dictation output mode.

The recognised (optionally translated) text can be delivered to whatever window
has focus in two ways:

* :func:`paste_text` — put the text on the clipboard and send ``Ctrl+V``. This is
  the default because it is fast and handles every character/script.
* :func:`type_text` — synthesize the individual characters with ``SendInput`` and
  ``KEYEVENTF_UNICODE``.

Both are no-ops on non-Windows platforms.
"""

from __future__ import annotations

import sys
import time

_IS_WIN = sys.platform == "win32"

if _IS_WIN:
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    _INPUT_KEYBOARD = 1
    _KEYEVENTF_KEYUP = 0x0002
    _KEYEVENTF_UNICODE = 0x0004
    _VK_CONTROL = 0x11
    _VK_V = 0x56
    _VK_RETURN = 0x0D
    _CF_UNICODETEXT = 13
    _GMEM_MOVEABLE = 0x0002

    class _MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
        ]

    class _KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
        ]

    class _HARDWAREINPUT(ctypes.Structure):
        _fields_ = [
            ("uMsg", wintypes.DWORD),
            ("wParamL", wintypes.WORD),
            ("wParamH", wintypes.WORD),
        ]

    class _INPUT_UNION(ctypes.Union):
        # Every member must be present so sizeof(INPUT) matches what Windows
        # expects (the mouse struct is the largest -> 40 bytes on x64).
        _fields_ = [
            ("mi", _MOUSEINPUT),
            ("ki", _KEYBDINPUT),
            ("hi", _HARDWAREINPUT),
        ]

    class _INPUT(ctypes.Structure):
        _anonymous_ = ("u",)
        _fields_ = [("type", wintypes.DWORD), ("u", _INPUT_UNION)]

    _user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(_INPUT), ctypes.c_int]
    _user32.SendInput.restype = wintypes.UINT

    def _send_input(*inputs: "_INPUT") -> bool:
        count = len(inputs)
        array = (_INPUT * count)(*inputs)
        sent = _user32.SendInput(count, array, ctypes.sizeof(_INPUT))
        return sent == count

    def _key_input(vk: int, scan: int, flags: int) -> _INPUT:
        item = _INPUT(type=_INPUT_KEYBOARD)
        item.ki = _KEYBDINPUT(wintypes.WORD(vk), wintypes.WORD(scan), flags, 0, None)
        return item

    def _send_unicode_char(ch: str) -> bool:
        code = ord(ch)
        if code > 0xFFFF:
            code -= 0x10000
            units = [0xD800 + (code >> 10), 0xDC00 + (code & 0x3FF)]
        else:
            units = [code]
        ok = True
        for unit in units:
            ok = _send_input(
                _key_input(0, unit, _KEYEVENTF_UNICODE),
                _key_input(0, unit, _KEYEVENTF_UNICODE | _KEYEVENTF_KEYUP),
            ) and ok
        return ok

    def _send_ctrl_v() -> bool:
        return _send_input(
            _key_input(_VK_CONTROL, 0, 0),
            _key_input(_VK_V, 0, 0),
            _key_input(_VK_V, 0, _KEYEVENTF_KEYUP),
            _key_input(_VK_CONTROL, 0, _KEYEVENTF_KEYUP),
        )

    _user32.OpenClipboard.argtypes = [wintypes.HWND]
    _user32.OpenClipboard.restype = wintypes.BOOL
    _user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    _user32.SetClipboardData.restype = wintypes.HANDLE
    _kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    _kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    _kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    _kernel32.GlobalLock.restype = wintypes.LPVOID
    _kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    _kernel32.GlobalUnlock.restype = wintypes.BOOL

    def _set_clipboard(text: str) -> bool:
        data = text.encode("utf-16-le") + b"\x00\x00"
        for _ in range(10):
            if _user32.OpenClipboard(None):
                break
            time.sleep(0.02)
        else:
            return False
        try:
            _user32.EmptyClipboard()
            handle = _kernel32.GlobalAlloc(_GMEM_MOVEABLE, len(data))
            if not handle:
                return False
            ptr = _kernel32.GlobalLock(handle)
            if not ptr:
                return False
            ctypes.memmove(ptr, data, len(data))
            _kernel32.GlobalUnlock(handle)
            if not _user32.SetClipboardData(_CF_UNICODETEXT, handle):
                return False
            # Ownership of the handle has been transferred to the clipboard; do
            # not free it here.
            return True
        finally:
            _user32.CloseClipboard()


def available() -> bool:
    """Whether text injection is supported on this platform."""
    return _IS_WIN


def type_text(text: str, delay_ms: int = 0) -> bool:
    """Type ``text`` into the focused window using unicode keystrokes.

    ``delay_ms`` adds a small pause between characters (helps very slow apps).
    """
    if not _IS_WIN or not text:
        return False
    try:
        ok = True
        pause = max(0, delay_ms) / 1000.0
        for ch in text:
            if not _send_unicode_char(ch):
                ok = False
            if pause:
                time.sleep(pause)
        return ok
    except Exception:  # noqa: BLE001
        return False


def press_enter() -> bool:
    """Press the Enter/Return key in the focused window."""
    if not _IS_WIN:
        return False
    try:
        return _send_input(
            _key_input(_VK_RETURN, 0, 0),
            _key_input(_VK_RETURN, 0, _KEYEVENTF_KEYUP),
        )
    except Exception:  # noqa: BLE001
        return False


def paste_text(text: str, restore_after: float = 0.0) -> bool:
    """Put ``text`` on the clipboard and send ``Ctrl+V`` to the focused window."""
    if not _IS_WIN or not text:
        return False
    try:
        if not _set_clipboard(text):
            return type_text(text)
        time.sleep(0.03)
        return _send_ctrl_v()
    except Exception:  # noqa: BLE001
        return False
