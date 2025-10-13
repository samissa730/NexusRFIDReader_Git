#!/usr/bin/env bash

set -euo pipefail

SERVICE_NAME="nexusrfid"
UNIT_PATH="/etc/systemd/system/${SERVICE_NAME}.service"

if systemctl list-units --type=service --all | grep -q "${SERVICE_NAME}.service"; then
  sudo systemctl stop "${SERVICE_NAME}.service" || true
  sudo systemctl disable "${SERVICE_NAME}.service" || true
fi

if [ -f "${UNIT_PATH}" ]; then
  sudo rm -f "${UNIT_PATH}"
fi

sudo systemctl daemon-reload

echo "Uninstalled ${SERVICE_NAME}.service"