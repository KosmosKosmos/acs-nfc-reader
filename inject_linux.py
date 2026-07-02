"""
Inject-Backend Linux — /dev/uinput (echtes virtuelles HID-Keyboard).

Braucht: pip install evdev  (+ Schreibrecht auf /dev/uinput)

GOTCHA: uinput sendet Scancodes wie eine echte Tastatur. Das resultierende
Zeichen haengt vom Tastaturlayout der GUI-Session ab. Fuer den UID-Zeichensatz
(Hex 0-9 A-F + Trenner : - _ space) ist das auf de/us-Layouts unkritisch, da
diese Tasten an gleicher Position liegen. Exotische Separatoren ggf. anpassen.
"""

from __future__ import annotations

import os
import time

try:
    from evdev import UInput, ecodes as e
except ImportError:  # evdev fehlt -> preflight meldet es
    UInput = None
    e = None


def _char_map():
    """char -> (keycode, needs_shift)"""
    m = {}
    for c in "1234567890":
        m[c] = (getattr(e, f"KEY_{c}"), False)
    for c in "abcdefghijklmnopqrstuvwxyz":
        code = getattr(e, f"KEY_{c.upper()}")
        m[c] = (code, False)
        m[c.upper()] = (code, True)
    m[":"] = (e.KEY_SEMICOLON, True)
    m[";"] = (e.KEY_SEMICOLON, False)
    m["-"] = (e.KEY_MINUS, False)
    m["_"] = (e.KEY_MINUS, True)
    m[" "] = (e.KEY_SPACE, False)
    return m


def preflight() -> str | None:
    if UInput is None:
        return "python-evdev fehlt: pip install evdev"
    if not os.access("/dev/uinput", os.W_OK):
        return (
            "/dev/uinput nicht beschreibbar. Als root starten ODER udev-Regel "
            "setzen und User in Gruppe 'input' aufnehmen (siehe README)."
        )
    return None


def make_injector(cfg):
    if UInput is None:
        raise RuntimeError("python-evdev fehlt: pip install evdev")

    cmap = _char_map()
    keys = {code for code, _ in cmap.values()} | {e.KEY_LEFTSHIFT, e.KEY_ENTER}
    ui = UInput({e.EV_KEY: sorted(keys)}, name="nfc-wedge-kbd")

    def tap(code, shift):
        if shift:
            ui.write(e.EV_KEY, e.KEY_LEFTSHIFT, 1)
        ui.write(e.EV_KEY, code, 1)
        ui.write(e.EV_KEY, code, 0)
        if shift:
            ui.write(e.EV_KEY, e.KEY_LEFTSHIFT, 0)
        ui.syn()

    def inject(text: str) -> None:
        for ch in text:
            mapped = cmap.get(ch)
            if mapped is None:
                continue  # nicht abbildbares Zeichen ueberspringen
            tap(*mapped)
            if cfg.inter_key_delay:
                time.sleep(cfg.inter_key_delay)
        if cfg.append_enter:
            tap(e.KEY_ENTER, False)

    return inject
