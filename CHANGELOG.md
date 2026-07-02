# Changelog

All notable changes to this project are documented here.
Format loosely follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added
- Cross-platform NFC keyboard-wedge for the ACS ACR122U.
- Shared PC/SC core (`wedge_core.py`): `Config`, UID read via the standard
  `FF CA 00 00 00` pseudo-APDU, `CardMonitor` + `ReaderMonitor` run loop.
- Platform injection backends:
  - `inject_macos.py` — Quartz CGEvent, Unicode, layout-independent.
  - `inject_linux.py` — `/dev/uinput` via evdev (real virtual HID, scancodes).
  - `inject_windows.py` — `SendInput` + `KEYEVENTF_UNICODE` via ctypes.
- Unified entry point `wedge.py` with automatic backend selection.
- Reader hotplug logging via a cross-platform poll-and-diff over `readers()`
  (replaces the `ReaderMonitor`, whose PnP events do not arrive on macOS).
- Daemon configs: macOS LaunchAgent, Linux systemd unit + udev rule.
- English README with setup, service, and hotplug documentation.

## Verification status

### Tested — macOS (Apple Silicon, macOS 26, Python 3.14, pyscard 2.3.1)
- ✅ PC/SC reader enumeration — `ACS ACR122U PICC Interface` via Apple's
  built-in `ifd-ccid.bundle` 1.5.1 (no ACS driver needed).
- ✅ UID read end-to-end — 7-byte NXP UIDs read correctly
  (e.g. `041C96CAB16F81`, `045F69B24B7880`).
- ✅ Keystroke injection — CGEvent typed a UID into a focused field live.
- ✅ Accessibility permission check (`AXIsProcessTrusted`).
- ✅ `ReaderMonitor` fires the initial reader-present event on startup.
- ✅ Refactored module structure imports and wires up cleanly.
- ✅ Reader **hotplug** — unplugging and re-plugging the reader while the
  service runs works: tags on the re-plugged reader are read without a restart.
  This works because `CardMonitor` re-enumerates readers every cycle.

### Resolved
- ⚠️→✅ macOS `ReaderMonitor` did not deliver PnP arrival/removal events, so
  the hotplug log stayed silent. Replaced with a poll-and-diff over `readers()`
  in the run loop; works on all platforms and names the specific reader that
  connected/disconnected. Startup enumeration + clean shutdown verified on macOS.

### Not yet verified
- ⬜ Multiple simultaneous readers on one host.
- ⬜ Linux backend (`inject_linux.py`) — no live run on a Linux host yet;
  uinput injection and udev/`pcscd` setup untested in practice.
- ⬜ Windows backend (`inject_windows.py`) — no live run; `SendInput` and the
  session-0 caveat untested in practice.
- ⬜ Daemon configs (LaunchAgent / systemd / logon task) not yet installed and
  run as actual background services.

## TODO

- [ ] Test on a Linux host with the reader (uinput device creation, layout,
      `pcscd` dependency, non-root `/dev/uinput` via udev rule).
- [ ] Test on Windows (Unicode SendInput, logon-task autostart).
- [ ] 4-byte UID (Mifare Classic) read path — only 7-byte NXP tags tested so far.
- [ ] Optional: CLI flags / config file instead of editing `Config` in source.
- [ ] Optional: debounce repeated reads of the same tag left on the reader.
- [ ] Optional: package as a signed macOS `.app` (py2app) with its own
      Accessibility grant for non-terminal deployment.
- [ ] Remove or fold in the superseded standalone `wedge_macos.py`.
