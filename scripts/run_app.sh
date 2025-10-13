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