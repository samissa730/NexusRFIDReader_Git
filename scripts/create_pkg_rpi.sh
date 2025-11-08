#!/usr/bin/env bash

set -euo pipefail

# Color palette for prettier logs
BLUE='\033[0;34m'
CYAN='\033[0;36m'
GREEN='\033[0;32m'
PURPLE='\033[0;35m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

PACKAGE_NAME="nexusrfidreader"
APP_DIR_NAME="NexusRFIDReader"
INSTALL_PREFIX="/opt/${APP_DIR_NAME}"
VERSION="${VERSION:-1.0}"
BUILD_ROOT="${PROJECT_ROOT}/build/package"
DIST_DIR="${PROJECT_ROOT}"
ARCH_MATRIX=("amd64:x64" "i386:x86")
declare -a BUILT_FILES=()

EXCLUDES=(
  ".git"
  ".mypy_cache"
  ".pytest_cache"
  "__pycache__"
  "build"
  "dist"
  "tests"
  "utils_Test"
  "Azure-IoT-Connection"
  "build"
  "venv"
  "UnitTests"
  "pipelines"
  "*.deb"
  "*.pyc"
  "*.pyo"
  "*.orig"
)

usage() {
  cat <<EOH
Usage: $(basename "$0") [--version <semver>] [--arch amd64,i386] [--keep-build]

Builds Debian packages (x64 and x86) for the Nexus RFID Reader application.

Options:
  --version <semver>   Override package version (default: ${VERSION})
  --arch <list>        Comma-separated list of deb-arch[:label] entries (default: amd64:x64,i386:x86)
  --keep-build         Retain intermediate build directory for inspection
  -h, --help           Show this help text
EOH
}

cleanup() {
  if [ "${KEEP_BUILD:-0}" -eq 0 ] && [ -d "${BUILD_ROOT}" ]; then
    rm -rf "${BUILD_ROOT}"
  fi
}

trap cleanup EXIT

log() {
  printf '%b\n' "${CYAN}[create-pkg][INFO]${NC} $*"
}

err() {
  printf '%b\n' "${RED}[create-pkg][ERROR]${NC} $*" >&2
}

log_step() {
  printf '%b\n' "${BLUE}[create-pkg][STEP]${NC} $*"
}

log_success() {
  printf '%b\n' "${GREEN}[create-pkg][SUCCESS]${NC} $*"
}

log_warn() {
  printf '%b\n' "${YELLOW}[create-pkg][WARN]${NC} $*"
}

ensure_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    err "Required command '$1' not found on PATH."
    exit 1
  fi
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --version)
        VERSION="$2"
        shift 2
        ;;
      --arch)
        IFS=',' read -r -a ARCH_MATRIX <<<"$2"
        shift 2
        ;;
      --keep-build)
        KEEP_BUILD=1
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        err "Unknown argument: $1"
        usage
        exit 1
        ;;
    esac
  done
}

copy_project_payload() {
  local src="$1"
  local dest="$2"

  rsync_args=(-a --delete --exclude=".git*")
  for pattern in "${EXCLUDES[@]}"; do
    rsync_args+=("--exclude=${pattern}")
  done
  rsync_args+=("${src}/" "${dest}/")

  rsync "${rsync_args[@]}"
}

prepare_venv() {
  local app_root="$1"
  local python_bin="${PYTHON_BIN:-python3}"
  local venv_dir="${app_root}/venv"

  log "Creating virtual environment at ${venv_dir}"
  "${python_bin}" -m venv --clear --copies "${venv_dir}"

  log "Installing Python dependencies into venv"
  "${venv_dir}/bin/pip" install --upgrade pip wheel setuptools
  if [ -f "${app_root}/requirements.txt" ]; then
    "${venv_dir}/bin/pip" install --no-cache-dir -r "${app_root}/requirements.txt"
  else
    err "requirements.txt not found in ${app_root}"
    exit 1
  fi

  # Strip caches to keep package size down
  find "${venv_dir}" -type d -name "__pycache__" -prune -exec rm -rf {} +
}

bundle_arp_scan() {
  local app_root="$1"
  local bindir="${app_root}/bin"

  mkdir -p "${bindir}"
  if command -v arp-scan >/dev/null 2>&1; then
    install -m 0755 "$(command -v arp-scan)" "${bindir}/arp-scan"
    log_success "Bundled arp-scan binary"
  else
    log_warn "arp-scan not found on build host; package will rely on system installation"
  fi
}

