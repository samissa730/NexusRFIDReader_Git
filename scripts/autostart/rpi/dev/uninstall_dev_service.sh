#!/bin/bash
set -euo pipefail

RUN_USER=${1:-$(logname || echo pi)}
SERVICE_NAME=nexusrfidreader-dev

sudo -u "$RUN_USER" systemctl --user stop ${SERVICE_NAME}.service || true
sudo -u "$RUN_USER" systemctl --user disable ${SERVICE_NAME}.service || true
rm -f "/home/$RUN_USER/.config/systemd/user/${SERVICE_NAME}.service"
sudo -u "$RUN_USER" systemctl --user daemon-reload || true

echo "Uninstalled user service ${SERVICE_NAME} for ${RUN_USER}."
#!/bin/bash
set -euo pipefail

RUN_USER=${1:-$(logname || echo pi)}
SERVICE_NAME=nexusrfidreader-dev

sudo -u "$RUN_USER" systemctl --user stop ${SERVICE_NAME}.service || true
sudo -u "$RUN_USER" systemctl --user disable ${SERVICE_NAME}.service || true
rm -f "/home/$RUN_USER/.config/systemd/user/${SERVICE_NAME}.service"
sudo -u "$RUN_USER" systemctl --user daemon-reload || true

echo "Uninstalled user service ${SERVICE_NAME} for ${RUN_USER}."

