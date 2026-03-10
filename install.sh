#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# ---- Install uv if missing ----
if ! command -v uv &>/dev/null; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

echo "uv $(uv --version)"

# ---- Create venv & install deps ----
uv venv .venv --python 3.13
uv pip install -r requirements.txt

# ---- Device permissions ----
NEED_LOGOUT=false

# Serial port access (ENTTEC DMX USB → /dev/ttyUSB*)
if ! groups | grep -qw dialout; then
    echo "Adding $USER to 'dialout' group (serial port access)..."
    sudo usermod -aG dialout "$USER"
    NEED_LOGOUT=true
fi

# Input device access (Makey Makey via evdev)
if ! groups | grep -qw input; then
    echo "Adding $USER to 'input' group (evdev access)..."
    sudo usermod -aG input "$USER"
    NEED_LOGOUT=true
fi

# Udev rule for Makey Makey (vendor 0x2A66)
UDEV_RULE='/etc/udev/rules.d/99-makey-makey.rules'
RULE_CONTENT='SUBSYSTEM=="input", ATTRS{idVendor}=="2a66", MODE="0666", TAG+="uaccess"'
if [ ! -f "$UDEV_RULE" ] || ! grep -q "2a66" "$UDEV_RULE" 2>/dev/null; then
    echo "Installing udev rule for Makey Makey..."
    echo "$RULE_CONTENT" | sudo tee "$UDEV_RULE" > /dev/null
    sudo udevadm control --reload-rules
    sudo udevadm trigger
fi

echo ""
if $NEED_LOGOUT; then
    echo "⚠  Group membership changed — log out and back in (or reboot) for it to take effect."
fi
echo "Done. Run the app with:  ./run.sh"