write_control_file() {
  local control_path="$1"
  local deb_arch="$2"

  cat >"${control_path}" <<EOF
Package: ${PACKAGE_NAME}
Version: ${VERSION}
Section: misc
Priority: optional
Architecture: ${deb_arch}
Maintainer: NexusRFID Packaging <support@nexusrfid.local>
Depends: python3 (>= 3.9), systemd, sudo, dhcpcd5, network-manager, libpcap0.8
Replaces: ${PACKAGE_NAME}
Provides: ${PACKAGE_NAME}
Conflicts: ${PACKAGE_NAME}
Description: Nexus RFID Reader kiosk application
 This package installs the Nexus RFID Reader application, its Python
 virtual environment, supporting scripts, and systemd service so the
 device boots directly into the kiosk UI.
EOF
}

write_postinst() {
  local postinst_path="$1"

  cat >"${postinst_path}" <<'EOF'
#!/bin/bash
set -e

PACKAGE_ROOT="/opt/NexusRFIDReader"
SERVICE_FILE="/etc/systemd/system/nexusrfid.service"

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

TARGET_USER="$(detect_target_user)"
TARGET_UID="$(id -u "${TARGET_USER}" 2>/dev/null || echo 0)"
TARGET_HOME="$(getent passwd "${TARGET_USER}" | cut -d: -f6)"
TARGET_HOME="${TARGET_HOME:-/home/${TARGET_USER}}"
RUNTIME_DIR="/run/user/${TARGET_UID}"

mkdir -p "${TARGET_HOME}/.nexusrfid" "${TARGET_HOME}/.local/share/applications"
chown -R "${TARGET_USER}:${TARGET_USER}" "${TARGET_HOME}/.nexusrfid"

if [ ! -d "${RUNTIME_DIR}" ]; then
  install -d -m 700 -o "${TARGET_USER}" -g "${TARGET_USER}" "${RUNTIME_DIR}"
fi

find "${PACKAGE_ROOT}" -type d -exec chmod 755 {} +
if [ -d "${PACKAGE_ROOT}/scripts" ]; then
  find "${PACKAGE_ROOT}/scripts" -type f -name "*.sh" -exec chmod 755 {} +
fi
if [ -d "${PACKAGE_ROOT}/bin" ]; then
  find "${PACKAGE_ROOT}/bin" -type f -exec chmod 755 {} +
fi
chown -R "${TARGET_USER}:${TARGET_USER}" "${PACKAGE_ROOT}"

# Install desktop entry for manual launch (optional)
install -d -m 755 "${TARGET_HOME}/.local/share/applications"
cat > "${TARGET_HOME}/.local/share/applications/nexus-rfid.desktop" <<DESKTOP
[Desktop Entry]
Name=Nexus RFID Reader
Comment=Nexus RFID Reader Application
Exec=${PACKAGE_ROOT}/scripts/run_app.sh
Icon=${PACKAGE_ROOT}/ui/img/icon.ico
Terminal=false
Type=Application
Categories=Utility;
DESKTOP
chown "${TARGET_USER}:${TARGET_USER}" "${TARGET_HOME}/.local/share/applications/nexus-rfid.desktop"
chmod 644 "${TARGET_HOME}/.local/share/applications/nexus-rfid.desktop"

# Install arp-scan symlink if binary bundled
if [ -x "${PACKAGE_ROOT}/bin/arp-scan" ]; then
  install -d -m 755 /usr/local/bin
  ln -sf "${PACKAGE_ROOT}/bin/arp-scan" /usr/local/bin/arp-scan
fi

# Install/refresh systemd service
if [ -x "${PACKAGE_ROOT}/scripts/install_service.sh" ]; then
  SUDO_USER="${TARGET_USER}" HOME="${TARGET_HOME}" "${PACKAGE_ROOT}/scripts/install_service.sh"
else
  echo "install_service.sh missing in package payload" >&2
  exit 1
fi

# Patch generated service file with runtime-specific paths
if [ -f "${SERVICE_FILE}" ]; then
  sed -i "s|^Environment=HOME=.*|Environment=HOME=${TARGET_HOME}|g" "${SERVICE_FILE}"
  sed -i "s|^Environment=XAUTHORITY=.*|Environment=XAUTHORITY=${TARGET_HOME}/.Xauthority|g" "${SERVICE_FILE}"
  sed -i "s|^Environment=XDG_RUNTIME_DIR=.*|Environment=XDG_RUNTIME_DIR=${RUNTIME_DIR}|g" "${SERVICE_FILE}"
  sed -i "s|^Environment=DBUS_SESSION_BUS_ADDRESS=.*|Environment=DBUS_SESSION_BUS_ADDRESS=unix:path=${RUNTIME_DIR}/bus|g" "${SERVICE_FILE}"

  systemctl daemon-reload
  systemctl restart nexusrfid.service || systemctl start nexusrfid.service
else
  echo "Systemd service file not found at ${SERVICE_FILE}" >&2
fi

exit 0
EOF

  chmod 755 "${postinst_path}"
}

