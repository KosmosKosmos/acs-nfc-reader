"""
Inject-Backend macOS — Quartz CGEvent.

Layout-unabhaengig via CGEventKeyboardSetUnicodeString (kein Keycode-Mapping).
Braucht: pip install pyobjc-framework-Quartz pyobjc-framework-ApplicationServices
Berechtigung: Datenschutz & Sicherheit -> Bedienungshilfen -> ausfuehrendes Programm.
"""

from __future__ import annotations

import time

from Quartz import (
    CGEventCreateKeyboardEvent,
    CGEventKeyboardSetUnicodeString,
    CGEventPost,
    kCGHIDEventTap,
)
from ApplicationServices import AXIsProcessTrusted

_KEY_RETURN = 0x24


def preflight() -> str | None:
    if not AXIsProcessTrusted():
        return (
            "Keine Bedienungshilfen-Berechtigung. System-Einstellungen -> "
            "Datenschutz & Sicherheit -> Bedienungshilfen -> ausfuehrendes "
            "Programm aktivieren (Tastenevents werden sonst verworfen)."
        )
    return None


def _post_char(ch: str) -> None:
    for keydown in (True, False):
        ev = CGEventCreateKeyboardEvent(None, 0, keydown)
        CGEventKeyboardSetUnicodeString(ev, len(ch), ch)
        CGEventPost(kCGHIDEventTap, ev)


def _post_return() -> None:
    for keydown in (True, False):
        CGEventPost(kCGHIDEventTap, CGEventCreateKeyboardEvent(None, _KEY_RETURN, keydown))


def make_injector(cfg):
    def inject(text: str) -> None:
        for ch in text:
            _post_char(ch)
            if cfg.inter_key_delay:
                time.sleep(cfg.inter_key_delay)
        if cfg.append_enter:
            _post_return()

    return inject
