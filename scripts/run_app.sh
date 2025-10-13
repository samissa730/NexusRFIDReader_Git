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

# Ensure GUI env for systemd-launched session
export DISPLAY=${DISPLAY:-:0}
export XAUTHORITY=${XAUTHORITY:-/home/pi/.Xauthority}
export HOME=${HOME:-/home/pi}
export XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-/run/user/1000}

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