write_prerm() {
  local prerm_path="$1"
  cat >"${prerm_path}" <<'EOF'
#!/bin/bash
set -e

SERVICE="nexusrfid.service"

if systemctl list-unit-files | grep -q "^${SERVICE}"; then
  systemctl stop "${SERVICE}" || true
  systemctl disable "${SERVICE}" || true
fi

exit 0
EOF
  chmod 755 "${prerm_path}"
}

write_postrm() {
  local postrm_path="$1"
  cat >"${postrm_path}" <<'EOF'
#!/bin/bash
set -e

SERVICE_FILE="/etc/systemd/system/nexusrfid.service"

if [ "$1" = "purge" ]; then
  rm -f /usr/local/bin/arp-scan
  rm -f "${SERVICE_FILE}"
  systemctl daemon-reload || true
fi

exit 0
EOF
  chmod 755 "${postrm_path}"
}

build_deb() {
  local deb_arch="$1"
  local label="$2"

  local stage_dir="${BUILD_ROOT}/stage_${label}"
  local control_dir="${stage_dir}/DEBIAN"
  local payload_dir="${stage_dir}${INSTALL_PREFIX}"

  rm -rf "${stage_dir}"
  mkdir -p "${control_dir}" "${payload_dir}"

  log_step "Staging project for architecture ${deb_arch}"
  copy_project_payload "${PROJECT_ROOT}" "${payload_dir}"

  prepare_venv "${payload_dir}"
  bundle_arp_scan "${payload_dir}"

  write_control_file "${control_dir}/control" "${deb_arch}"
  write_postinst "${control_dir}/postinst"
  write_prerm "${control_dir}/prerm"
  write_postrm "${control_dir}/postrm"

  find "${stage_dir}" -type d -exec chmod 755 {} +
  find "${stage_dir}" -type f -name "*.sh" -exec chmod 755 {} +
  find "${payload_dir}" -type f -name "*.py" -exec chmod 644 {} +

  local output_file="${DIST_DIR}/${APP_DIR_NAME}-${VERSION}_${label}.deb"
  log_step "Building package ${output_file}"
  dpkg-deb --build --root-owner-group "${stage_dir}" "${output_file}"
  log_success "Created ${output_file}"
  BUILT_FILES+=("${output_file}")
}

main() {
  parse_args "$@"

  ensure_command python3
  ensure_command dpkg-deb
  ensure_command rsync
  ensure_command sed

  mkdir -p "${BUILD_ROOT}"

  printf '%b\n' "${PURPLE}============================================================${NC}"
  printf '%b\n' "${PURPLE}[create-pkg] Nexus RFID Reader Package Builder${NC}"
  printf '%b\n' "${PURPLE}============================================================${NC}"
  log "Building NexusRFIDReader packages (version ${VERSION})"

  for entry in "${ARCH_MATRIX[@]}"; do
    local arch="${entry%%:*}"
    local label="${entry##*:}"
    build_deb "${arch}" "${label}"
  done

  if [ "${#BUILT_FILES[@]}" -gt 0 ]; then
    local default_alias="${DIST_DIR}/${APP_DIR_NAME}-${VERSION}.deb"
    log_step "Creating convenience copy ${default_alias}"
    cp -f "${BUILT_FILES[0]}" "${default_alias}"
    BUILT_FILES+=("${default_alias}")
  fi

  log "Packages created in ${DIST_DIR}:"
  ls -1 "${DIST_DIR}"/${APP_DIR_NAME}-${VERSION}_*.deb 2>/dev/null || true
  if [ -e "${DIST_DIR}/${APP_DIR_NAME}-${VERSION}.deb" ]; then
    log_success "Default package copy: ${APP_DIR_NAME}-${VERSION}.deb"
  fi

  log_success "Packaging complete."
  printf '%b\n' "${PURPLE}============================================================${NC}"
}

main "$@"

