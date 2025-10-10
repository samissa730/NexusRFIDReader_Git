#!/usr/bin/env bash

set -euo pipefail

SERVICE_NAME="nexusrfid"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
RUN_SCRIPT="${PROJECT_ROOT}/scripts/run_app.sh"
UNIT_PATH="/etc/systemd/system/${SERVICE_NAME}.service"

if [ ! -x "${RUN_SCRIPT}" ]; then
  chmod +x "${RUN_SCRIPT}"
fi

sudo bash -c "cat > '${UNIT_PATH}'" <<UNIT
[Unit]
Description=Nexus RFID Application
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${PROJECT_ROOT}
ExecStart=${RUN_SCRIPT}
Restart=always
RestartSec=5
User=${SUDO_USER:-$(whoami)}
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}.service"
sudo systemctl restart "${SERVICE_NAME}.service"

echo "Installed and started ${SERVICE_NAME}.service"


