#!/bin/bash
set -euo pipefail

PROJECT_DIR=${1:-}
RUN_USER=${2:-$(logname || echo pi)}

if [ -z "$PROJECT_DIR" ]; then
  echo "Usage: sudo bash $0 /absolute/path/to/NexusRFIDReader [username]"
  exit 1
fi

SERVICE_NAME=nexusrfidreader-dev

# Enable user lingering so --user services run at boot
loginctl enable-linger "$RUN_USER" || true

install -d -m 0755 -o "$RUN_USER" -g "$RUN_USER" \
  "/home/$RUN_USER/.config/systemd/user"

sed "s|%h|/home/${RUN_USER}|g; s|%i|${RUN_USER}|g; s|WorkingDirectory=.*|WorkingDirectory=${PROJECT_DIR}|g" \
  "$(dirname "$0")/nexusrfidreader-dev.service" > \
  "/home/$RUN_USER/.config/systemd/user/${SERVICE_NAME}.service"

chown "$RUN_USER":"$RUN_USER" \
  "/home/$RUN_USER/.config/systemd/user/${SERVICE_NAME}.service"

sudo -u "$RUN_USER" systemctl --user daemon-reload
sudo -u "$RUN_USER" systemctl --user enable ${SERVICE_NAME}.service
sudo -u "$RUN_USER" systemctl --user start ${SERVICE_NAME}.service

echo "Installed and started user service ${SERVICE_NAME} for ${RUN_USER}."
#!/bin/bash
set -euo pipefail

PROJECT_DIR=${1:-}
RUN_USER=${2:-$(logname || echo pi)}

if [ -z "$PROJECT_DIR" ]; then
  echo "Usage: sudo bash $0 /absolute/path/to/NexusRFIDReader [username]"
  exit 1
fi

SERVICE_NAME=nexusrfidreader-dev
SERVICE_UNIT=/etc/systemd/user/${SERVICE_NAME}.service

# Ensure lingering enabled so user services run at boot
loginctl enable-linger "$RUN_USER" || true

install -d -m 0755 -o "$RUN_USER" -g "$RUN_USER" \
  "/home/$RUN_USER/.config/systemd/user"

sed "s|%h|/home/${RUN_USER}|g; s|%i|${RUN_USER}|g; s|WorkingDirectory=.*|WorkingDirectory=${PROJECT_DIR}|g" \
  "$(dirname "$0")/nexusrfidreader-dev.service" > \
  "/home/$RUN_USER/.config/systemd/user/${SERVICE_NAME}.service"

chown "$RUN_USER":"$RUN_USER" \
  "/home/$RUN_USER/.config/systemd/user/${SERVICE_NAME}.service"

sudo -u "$RUN_USER" systemctl --user daemon-reload
sudo -u "$RUN_USER" systemctl --user enable ${SERVICE_NAME}.service
sudo -u "$RUN_USER" systemctl --user start ${SERVICE_NAME}.service

echo "Installed and started user service ${SERVICE_NAME} for ${RUN_USER}."

