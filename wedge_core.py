"""
NFC Keyboard-Wedge — plattformunabhaengiger Kern
=================================================

Enthaelt alles, was mac/Linux/Windows teilen:
  - Config
  - UID-Formatierung
  - PC/SC-Lesen (FF CA 00 00 00)
  - Card-Observer + Run-Loop

Die eigentliche Tasten-Injektion kommt aus einem plattformspezifischen
Backend (inject_macos / inject_linux / inject_windows) und wird als
Callable `inject(text: str)` an run() uebergeben.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass

from smartcard.CardMonitoring import CardMonitor, CardObserver
from smartcard.ReaderMonitoring import ReaderMonitor, ReaderObserver

# PC/SC-Standard-Pseudo-APDU "Get Data" -> Karten-UID (PN532 / ACR122U).
GET_UID_APDU = [0xFF, 0xCA, 0x00, 0x00, 0x00]


@dataclass
class Config:
    uppercase: bool = True       # AABB vs aabb
    separator: str = ""          # z.B. ":" -> AA:BB:CC:DD
    append_enter: bool = True    # Enter nach der UID
    reverse_bytes: bool = False  # LSB-first fuer Altsysteme
    inter_key_delay: float = 0.004  # Sekunden zwischen Tasten


def format_uid(data, cfg: Config) -> str:
    if cfg.reverse_bytes:
        data = list(reversed(data))
    fmt = "{:02X}" if cfg.uppercase else "{:02x}"
    return cfg.separator.join(fmt.format(b) for b in data)


def read_uid(connection, cfg: Config) -> str | None:
    data, sw1, sw2 = connection.transmit(GET_UID_APDU)
    if (sw1, sw2) != (0x90, 0x00):
        return None
    return format_uid(data, cfg)


class _Observer(CardObserver):
    def __init__(self, cfg: Config, inject):
        self.cfg = cfg
        self.inject = inject

    def update(self, observable, actions):
        added, _removed = actions
        for card in added:
            try:
                conn = card.createConnection()
                conn.connect()
                uid = read_uid(conn, self.cfg)
                conn.disconnect()
            except Exception as exc:
                print(f"[warn] Lesefehler: {exc}", file=sys.stderr)
                continue
            if uid is None:
                print("[warn] Karte erkannt, keine UID lesbar", file=sys.stderr)
                continue
            print(f"[uid ] {uid}")
            self.inject(uid)


class _ReaderLog(ReaderObserver):
    """Loggt Ein-/Ausstecken der Reader (Hotplug-Feedback fuer den User).

    Rein informativ: der CardMonitor ueberwacht ohnehin alle jeweils
    angeschlossenen Reader, auch solche, die erst nach Dienststart kommen.
    """

    def update(self, observable, actions):
        added, removed = actions
        for r in added:
            print(f"[rdr ] + angeschlossen: {r}")
        for r in removed:
            print(f"[rdr ] - entfernt:      {r}")


def run(cfg: Config, inject) -> None:
    """Blockierender Run-Loop. `inject(text)` wird pro erkannter Karte gerufen.

    Zwei Monitore: ReaderMonitor (Hotplug der Geraete) + CardMonitor (Tags).
    Beide sind event-basiert und decken beliebig viele Reader gleichzeitig ab.
    """
    reader_monitor = ReaderMonitor()
    reader_log = _ReaderLog()
    reader_monitor.addObserver(reader_log)

    card_monitor = CardMonitor()
    card_observer = _Observer(cfg, inject)
    card_monitor.addObserver(card_observer)

    print("NFC Keyboard-Wedge laeuft. Reader ein-/abstecken jederzeit moeglich. "
          "Tag auflegen. Strg+C beendet.")
    try:
        while True:
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("\nbeendet.")
    finally:
        card_monitor.deleteObserver(card_observer)
        reader_monitor.deleteObserver(reader_log)
