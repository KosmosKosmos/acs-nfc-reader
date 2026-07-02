#!/usr/bin/env python3
"""
NFC Keyboard-Wedge — macOS-Prototyp
===================================

Liest die UID von NFC-Tags über den ACR122U (PC/SC) und "tippt" sie als
Tastatureingabe in das gerade fokussierte Feld — plus optionalem Enter.

Der ACR122U ist KEINE HID-Tastatur. Wir emulieren das Verhalten:
    Tag auflegen  ->  UID via PC/SC lesen  ->  Keystrokes ins OS injizieren.

Plattform-Aufteilung (nur die Inject-Schicht unten unterscheidet sich):
    - macOS  : Quartz CGEvent          (diese Datei)
    - Linux  : /dev/uinput (echtes HID)  -> wedge_linux.py
    - Windows: SendInput                 -> wedge_windows.py
Die PC/SC-Leseschicht (read_uid / CardObserver) ist auf allen dreien gleich.

Setup:
    python3 -m venv .venv && source .venv/bin/activate
    pip install pyscard pyobjc-framework-Quartz pyobjc-framework-ApplicationServices

Berechtigung (einmalig):
    System-Einstellungen -> Datenschutz & Sicherheit -> Bedienungshilfen
    -> Terminal/iTerm (bzw. das ausführende Programm) aktivieren.
    Ohne diese Freigabe werden die Tastenevents still verworfen.
"""

from __future__ import annotations

import sys
import time

# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------
UID_UPPERCASE = True      # AA:BB vs aa:bb
UID_SEPARATOR = ""        # z.B. ":" fuer AA:BB:CC:DD, "" fuer AABBCCDD
APPEND_ENTER = True       # Enter nach der UID (typisches Wedge-Verhalten)
REVERSE_BYTES = False     # manche Systeme erwarten LSB-first
INTER_KEY_DELAY = 0.004   # Sekunden zwischen Tasten (0 = so schnell wie moeglich)


# ---------------------------------------------------------------------------
# PC/SC — UID lesen (plattformunabhaengig, teilen sich mac/linux/windows)
# ---------------------------------------------------------------------------
from smartcard.CardMonitoring import CardMonitor, CardObserver
from smartcard.util import toHexString

# Pseudo-APDU des PC/SC-Standards: "Get Data" -> liefert die Karten-UID.
# Funktioniert beim ACR122U (PN532) fuer Mifare Classic/Ultralight/NTAG/DESFire.
GET_UID_APDU = [0xFF, 0xCA, 0x00, 0x00, 0x00]


def read_uid(connection) -> str | None:
    """UID der aktuell verbundenen Karte lesen und formatiert zurueckgeben."""
    data, sw1, sw2 = connection.transmit(GET_UID_APDU)
    if (sw1, sw2) != (0x90, 0x00):
        # 0x63 0x00 o.ae. -> Karte nicht lesbar / kein UID-Typ
        return None
    if REVERSE_BYTES:
        data = list(reversed(data))
    parts = [f"{b:02X}" if UID_UPPERCASE else f"{b:02x}" for b in data]
    return UID_SEPARATOR.join(parts)


# ---------------------------------------------------------------------------
# Inject-Schicht — macOS (Quartz CGEvent)
# ---------------------------------------------------------------------------
from Quartz import (
    CGEventCreateKeyboardEvent,
    CGEventKeyboardSetUnicodeString,
    CGEventPost,
    kCGHIDEventTap,
)
from ApplicationServices import AXIsProcessTrusted

_KEY_RETURN = 0x24  # macOS virtueller Keycode fuer Return


def _post_char(ch: str) -> None:
    """Ein Unicode-Zeichen tippen — layout-unabhaengig (kein Keycode-Mapping)."""
    for keydown in (True, False):
        ev = CGEventCreateKeyboardEvent(None, 0, keydown)
        CGEventKeyboardSetUnicodeString(ev, len(ch), ch)
        CGEventPost(kCGHIDEventTap, ev)


def _post_return() -> None:
    for keydown in (True, False):
        ev = CGEventCreateKeyboardEvent(None, _KEY_RETURN, keydown)
        CGEventPost(kCGHIDEventTap, ev)


def type_text(text: str) -> None:
    for ch in text:
        _post_char(ch)
        if INTER_KEY_DELAY:
            time.sleep(INTER_KEY_DELAY)
    if APPEND_ENTER:
        _post_return()


# ---------------------------------------------------------------------------
# Karten-Observer: reagiert auf Auflegen/Abnehmen
# ---------------------------------------------------------------------------
class WedgeObserver(CardObserver):
    def update(self, observable, actions):
        added, _removed = actions
        for card in added:
            try:
                conn = card.createConnection()
                conn.connect()
                uid = read_uid(conn)
                conn.disconnect()
            except Exception as exc:  # Reader kurz nicht verfuegbar o.ae.
                print(f"[warn] Lesefehler: {exc}", file=sys.stderr)
                continue
            if uid is None:
                print("[warn] Karte erkannt, aber keine UID lesbar")
                continue
            print(f"[uid ] {uid}")
            type_text(uid)


def main() -> int:
    if not AXIsProcessTrusted():
        print(
            "[!] Keine Bedienungshilfen-Berechtigung.\n"
            "    System-Einstellungen -> Datenschutz & Sicherheit -> "
            "Bedienungshilfen -> Terminal aktivieren.\n"
            "    (Tastenevents werden sonst still verworfen.)",
            file=sys.stderr,
        )
        # Nicht abbrechen — Lesen funktioniert, nur das Tippen nicht.

    monitor = CardMonitor()
    observer = WedgeObserver()
    monitor.addObserver(observer)
    print("NFC Keyboard-Wedge laeuft. Tag auflegen. Beenden mit Strg+C.")
    try:
        while True:
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("\nbeendet.")
    finally:
        monitor.deleteObserver(observer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
