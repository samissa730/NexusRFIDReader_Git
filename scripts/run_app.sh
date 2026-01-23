#!/usr/bin/env bash

set -e

# Setup internet connection via usb0 FIRST, before anything else
# This must run before any network-dependent operations
sudo dhclient usb0 2>&1 || true

# Resolve project root as the parent of this script directory
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

# Prefer project venv if present
if [ -f "${PROJECT_ROOT}/venv/bin/activate" ]; then
  . "${PROJECT_ROOT}/venv/bin/activate"
fi

# Get actual user info (service runs as user, not root)
ACTUAL_USER=${SUDO_USER:-$USER}
if [ -z "$ACTUAL_USER" ]; then
    ACTUAL_USER=$(whoami)
fi
ACTUAL_HOME=$(getent passwd "$ACTUAL_USER" 2>/dev/null | cut -d: -f6)
if [ -z "$ACTUAL_HOME" ]; then
    ACTUAL_HOME=$(eval echo ~$ACTUAL_USER)
fi
ACTUAL_UID=$(id -u "$ACTUAL_USER" 2>/dev/null || echo "1000")

# Ensure GUI env for systemd-launched session
export DISPLAY=${DISPLAY:-:0}
# Use actual user's home for XAUTHORITY if not already set by systemd
export XAUTHORITY=${XAUTHORITY:-${ACTUAL_HOME}/.Xauthority}
export HOME=${HOME:-${ACTUAL_HOME}}
export XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-/run/user/${ACTUAL_UID}}
export DBUS_SESSION_BUS_ADDRESS=${DBUS_SESSION_BUS_ADDRESS:-unix:path=/run/user/${ACTUAL_UID}/bus}

# Allow X11 access (if xhost is available)
if command -v xhost >/dev/null 2>&1; then
    xhost +local: >/dev/null 2>&1 || true
fi

# Run Python as the actual user (not root) to maintain X11 access
# The service already runs as the user, so we don't need sudo here
exec python3 "${PROJECT_ROOT}/main.py"