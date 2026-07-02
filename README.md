# acs-nfc-reader — NFC Keyboard Wedge (ACR122U)

Reads the UID of NFC tags via an **ACS ACR122U** (PC/SC) and "types" it as
keyboard input into the currently focused field, optionally followed by Enter.

The ACR122U is **not** an HID keyboard — it is a PC/SC CCID device (PN532 chip).
Its firmware cannot be turned into a USB keyboard by software. Instead, this
tool emulates the behaviour the same way commercial "NFC keyboard wedge" tools
do: a background process reads the UID over PC/SC and injects keystrokes through
the operating system's input API.

```
Tag placed on reader  →  read UID via PC/SC  →  inject keystrokes into the OS
```

## Architecture

Only the injection layer is platform-specific. The PC/SC layer is shared.

```
wedge.py            Entry point — picks the backend by sys.platform
wedge_core.py       Config, UID read (FF CA 00 00 00), reader + card monitors   [shared]
inject_macos.py     Quartz CGEvent (Unicode, layout-independent)
inject_linux.py     /dev/uinput via evdev (real virtual HID, scancodes)
inject_windows.py   SendInput + KEYEVENTF_UNICODE (ctypes, layout-independent)
daemon/             LaunchAgent (macOS), systemd unit + udev rule (Linux)
wedge_macos.py      Original standalone macOS prototype (superseded by wedge.py)
```

| Layer | macOS | Linux | Windows |
|-------|-------|-------|---------|
| Read card (PC/SC) | `PCSC.framework` | `pcsclite` / `pcscd` | `WinSCard` |
| Inject keystrokes | `CGEvent` (Quartz) | `/dev/uinput` (real virtual HID) | `SendInput` |

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install pyscard                       # all platforms
# macOS:
pip install pyobjc-framework-Quartz pyobjc-framework-ApplicationServices
# Linux:
pip install evdev
# Windows: no extra packages (pure ctypes)

python wedge.py
```

## Configuration

Edit `Config` in `wedge_core.py`:

| Field | Default | Meaning |
|-------|---------|---------|
| `uppercase` | `True` | `AABB` vs `aabb` |
| `separator` | `""` | e.g. `":"` → `AA:BB:CC:DD` |
| `append_enter` | `True` | send Enter after the UID |
| `reverse_bytes` | `False` | LSB-first for legacy systems |
| `inter_key_delay` | `0.004` | seconds between keystrokes |

## Hotplug behaviour

The service is event-driven and watches two layers:

```
Reader layer  ← device plugged / unplugged   (ReaderMonitor)
   └─ Card layer  ← tag placed / removed      (CardMonitor)
```

pyscard re-enumerates the reader list on every monitor cycle, so the service is
hotplug-capable in both directions:

- Start the service with **no** reader attached → it waits until one appears.
- Plug a reader in **after** the service is running → detected, tags read.
- Unplug and re-plug while running → handled without restart.
- **Multiple readers** at once → all monitored; a tag on *any* of them triggers.

On Linux this requires `pcscd` to be running (the systemd unit declares
`Wants=pcscd.service`).

## Running as a service

Supported on all three platforms, each with one session caveat:

### macOS — LaunchAgent (not LaunchDaemon)
Must run in the GUI session, otherwise CGEvent cannot reach a window. The
**Accessibility** permission must be granted to the `.venv/bin/python` binary,
not to the terminal.

```bash
cp daemon/com.kosmoskosmos.nfcwedge.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.kosmoskosmos.nfcwedge.plist
# stop:
launchctl bootout gui/$(id -u)/com.kosmoskosmos.nfcwedge
```

### Linux — systemd (cleanest option)
uinput injects globally, independent of window focus. Needs `pcscd` and
`/dev/uinput` access (group `input` + udev rule).

```bash
sudo cp daemon/99-uinput.rules /etc/udev/rules.d/
sudo udevadm control --reload && sudo modprobe uinput
sudo cp -r . /opt/nfc-kbd-wedge && sudo cp daemon/nfc-wedge.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now nfc-wedge
```

### Windows — logon task, NOT a service
A real Windows service runs in **session 0**, where `SendInput` cannot reach the
interactive desktop. Register it as a logon task in the user session instead:

```powershell
schtasks /Create /TN "NFC-Wedge" /SC ONLOGON /RL LIMITED ^
  /TR "C:\path\nfc-kbd-wedge\.venv\Scripts\pythonw.exe C:\path\nfc-kbd-wedge\wedge.py"
```

## Gotchas

- **macOS**: without Accessibility permission, keystrokes are silently dropped
  (reading still works, typing does not).
- **Linux**: uinput sends scancodes, so the resulting character depends on the
  session keyboard layout — like a real keyboard. Harmless for the hex UID
  charset on de/us layouts; adjust `inject_linux._char_map` for exotic separators.
- **Windows**: no session-0 service (see above).
- **UID length**: 4 bytes (Mifare Classic) or 7 bytes (NTAG/Ultralight/DESFire) —
  both supported.

## Status

See [CHANGELOG.md](CHANGELOG.md) for what has been tested and what is still open.
