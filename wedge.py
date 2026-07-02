#!/usr/bin/env python3
"""
NFC Keyboard-Wedge — einheitlicher Entrypoint.

Waehlt automatisch das passende Inject-Backend anhand der Plattform und
startet den PC/SC-Run-Loop aus wedge_core.

    python wedge.py
"""

from __future__ import annotations

import sys

from wedge_core import Config, run


def _load_backend():
    p = sys.platform
    if p == "darwin":
        import inject_macos as backend
    elif p.startswith("linux"):
        import inject_linux as backend
    elif p == "win32":
        import inject_windows as backend
    else:
        raise SystemExit(f"Nicht unterstuetzte Plattform: {p}")
    return backend


def main() -> int:
    cfg = Config()
    backend = _load_backend()

    warn = backend.preflight()
    if warn:
        print(f"[!] {warn}", file=sys.stderr)

    inject = backend.make_injector(cfg)
    run(cfg, inject)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
