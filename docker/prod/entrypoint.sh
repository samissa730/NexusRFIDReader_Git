#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="/opt/nexusrfid"
IOT_SCRIPT="${PROJECT_ROOT}/Azure-IoT-Connection/iot_service.py"
APP_SCRIPT="${PROJECT_ROOT}/main.py"
IOT_CONFIG="/etc/nexuslocate/config/provisioning_config.json"
SOCKET_DIR="/var/run"
SOCKET_PATH="${SOCKET_DIR}/nexus-iot.sock"
IOT_PID=""
IOT_ENABLED=1

mkdir -p "${SOCKET_DIR}" /tmp/runtime-root
chmod 700 /tmp/runtime-root || true

# Keep behavior close to existing production launch flow.
if command -v dhclient >/dev/null 2>&1; then
  dhclient usb0 2>/dev/null || true
fi

if [ -f "${SOCKET_PATH}" ]; then
  rm -f "${SOCKET_PATH}" || true
fi

if [ ! -f "${IOT_CONFIG}" ]; then
  echo "WARNING: Missing ${IOT_CONFIG}. Starting in degraded mode (GUI only, IoT disabled)."
  IOT_ENABLED=0
else
  python3 "${IOT_SCRIPT}" &
  IOT_PID=$!

  sleep 3

  if ! kill -0 "${IOT_PID}" 2>/dev/null; then
    echo "WARNING: IoT service failed during startup. Continuing in degraded mode (GUI only)."
    IOT_ENABLED=0
    IOT_PID=""
  fi
fi

python3 "${APP_SCRIPT}" &
APP_PID=$!

shutdown() {
  kill -TERM "${APP_PID}" 2>/dev/null || true
  if [ -n "${IOT_PID}" ]; then
    kill -TERM "${IOT_PID}" 2>/dev/null || true
  fi
  wait "${APP_PID}" 2>/dev/null || true
  if [ -n "${IOT_PID}" ]; then
    wait "${IOT_PID}" 2>/dev/null || true
  fi
}

trap shutdown SIGINT SIGTERM

while true; do
  if [ "${IOT_ENABLED}" -eq 1 ] && [ -n "${IOT_PID}" ] && ! kill -0 "${IOT_PID}" 2>/dev/null; then
    echo "WARNING: IoT service exited; switching to degraded mode (GUI only)."
    IOT_ENABLED=0
    IOT_PID=""
  fi
  if ! kill -0 "${APP_PID}" 2>/dev/null; then
    echo "App process exited; stopping container"
    shutdown
    exit 1
  fi
  sleep 2
done
