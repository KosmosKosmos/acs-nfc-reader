#!/usr/bin/env bash
#
# install-service.sh — install + enable the NFC keyboard-wedge as a systemd
# system service on Debian/Ubuntu. Run scripts/provision-deb.sh first.
#
# Runs as root by default. This is the simplest robust setup for desktops:
#   - root bypasses the pcsc-lite polkit check, so no polkit rule is needed;
#   - /dev/uinput is a kernel-global device, so keystrokes reach whatever GUI
#     session currently has focus, regardless of which user owns the service.
#
# Usage (as root):
#   sudo ./scripts/install-service.sh
#
# Idempotent — safe to re-run.
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Re-running with sudo ..." >&2
  exec sudo -E bash "$0" "$@"
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PY="${REPO_ROOT}/.venv/bin/python"
UNIT="/etc/systemd/system/nfc-wedge.service"

if [[ ! -x "$VENV_PY" ]]; then
  echo "venv not found at ${VENV_PY}" >&2
  echo "Run scripts/provision-deb.sh first." >&2
  exit 1
fi

echo "==> Writing ${UNIT} ..."
cat > "$UNIT" <<EOF
[Unit]
Description=NFC Keyboard-Wedge (ACR122U UID -> Keystrokes)
After=pcscd.service
Wants=pcscd.service

[Service]
Type=simple
ExecStart=${VENV_PY} ${REPO_ROOT}/wedge.py
Restart=on-failure
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now nfc-wedge

echo "==> Status:"
systemctl --no-pager --lines=5 status nfc-wedge || true
echo
echo "==> Follow logs: journalctl -u nfc-wedge -f"
exit 0
