#!/usr/bin/env bash

set -e

# Resolve project root as the parent of this script directory
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

# Prefer project venv if present
if [ -f "${PROJECT_ROOT}/venv/bin/activate" ]; then
  . "${PROJECT_ROOT}/venv/bin/activate"
fi

# Ensure GUI env for systemd-launched session; use systemd-provided HOME and UID-derived runtime
export DISPLAY=${DISPLAY:-:0}
export XAUTHORITY=${XAUTHORITY:-${HOME}/.Xauthority}
uid=$(id -u)
if [ -z "${XDG_RUNTIME_DIR:-}" ]; then
  export XDG_RUNTIME_DIR="/run/user/${uid}"
fi
export DBUS_SESSION_BUS_ADDRESS=${DBUS_SESSION_BUS_ADDRESS:-unix:path=${XDG_RUNTIME_DIR}/bus}

# Wait for X server socket and XAUTHORITY to be readable (max ~20s)
for i in $(seq 1 40); do
  if [ -S "/tmp/.X11-unix/X${DISPLAY#:}" ] && [ -r "${XAUTHORITY}" ]; then
    break
  fi
  sleep 0.5
done

exec python3 "${PROJECT_ROOT}/main.py"


pi@raspberrypi:~/NexusRFIDReader_Git/scripts $ cat uninstall_service.sh 
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