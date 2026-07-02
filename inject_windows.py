"""
Inject-Backend Windows — SendInput mit KEYEVENTF_UNICODE.

Layout-unabhaengig (sendet Unicode-Codepoints, analog zum mac-Trick).
Keine externen Abhaengigkeiten — reines ctypes.

GOTCHA: SendInput erreicht nur den interaktiven Desktop der eigenen Session.
Ein echter Windows-Dienst laeuft in Session 0 und kann NICHT tippen. Daher als
Autostart-Task in der User-Session betreiben, nicht als Session-0-Service.
"""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

ULONG_PTR = wintypes.WPARAM

INPUT_KEYBOARD = 1
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_KEYUP = 0x0002
VK_RETURN = 0x0D


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class _INPUTunion(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTunion)]


def preflight() -> str | None:
    # Session-0-Isolation laesst sich nicht zuverlaessig detektieren -> siehe README.
    return None


def _send(inp: INPUT) -> None:
    ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def _unicode_event(ch: str, keyup: bool) -> INPUT:
    flags = KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if keyup else 0)
    ki = KEYBDINPUT(0, ord(ch), flags, 0, 0)
    return INPUT(INPUT_KEYBOARD, _INPUTunion(ki=ki))


def _vk_event(vk: int, keyup: bool) -> INPUT:
    flags = KEYEVENTF_KEYUP if keyup else 0
    ki = KEYBDINPUT(vk, 0, flags, 0, 0)
    return INPUT(INPUT_KEYBOARD, _INPUTunion(ki=ki))


def make_injector(cfg):
    def inject(text: str) -> None:
        for ch in text:
            _send(_unicode_event(ch, False))
            _send(_unicode_event(ch, True))
            if cfg.inter_key_delay:
                time.sleep(cfg.inter_key_delay)
        if cfg.append_enter:
            _send(_vk_event(VK_RETURN, False))
            _send(_vk_event(VK_RETURN, True))

    return inject
