#!/usr/bin/env bash
#
# provision-deb.sh — system provisioning for the NFC keyboard-wedge on
# Debian/Ubuntu (.deb) machines.
#
# Installs PC/SC + build dependencies, enables pcscd, releases the ACR122U from
# the kernel NFC stack (pn533_usb), grants /dev/uinput access, creates the
# Python venv, and optionally adds a polkit rule for non-root PC/SC access.
#
# Usage (as root):
#   sudo ./scripts/provision-deb.sh [--user NAME] [--polkit-user NAME]
#
#   --user NAME         owner of the venv + added to group 'input'
#                       (default: the sudo-invoking user)
#   --polkit-user NAME  allow this user to use pcscd without a local seat
#                       (needed for a non-root user over SSH; NOT needed for a
#                       desktop user with an active session, nor for the
#                       root systemd service)
#
# Idempotent — safe to re-run.
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Re-running with sudo ..." >&2
  exec sudo -E bash "$0" "$@"
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_USER="${SUDO_USER:-root}"
POLKIT_USER=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --user)        TARGET_USER="${2:?}"; shift 2 ;;
    --polkit-user) POLKIT_USER="${2:?}"; shift 2 ;;
    -h|--help)     sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

if ! command -v apt-get >/dev/null; then
  echo "apt-get not found — this script targets Debian/Ubuntu." >&2
  exit 1
fi
. /etc/os-release 2>/dev/null || true
echo "==> Distro: ${PRETTY_NAME:-unknown} | user: ${TARGET_USER} | repo: ${REPO_ROOT}"

# --- 1. packages ----------------------------------------------------------
echo "==> Installing packages ..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y pcscd pcsc-tools libpcsclite-dev swig gcc python3-dev git

# ensurepip ships in a version-specific venv package on Debian
PYVER="$(python3 -c 'import sys;print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
apt-get install -y "python${PYVER}-venv" 2>/dev/null || apt-get install -y python3-venv

systemctl enable --now pcscd

# --- 2. release reader from kernel NFC stack ------------------------------
echo "==> Blacklisting kernel NFC modules (pn533_usb) ..."
install -m 0644 "${REPO_ROOT}/daemon/blacklist-nfc.conf" /etc/modprobe.d/blacklist-nfc.conf
modprobe -r pn533_usb pn533 nfc 2>/dev/null || true
systemctl restart pcscd

# --- 3. uinput access -----------------------------------------------------
echo "==> Configuring /dev/uinput access ..."
install -m 0644 "${REPO_ROOT}/daemon/99-uinput.rules" /etc/udev/rules.d/99-uinput.rules
udevadm control --reload
modprobe uinput
udevadm trigger --name-match=uinput 2>/dev/null || true
if [[ "$TARGET_USER" != "root" ]]; then
  usermod -aG input "$TARGET_USER"
  echo "    added '${TARGET_USER}' to group 'input' (re-login required)"
fi

# --- 4. optional polkit rule ----------------------------------------------
if [[ -n "$POLKIT_USER" ]]; then
  echo "==> Installing polkit rule for PC/SC user '${POLKIT_USER}' ..."
  cat > /etc/polkit-1/rules.d/50-pcsc-wedge.rules <<EOF
polkit.addRule(function(action, subject) {
  if ((action.id == "org.debian.pcsc-lite.access_pcsc" ||
       action.id == "org.debian.pcsc-lite.access_card") &&
      subject.user == "${POLKIT_USER}") {
    return polkit.Result.YES;
  }
});
EOF
  systemctl restart polkit || true
fi

# --- 5. python venv (owned by the target user) ----------------------------
echo "==> Creating Python venv + installing pyscard/evdev ..."
VENV_CMD="cd '${REPO_ROOT}' && python3 -m venv .venv && . .venv/bin/activate && pip install -q --upgrade pip && pip install -q pyscard evdev"
if [[ "$TARGET_USER" == "root" ]]; then
  bash -c "$VENV_CMD"
else
  sudo -u "$TARGET_USER" bash -c "$VENV_CMD"
fi

echo
echo "==> Provisioning complete."
echo "    Manual test:  cd ${REPO_ROOT} && . .venv/bin/activate && python wedge.py"
echo "    As a service: sudo ${REPO_ROOT}/scripts/install-service.sh"
[[ "$TARGET_USER" != "root" ]] && echo "    Note: log out/in once so '${TARGET_USER}' picks up group 'input'."
exit 0
