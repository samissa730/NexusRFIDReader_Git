#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="/opt/nexusrfid"
IOT_SCRIPT="${PROJECT_ROOT}/Azure-IoT-Connection/iot_service.py"
APP_SCRIPT="${PROJECT_ROOT}/main.py"
SOCKET_DIR="/var/run"
SOCKET_PATH="${SOCKET_DIR}/nexus-iot.sock"

mkdir -p "${SOCKET_DIR}" /tmp/runtime-root
chmod 700 /tmp/runtime-root || true

# Keep behavior close to existing production launch flow.
if command -v dhclient >/dev/null 2>&1; then
  dhclient usb0 2>/dev/null || true
fi

if [ -f "${SOCKET_PATH}" ]; then
  rm -f "${SOCKET_PATH}" || true
fi

python3 "${IOT_SCRIPT}" &
IOT_PID=$!

sleep 2

python3 "${APP_SCRIPT}" &
APP_PID=$!

shutdown() {
  kill -TERM "${APP_PID}" "${IOT_PID}" 2>/dev/null || true
  wait "${APP_PID}" 2>/dev/null || true
  wait "${IOT_PID}" 2>/dev/null || true
}

trap shutdown SIGINT SIGTERM

while true; do
  if ! kill -0 "${IOT_PID}" 2>/dev/null; then
    echo "IoT service exited; stopping container"
    shutdown
    exit 1
  fi
  if ! kill -0 "${APP_PID}" 2>/dev/null; then
    echo "App process exited; stopping container"
    shutdown
    exit 1
  fi
  sleep 2
done
