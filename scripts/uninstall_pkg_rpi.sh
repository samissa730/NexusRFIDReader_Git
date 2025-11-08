#!/usr/bin/env bash

set -euo pipefail

# Color palette for better log output
BLUE='\033[0;34m'
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
PURPLE='\033[0;35m'
NC='\033[0m'

PACKAGE_NAME="nexusrfidreader"
APP_PREFIX="/opt/NexusRFIDReader"
SERVICE_NAME="nexusrfid.service"

usage() {
  cat <<EOF
Usage: $(basename "$0") [--purge]

Removes the installed Nexus RFID Reader Debian package and cleans up the
systemd service, desktop entries, and optional resources.

Options:
  --purge   Remove package plus configuration/cache files (~/.nexusrfid)
  -h        Show this help text
EOF
}

PURGE=0

log_info() {
  printf '%b\n' "${CYAN}[uninstall][INFO]${NC} $*"
}

log_step() {
  printf '%b\n' "${BLUE}[uninstall][STEP]${NC} $*"
}

log_success() {
  printf '%b\n' "${GREEN}[uninstall][SUCCESS]${NC} $*"
}

log_warn() {
  printf '%b\n' "${YELLOW}[uninstall][WARN]${NC} $*"
}

log_error() {
  printf '%b\n' "${RED}[uninstall][ERROR]${NC} $*" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --purge)
      PURGE=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      log_error "Unknown option: $1"
      usage
      exit 1
      ;;
  esac
done

if ! command -v apt >/dev/null 2>&1; then
  log_error "apt not available. Please uninstall ${PACKAGE_NAME} manually."
  exit 1
fi

detect_target_user() {
  if [ -n "${SUDO_USER:-}" ] && [ "${SUDO_USER}" != "root" ]; then
    echo "${SUDO_USER}"
    return
  fi

  if command -v logname >/dev/null 2>&1; then
    local ln_user
    ln_user="$(logname 2>/dev/null || true)"
    if [ -n "${ln_user}" ] && [ "${ln_user}" != "root" ]; then
      echo "${ln_user}"
      return
    fi
  fi

  local uid_user
  uid_user="$(getent passwd 1000 | cut -d: -f1)"
  if [ -n "${uid_user}" ]; then
    echo "${uid_user}"
  else
    echo "root"
  fi
}

printf '%b\n' "${PURPLE}============================================================${NC}"
printf '%b\n' "${PURPLE}[uninstall] Nexus RFID Reader Package Removal${NC}"
printf '%b\n' "${PURPLE}============================================================${NC}"

log_step "Stopping service (if running)..."
if systemctl list-unit-files | grep -q "^${SERVICE_NAME}"; then
  sudo systemctl stop "${SERVICE_NAME}" || true
  sudo systemctl disable "${SERVICE_NAME}" || true
  log_success "Service ${SERVICE_NAME} stopped and disabled"
else
  log_warn "Service ${SERVICE_NAME} not registered with systemd"
fi

log_step "Removing Debian package ${PACKAGE_NAME}..."
sudo apt remove -y "${PACKAGE_NAME}" || true

if [ "${PURGE}" -eq 1 ]; then
  log_step "Purging package and configuration files..."
  sudo apt purge -y "${PACKAGE_NAME}" || true
fi

log_step "Cleaning up residual system files..."
sudo rm -rf "${APP_PREFIX}"
sudo rm -f /usr/local/bin/arp-scan
sudo rm -f /etc/systemd/system/${SERVICE_NAME}
sudo systemctl daemon-reload || true

if [ "${PURGE}" -eq 1 ]; then
  target_user="$(detect_target_user)"
  if [ -n "${target_user}" ]; then
    target_home="$(getent passwd "${target_user}" | cut -d: -f6)"
    target_home="${target_home:-/home/${target_user}}"
    sudo rm -rf "${target_home}/.nexusrfid"
    sudo rm -f "${target_home}/.local/share/applications/nexus-rfid.desktop"
    log_success "Removed user data for ${target_user}"
  fi
fi

log_success "Uninstallation completed."
printf '%b\n' "${PURPLE}============================================================${NC}"

