#!/bin/bash
set -euo pipefail

EXEC_PATH=${1:-}
RUN_USER=${2:-$(logname || echo pi)}
SERVICE_NAME=nexusrfidreader-prod

if [ -z "$EXEC_PATH" ]; then
  echo "Usage: sudo bash $0 /path/to/NexusRFIDReader [username]"
  exit 1
fi

# Place executable in a user-local standard path (default used by service)
install -d -m 0755 -o "$RUN_USER" -g "$RUN_USER" "/home/$RUN_USER/.local/bin"
install -m 0755 -o "$RUN_USER" -g "$RUN_USER" "$EXEC_PATH" "/home/$RUN_USER/.local/bin/NexusRFIDReader"

# Enable user lingering and install service
loginctl enable-linger "$RUN_USER" || true
install -d -m 0755 -o "$RUN_USER" -g "$RUN_USER" \
  "/home/$RUN_USER/.config/systemd/user"

sed "s|%h|/home/${RUN_USER}|g; s|%i|${RUN_USER}|g" \
  "$(dirname "$0")/nexusrfidreader-prod.service" > \
  "/home/$RUN_USER/.config/systemd/user/${SERVICE_NAME}.service"

chown "$RUN_USER":"$RUN_USER" \
  "/home/$RUN_USER/.config/systemd/user/${SERVICE_NAME}.service"

sudo -u "$RUN_USER" systemctl --user daemon-reload
sudo -u "$RUN_USER" systemctl --user enable ${SERVICE_NAME}.service
sudo -u "$RUN_USER" systemctl --user start ${SERVICE_NAME}.service

echo "Installed and started product user service ${SERVICE_NAME} for ${RUN_USER}."
#!/bin/bash
set -euo pipefail

EXEC_PATH=${1:-}
RUN_USER=${2:-$(logname || echo pi)}
SERVICE_NAME=nexusrfidreader-prod

if [ -z "$EXEC_PATH" ]; then
  echo "Usage: sudo bash $0 /path/to/NexusRFIDReader [username]"
  exit 1
fi

# Place executable in a user-local standard path (default used by service)
install -d -m 0755 -o "$RUN_USER" -g "$RUN_USER" "/home/$RUN_USER/.local/bin"
install -m 0755 -o "$RUN_USER" -g "$RUN_USER" "$EXEC_PATH" "/home/$RUN_USER/.local/bin/NexusRFIDReader"

# Enable user lingering and install service
loginctl enable-linger "$RUN_USER" || true
install -d -m 0755 -o "$RUN_USER" -g "$RUN_USER" \
  "/home/$RUN_USER/.config/systemd/user"

sed "s|%h|/home/${RUN_USER}|g; s|%i|${RUN_USER}|g" \
  "$(dirname "$0")/nexusrfidreader-prod.service" > \
  "/home/$RUN_USER/.config/systemd/user/${SERVICE_NAME}.service"

chown "$RUN_USER":"$RUN_USER" \
  "/home/$RUN_USER/.config/systemd/user/${SERVICE_NAME}.service"

sudo -u "$RUN_USER" systemctl --user daemon-reload
sudo -u "$RUN_USER" systemctl --user enable ${SERVICE_NAME}.service
sudo -u "$RUN_USER" systemctl --user start ${SERVICE_NAME}.service

echo "Installed and started product user service ${SERVICE_NAME} for ${RUN_USER}."

