#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Run with sudo: sudo ./scripts/install.sh" >&2
  exit 1
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PREFIX=/opt/robot-ai
APP=$PREFIX/app
VENV=$PREFIX/venv
XIAOZHI=$PREFIX/vendor/py-xiaozhi
XIAOZHI_COMMIT=577e1c9802a899ee558e6fa4f6fed8c4c64cecee

apt-get update
apt-get install -y \
  python3 python3-venv python3-dev python3-pip git rsync build-essential \
  libasound2-dev alsa-utils portaudio19-dev libopenblas0 libjpeg-dev ffmpeg \
  device-tree-compiler python3-picamera2

if ! id robotai >/dev/null 2>&1; then
  useradd --system --create-home --home-dir /var/lib/robot-ai --shell /usr/sbin/nologin robotai
fi
for group in dialout gpio spi audio video; do
  getent group "$group" >/dev/null && usermod -aG "$group" robotai || true
done

mkdir -p "$PREFIX" /etc/robot-ai /var/lib/robot-ai
rsync -a --delete --exclude .git "$ROOT/" "$APP/"
python3 -m venv --system-site-packages "$VENV"
"$VENV/bin/pip" install --upgrade pip setuptools wheel
"$VENV/bin/pip" install -e "$APP[hardware]"

mkdir -p "$PREFIX/vendor"
if [[ ! -d "$XIAOZHI/.git" ]]; then
  git clone https://github.com/huangjunsen0406/py-xiaozhi.git "$XIAOZHI"
fi
git -C "$XIAOZHI" fetch --all --tags
git -C "$XIAOZHI" checkout --detach "$XIAOZHI_COMMIT"
"$VENV/bin/pip" install -e "$XIAOZHI"

install -m 0644 "$APP/config/robot.yaml" /etc/robot-ai/robot.yaml
install -m 0644 "$APP/systemd/robot-ai.service" /etc/systemd/system/robot-ai.service
install -m 0644 "$APP/systemd/xiaozhi-robot.service" /etc/systemd/system/xiaozhi-robot.service

CONFIG_TXT=/boot/firmware/config.txt
[[ -f "$CONFIG_TXT" ]] || CONFIG_TXT=/boot/config.txt
for line in 'enable_uart=1' 'dtoverlay=disable-bt' 'dtparam=spi=on' 'dtparam=i2s=on'; do
  grep -qxF "$line" "$CONFIG_TXT" || echo "$line" >> "$CONFIG_TXT"
done

# Do not invent an audio overlay here. INMP441 + MAX98357A full duplex must
# pass the dedicated HIL gate documented in docs/HARDWARE.md.

sudo -u robotai "$VENV/bin/python" "$APP/integrations/py_xiaozhi/configure_robot.py" \
  --xiaozhi-root "$XIAOZHI" \
  --plugin-dir "$APP/integrations/py_xiaozhi/mcp_plugins" \
  --wake-word Robot

chown -R robotai:robotai /var/lib/robot-ai
systemctl daemon-reload
systemctl enable robot-ai.service

echo
printf '%s\n' \
  'Base installation complete.' \
  '1. Configure the custom duplex I2S sound card and verify arecord/aplay.' \
  '2. Reboot.' \
  '3. Run: sudo systemctl start robot-ai' \
  '4. Run diagnostics: sudo -u robotai /opt/robot-ai/venv/bin/robot-ai --config /etc/robot-ai/robot.yaml diagnostics' \
  '5. Run Xiaozhi once interactively as robotai to finish activation.' \
  '6. Only after Audio + Xiaozhi + MCP HIL PASS: enable xiaozhi-robot.service.'
