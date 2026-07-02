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

On **Linux**, pyscard needs system packages first (Debian/Ubuntu):

```bash
sudo apt install pcscd pcsc-tools libpcsclite-dev swig gcc python3-dev python3-venv
sudo systemctl enable --now pcscd
```

Then see the two Linux gotchas below (`pn533_usb` blacklist, and polkit if you
run it as a non-root SSH user).

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
Reader layer  ← device plugged / unplugged   (poll-and-diff over readers())
   └─ Card layer  ← tag placed / removed       (CardMonitor)
```

`CardMonitor` re-enumerates the reader list on every cycle, so the service is
hotplug-capable in both directions. A poll-and-diff over `readers()` logs which
reader connected/disconnected (pyscard's `ReaderMonitor` is not used, as its PnP
events do not arrive on macOS):

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
uinput injects globally, independent of window focus. Needs `pcscd`, the
`pn533_usb` blacklist (see gotchas), and `/dev/uinput` access (group `input` +
udev rule). The systemd unit runs as root, so polkit does not apply to it.

```bash
sudo cp daemon/blacklist-nfc.conf /etc/modprobe.d/    # release reader from kernel NFC stack
sudo modprobe -r pn533_usb pn533 nfc
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
- **Linux — kernel NFC stack**: the `pn533_usb` module claims the ACR122U on
  plug-in and blocks pcscd (`readers()` returns empty even though `lsusb` shows
  the device). Blacklist it with `daemon/blacklist-nfc.conf`, or unload live:
  `sudo modprobe -r pn533_usb pn533 nfc && sudo systemctl restart pcscd`.
- **Linux — polkit**: pcsc-lite gates access via polkit. A non-root user over
  SSH has no local seat and is denied with `SCARD_W_SECURITY_VIOLATION`
  (`0x8010006A`). Running as root (the systemd unit does) bypasses this. To
  allow a specific non-root user, add a polkit rule for
  `org.debian.pcsc-lite.access_pcsc` / `access_card`.
- **Linux**: uinput sends scancodes, so the resulting character depends on the
  session keyboard layout — like a real keyboard. Harmless for the hex UID
  charset on de/us layouts; adjust `inject_linux._char_map` for exotic separators.
- **Windows**: no session-0 service (see above).
- **UID length**: 4 bytes (Mifare Classic) or 7 bytes (NTAG/Ultralight/DESFire) —
  both supported.

## Status

See [CHANGELOG.md](CHANGELOG.md) for what has been tested and what is still open.
