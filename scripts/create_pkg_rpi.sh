#!/usr/bin/env bash

# NexusRFIDReader Package Creation Script for Raspberry Pi
# Builds one .deb that installs:
# - the packaged app executable
# - the app service
# - EC25 modem/GPS recovery service + timer
# - DNS self-heal
# - network watchdog
# - optional default customer WiFi profile (editable below)
# - automatic dhclient fallback for usb0 in SIM-only scenarios
# - log/data directory permissions

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
NC='\033[0m'

PACKAGE_NAME="NexusRFIDReader"
PACKAGE_VERSION="1.0"
ARCHITECTURE="$(dpkg --print-architecture)"
DESCRIPTION="Nexus RFID Reader - Advanced RFID scanning and GPS tracking system"
MAINTAINER="Nexus Systems"
WEBSITE="https://nexusyms.com"

# ============================================================
# CUSTOMER DEFAULT WIFI SETTINGS
#
# Set ENABLE_DEFAULT_WIFI="true"  -> package preconfigures WiFi
# Set ENABLE_DEFAULT_WIFI="false" -> package does NOT create WiFi
#
# Change these values for future customers if needed.
# ============================================================
ENABLE_DEFAULT_WIFI="true"
DEFAULT_WIFI_SSID="LazerStarlink"
DEFAULT_WIFI_PASSWORD="LLOS1105"
DEFAULT_WIFI_PROFILE_NAME="LazerStarlink"
# ============================================================

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

APP_BIN_NAME="NexusRFIDReader"
DEB_NAME="${PACKAGE_NAME}-${PACKAGE_VERSION}"
BUILD_ROOT="${PROJECT_ROOT}/${DEB_NAME}"

print_status()  { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
print_step()    { echo -e "${CYAN}[STEP]${NC} $1"; }

echo -e "${CYAN}==============================================================${NC}"
echo -e "${CYAN}        NexusRFIDReader Package Builder${NC}"
echo -e "${CYAN}              For Raspberry Pi${NC}"
echo -e "${CYAN}==============================================================${NC}"
echo ""

if [ ! -f "main.py" ]; then
    echo -e "${RED}ERROR: Please run this script from the project root directory${NC}"
    exit 1
fi

if [ -n "${VIRTUAL_ENV:-}" ]; then
    PYTHON_BIN="${VIRTUAL_ENV}/bin/python"
    print_status "Using Python: ${PYTHON_BIN}"
    print_status "Using venv: ${VIRTUAL_ENV}"
else
    PYTHON_BIN="${PROJECT_ROOT}/.venv-build/bin/python"
    if [ -x "${PYTHON_BIN}" ]; then
        print_status "Using Python: ${PYTHON_BIN}"
        print_status "Using venv: ${PROJECT_ROOT}/.venv-build"
    else
        echo -e "${RED}ERROR: No virtual environment is active and .venv-build was not found.${NC}"
        echo -e "${YELLOW}Activate your venv first, for example:${NC}"
        echo -e "   source .venv-build/bin/activate"
        exit 1
    fi
fi

if ! "${PYTHON_BIN}" -c "import PySide6" >/dev/null 2>&1; then
    echo -e "${RED}ERROR: PySide6 is not installed in the active Python environment.${NC}"
    exit 1
fi

if ! "${PYTHON_BIN}" -m PyInstaller --version >/dev/null 2>&1; then
    echo -e "${RED}ERROR: PyInstaller is not installed in the active Python environment.${NC}"
    exit 1
fi

echo -e "${BLUE}Package Information:${NC}"
echo -e "   ${WHITE}Name:${NC} ${PACKAGE_NAME}"
echo -e "   ${WHITE}Version:${NC} ${PACKAGE_VERSION}"
echo -e "   ${WHITE}Architecture:${NC} ${ARCHITECTURE}"
echo -e "   ${WHITE}Description:${NC} ${DESCRIPTION}"
echo -e "   ${WHITE}Enable Default WiFi:${NC} ${ENABLE_DEFAULT_WIFI}"
if [ "${ENABLE_DEFAULT_WIFI}" = "true" ]; then
    echo -e "   ${WHITE}Default WiFi SSID:${NC} ${DEFAULT_WIFI_SSID}"
fi
echo ""

print_step "Cleaning old build artifacts..."
chmod -R u+rwX build dist 2>/dev/null || true
rm -rf build dist "${BUILD_ROOT}" "${PACKAGE_NAME}.spec"
print_success "Cleaned old build artifacts"

print_step "Building PyInstaller executable..."
"${PYTHON_BIN}" -m PyInstaller     --clean     --noconfirm     --onefile     --name="${APP_BIN_NAME}"     --hidden-import=PySide6     --hidden-import=shiboken6     --collect-all=PySide6     main.py

if [ ! -f "dist/${APP_BIN_NAME}" ]; then
    echo -e "${RED}ERROR: Executable build failed${NC}"
    exit 1
fi
print_success "Executable built"

print_step "Creating package directory structure..."
mkdir -p "${BUILD_ROOT}/DEBIAN"
mkdir -p "${BUILD_ROOT}/usr/local/bin"
mkdir -p "${BUILD_ROOT}/usr/share/applications"
mkdir -p "${BUILD_ROOT}/usr/share/icons/hicolor/512x512/apps"
mkdir -p "${BUILD_ROOT}/etc/systemd/system"
print_success "Directory structure created"

print_step "Copying application files..."
cp "dist/${APP_BIN_NAME}" "${BUILD_ROOT}/usr/local/bin/${APP_BIN_NAME}"
if [ -f "ui/img/icon.ico" ]; then
    cp "ui/img/icon.ico" "${BUILD_ROOT}/usr/share/icons/hicolor/512x512/apps/${PACKAGE_NAME}.ico"
fi
print_success "Application files copied"

print_step "Writing recovery helper scripts into package..."
cat > "${BUILD_ROOT}/usr/local/bin/nexus-ec25-recover.sh" <<'EOF'
#!/usr/bin/env bash
set -u

LOG_TAG="[EC25-RECOVER]"
MODEM_PORT="${MODEM_PORT:-/dev/ttyUSB2}"
DNS1="8.8.8.8"
DNS2="1.1.1.1"
LOCK_FILE="/run/nexus-ec25-recover.lock"

log() { echo "${LOG_TAG} $1"; }

exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
  log "Another recovery process is already running. Exiting."
  exit 0
fi

ensure_dns() {
  rm -f /etc/resolv.conf 2>/dev/null || true
  printf "nameserver %s
nameserver %s
" "${DNS1}" "${DNS2}" > /etc/resolv.conf 2>/dev/null || true
}

has_working_usb0_internet() {
  ip -4 addr show usb0 >/dev/null 2>&1 || return 1
  ping -I usb0 -c 1 -W 5 8.8.8.8 >/dev/null 2>&1
}

ensure_nm_usb0_profile() {
  command -v nmcli >/dev/null 2>&1 || return 0
  if ! nmcli -t -f NAME connection show | grep -Fxq "usb0"; then
    nmcli connection add type ethernet ifname usb0 con-name usb0 >/dev/null 2>&1 || true
  fi
  nmcli connection modify usb0     connection.autoconnect yes     ipv4.method auto     ipv4.route-metric 300     ipv4.dns "${DNS1} ${DNS2}"     ipv4.ignore-auto-dns yes >/dev/null 2>&1 || true
}

bring_up_usb0() {
  command -v nmcli >/dev/null 2>&1 || return 0
  ensure_nm_usb0_profile
  nmcli device connect usb0 >/dev/null 2>&1 || true
  nmcli connection up usb0 >/dev/null 2>&1 || true
}

wait_for_port() {
  local timeout="${1:-60}"
  local i
  for ((i=0; i<timeout; i++)); do
    [ -e "${MODEM_PORT}" ] && return 0
    sleep 1
  done
  return 1
}

setup_serial() {
  stty -F "${MODEM_PORT}" 115200 raw -echo -echoe -echok -echoctl -echoke 2>/dev/null || true
  timeout 1 cat "${MODEM_PORT}" >/dev/null 2>&1 || true
}

send_at() {
  local cmd="$1"
  local wait_s="${2:-2}"
  printf '%s
' "${cmd}" > "${MODEM_PORT}"
  sleep "${wait_s}"
  timeout 3 cat "${MODEM_PORT}" 2>/dev/null || true
}

gps_enabled() {
  local out
  out="$(send_at 'AT+QGPS?' 2 || true)"
  echo "${out}" | grep -Eq '\+QGPS:\s*1'
}

ecm_enabled() {
  local out
  out="$(send_at 'AT+QCFG="usbnet"' 2 || true)"
  echo "${out}" | grep -q '"usbnet",1'
}

enable_gps() {
  log "Enabling GPS with AT+QGPS=1"
  send_at 'AT+QGPS=1' 2 >/dev/null || true
}

switch_to_ecm() {
  log "EC25 not in ECM mode. Sending AT+QCFG="usbnet",1"
  send_at 'AT+QCFG="usbnet",1' 2 >/dev/null || true
  log "Rebooting modem with AT+CFUN=1,1"
  send_at 'AT+CFUN=1,1' 2 >/dev/null || true
}

recover_modem() {
  log "lsusb output:"
  lsusb || true
  log "lsusb -t output:"
  lsusb -t || true

  if ! wait_for_port 60; then
    log "Modem port ${MODEM_PORT} not found."
    exit 0
  fi

  setup_serial

  local at_out
  at_out="$(send_at 'AT' 1 || true)"
  if ! echo "${at_out}" | grep -q 'OK'; then
    log "AT test did not return OK."
  fi

  if ! ecm_enabled; then
    switch_to_ecm
    sleep 25
    if ! wait_for_port 60; then
      log "Modem port did not come back after ECM reboot."
      exit 0
    fi
    setup_serial
  else
    log "EC25 already in ECM mode."
  fi

  log "CPIN response:"
  send_at 'AT+CPIN?' 2 || true
  log "CEREG response:"
  send_at 'AT+CEREG?' 2 || true
  log "QNWINFO response:"
  send_at 'AT+QNWINFO' 2 || true
  log "CGDCONT response:"
  send_at 'AT+CGDCONT?' 2 || true

  if ! gps_enabled; then
    enable_gps
  else
    log "GPS already enabled."
  fi

  local i
  for i in $(seq 1 24); do
    if ip link show usb0 >/dev/null 2>&1 || nmcli device status | awk '{print $1}' | grep -Fxq "usb0"; then
      log "usb0 detected."
      break
    fi
    sleep 5
  done

  bring_up_usb0
  ensure_dns

  if has_working_usb0_internet; then
    log "usb0 internet is working."
  else
    log "usb0 exists but internet is still not working."
  fi
}

main() {
  ensure_dns

  if has_working_usb0_internet; then
    log "usb0 internet already healthy. Checking GPS only."
    if wait_for_port 15; then
      setup_serial
      if ! gps_enabled; then
        enable_gps
      fi
    fi
    exit 0
  fi

  log "SIM/GPS recovery triggered."
  recover_modem
}

main "$@"
EOF
chmod 755 "${BUILD_ROOT}/usr/local/bin/nexus-ec25-recover.sh"

cat > "${BUILD_ROOT}/usr/local/bin/nexus-network-watchdog.sh" <<'EOF'
#!/usr/bin/env bash
set -u

LOG_TAG="[NET-WATCHDOG]"
DNS1="8.8.8.8"
DNS2="1.1.1.1"
SLEEP_SECS=20
USB0_DHCLIENT_TIMEOUT=25

log() { echo "${LOG_TAG} $1"; }

fix_dns() {
  rm -f /etc/resolv.conf 2>/dev/null || true
  printf "nameserver %s
nameserver %s
" "${DNS1}" "${DNS2}" > /etc/resolv.conf 2>/dev/null || true
}

iface_exists() {
  ip link show "$1" >/dev/null 2>&1
}

has_ip() {
  ip -4 addr show "$1" 2>/dev/null | grep -q "inet "
}

get_gateway() {
  ip route show default dev "$1" 2>/dev/null | awk '/default via/ {print $3; exit}'
}

can_reach_ip() {
  ping -I "$1" -c 1 -W 3 8.8.8.8 >/dev/null 2>&1
}

ensure_metric() {
  local con="$1"
  local metric="$2"
  nmcli connection modify "$con" ipv4.route-metric "$metric" >/dev/null 2>&1 || true
}

ensure_wifi_profile() {
  local enable_default_wifi="${ENABLE_DEFAULT_WIFI:-false}"
  local ssid="${DEFAULT_WIFI_SSID:-}"
  local password="${DEFAULT_WIFI_PASSWORD:-}"
  local profile="${DEFAULT_WIFI_PROFILE_NAME:-}"
  local current_wifi_name=""

  [ "${enable_default_wifi}" = "true" ] || return 0
  [ -n "${ssid}" ] || return 0
  [ -n "${password}" ] || return 0
  [ -n "${profile}" ] || return 0
  command -v nmcli >/dev/null 2>&1 || return 0

  if ! nmcli -t -f NAME connection show | grep -Fxq "${profile}"; then
    nmcli connection add type wifi con-name "${profile}" ifname wlan0 ssid "${ssid}" >/dev/null 2>&1 || true
  fi

  nmcli connection modify "${profile}" \
    802-11-wireless.ssid "${ssid}" \
    802-11-wireless.mode infrastructure \
    wifi-sec.key-mgmt wpa-psk \
    wifi-sec.psk "${password}" \
    connection.autoconnect yes \
    connection.autoconnect-priority 50 \
    ipv4.method auto \
    ipv4.route-metric 200 \
    ipv4.dns "${DNS1} ${DNS2}" \
    ipv4.ignore-auto-dns yes >/dev/null 2>&1 || true

  nmcli radio wifi on >/dev/null 2>&1 || true

  current_wifi_name="$(nmcli -t -f GENERAL.CONNECTION device show wlan0 2>/dev/null | sed -n 's/^GENERAL.CONNECTION://p' | head -n1)"
  if [ "${current_wifi_name}" = "${profile}" ] && has_ip wlan0; then
    return 0
  fi

  if [ "${current_wifi_name}" != "${profile}" ]; then
    nmcli connection up "${profile}" >/dev/null 2>&1 || true
    return 0
  fi

  if ! can_reach_ip wlan0; then
    nmcli connection up "${profile}" >/dev/null 2>&1 || true
  fi
}

ensure_usb0_nm_profile() {
  command -v nmcli >/dev/null 2>&1 || return 0

  if ! nmcli -t -f NAME connection show | grep -Fxq "usb0"; then
    nmcli connection add type ethernet ifname usb0 con-name usb0 >/dev/null 2>&1 || true
  fi

  nmcli connection modify usb0     connection.autoconnect yes     ipv4.method auto     ipv4.route-metric 300     ipv4.dns "${DNS1} ${DNS2}"     ipv4.ignore-auto-dns yes >/dev/null 2>&1 || true
}

renew_usb0_with_dhclient() {
  if ! iface_exists usb0; then
    return 0
  fi

  if ! command -v dhclient >/dev/null 2>&1; then
    log "dhclient not installed; cannot force usb0 DHCP lease"
    return 1
  fi

  log "Attempting dhclient recovery for usb0..."
  dhclient -r usb0 >/dev/null 2>&1 || true

  if timeout "${USB0_DHCLIENT_TIMEOUT}" dhclient usb0 >/tmp/nexus-dhclient-usb0.log 2>&1; then
    log "dhclient obtained/renewed lease on usb0"
    ip route | grep usb0 || true
    return 0
  else
    log "dhclient usb0 failed or timed out"
    cat /tmp/nexus-dhclient-usb0.log 2>/dev/null || true
    return 1
  fi
}

ensure_usb0_connection() {
  if iface_exists usb0 || nmcli device status 2>/dev/null | awk '{print $1}' | grep -Fxq "usb0"; then
    ensure_usb0_nm_profile

    nmcli device connect usb0 >/dev/null 2>&1 || true
    nmcli connection up usb0 >/dev/null 2>&1 || true

    if iface_exists usb0; then
      if ! has_ip usb0; then
        log "usb0 exists but has no IPv4 address; forcing dhclient"
        renew_usb0_with_dhclient || true
      elif [ -z "$(get_gateway usb0)" ]; then
        log "usb0 has IPv4 but no default gateway; forcing dhclient"
        renew_usb0_with_dhclient || true
      fi
    fi
  fi
}

promote_route() {
  local iface="$1"
  local metric="$2"
  local gw
  gw="$(get_gateway "$iface")"
  [ -n "${gw}" ] || return 1
  ip route replace default via "${gw}" dev "${iface}" metric "${metric}"
  return 0
}

while true; do
  fix_dns

  ensure_metric eth1 100
  ensure_metric wlan0 200
  ensure_metric usb0 300

  ensure_wifi_profile
  ensure_usb0_connection

  ETH1_GW="$(get_gateway eth1)"
  WLAN0_GW="$(get_gateway wlan0)"
  USB0_GW="$(get_gateway usb0)"

  if has_ip eth1 && [ -n "${ETH1_GW}" ] && can_reach_ip eth1; then
    promote_route eth1 100 || true
    ip route del default dev wlan0 2>/dev/null || true
    ip route del default dev usb0 2>/dev/null || true
    log "Using eth1 via ${ETH1_GW}"
  elif has_ip wlan0 && [ -n "${WLAN0_GW}" ] && can_reach_ip wlan0; then
    promote_route wlan0 200 || true
    ip route del default dev eth1 2>/dev/null || true
    ip route del default dev usb0 2>/dev/null || true
    log "Using wlan0 via ${WLAN0_GW}"
  else
    if iface_exists usb0 && { ! has_ip usb0 || [ -z "${USB0_GW}" ]; }; then
      log "No healthy Ethernet/WiFi. Trying to bring up usb0 automatically..."
      renew_usb0_with_dhclient || true
      USB0_GW="$(get_gateway usb0)"
    fi

    if has_ip usb0 && [ -n "${USB0_GW}" ] && can_reach_ip usb0; then
      promote_route usb0 300 || true
      ip route del default dev eth1 2>/dev/null || true
      ip route del default dev wlan0 2>/dev/null || true
      log "Using usb0 via ${USB0_GW}"
    else
      log "No healthy internet interface yet"
    fi
  fi

  sleep "${SLEEP_SECS}"
done
EOF
chmod 755 "${BUILD_ROOT}/usr/local/bin/nexus-network-watchdog.sh"

cat > "${BUILD_ROOT}/usr/local/bin/nexus-dns-fix.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
rm -f /etc/resolv.conf
printf "nameserver 8.8.8.8
nameserver 1.1.1.1
" > /etc/resolv.conf
EOF
chmod 755 "${BUILD_ROOT}/usr/local/bin/nexus-dns-fix.sh"
print_success "Recovery helper scripts and services written"

cat > "${BUILD_ROOT}/etc/systemd/system/nexus-ec25-recover.service" <<'EOF'
[Unit]
Description=Nexus EC25 GPS/SIM Recovery
After=NetworkManager.service network-online.target
Wants=NetworkManager.service network-online.target
StartLimitIntervalSec=0

[Service]
Type=oneshot
ExecStart=/usr/local/bin/nexus-ec25-recover.sh
TimeoutStartSec=300
EOF

cat > "${BUILD_ROOT}/etc/systemd/system/nexus-ec25-recover.timer" <<'EOF'
[Unit]
Description=Run Nexus EC25 GPS/SIM Recovery every 5 minutes

[Timer]
OnBootSec=20
OnUnitActiveSec=5min
Persistent=true
Unit=nexus-ec25-recover.service

[Install]
WantedBy=timers.target
EOF

cat > "${BUILD_ROOT}/etc/systemd/system/nexus-network-watchdog.service" <<'EOF'
[Unit]
Description=Nexus Network Watchdog
After=NetworkManager.service network-online.target nexus-ec25-recover.service
Wants=NetworkManager.service network-online.target
StartLimitIntervalSec=0

[Service]
Type=simple
ExecStart=/usr/local/bin/nexus-network-watchdog.sh
Restart=always
RestartSec=20
Environment=ENABLE_DEFAULT_WIFI=__ENABLE_DEFAULT_WIFI__
Environment=DEFAULT_WIFI_SSID=__DEFAULT_WIFI_SSID__
Environment=DEFAULT_WIFI_PASSWORD=__DEFAULT_WIFI_PASSWORD__
Environment=DEFAULT_WIFI_PROFILE_NAME=__DEFAULT_WIFI_PROFILE_NAME__

[Install]
WantedBy=multi-user.target
EOF

cat > "${BUILD_ROOT}/etc/systemd/system/nexus-dns-fix.service" <<'EOF'
[Unit]
Description=Nexus DNS Self-Heal
After=network-online.target NetworkManager.service
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/nexus-dns-fix.sh

[Install]
WantedBy=multi-user.target
EOF
print_success "Helper service files created"

print_step "Creating app systemd service file..."
cat > "${BUILD_ROOT}/etc/systemd/system/nexusrfid_production.service" <<'EOL'
[Unit]
Description=Nexus RFID Application
After=graphical.target nexus-dns-fix.service nexus-network-watchdog.service
Wants=graphical.target nexus-dns-fix.service nexus-network-watchdog.service

[Service]
Type=simple
ExecStartPre=/bin/sleep 2
ExecStart=/usr/local/bin/NexusRFIDReader
Restart=always
RestartSec=5
User=__SERVICE_USER__
Environment=PYTHONUNBUFFERED=1
Environment=DISPLAY=:0
Environment=XAUTHORITY=__XAUTHORITY_PATH__
Environment=HOME=__HOME_DIR__
Environment=XDG_RUNTIME_DIR=__XDG_RUNTIME_DIR__
Environment=DBUS_SESSION_BUS_ADDRESS=__DBUS_SESSION_BUS_ADDRESS__

[Install]
WantedBy=graphical.target
EOL
print_success "App systemd service created"

print_step "Creating desktop entry..."
cat > "${BUILD_ROOT}/usr/share/applications/${PACKAGE_NAME}.desktop" <<EOL
[Desktop Entry]
Version=1.0
Name=Nexus RFID Reader
Comment=Advanced RFID scanning and GPS tracking system
Exec=/usr/local/bin/NexusRFIDReader
Icon=${PACKAGE_NAME}
Terminal=false
Type=Application
Categories=Utility;Office;
Keywords=RFID;GPS;Inventory;Tracking;
StartupNotify=true
EOL
print_success "Desktop entry created"

print_step "Creating package control file..."
cat > "${BUILD_ROOT}/DEBIAN/control" <<EOL
Package: ${PACKAGE_NAME,,}
Version: ${PACKAGE_VERSION}
Section: utils
Priority: optional
Architecture: ${ARCHITECTURE}
Maintainer: ${MAINTAINER} <support@nexusyms.com>
Homepage: ${WEBSITE}
Depends: libxcb-xinerama0, libx11-xcb1, libxcb1, libxfixes3, libxi6, libxrender1, libxcb-render0, libxcb-shape0, libxcb-xfixes0, libglib2.0-0, libdbus-1-3, x11-xserver-utils, python3, systemd, sudo, network-manager, sed, isc-dhcp-client
Description: ${DESCRIPTION}
 This application provides advanced RFID scanning capabilities with GPS tracking,
 real-time data processing, and cloud synchronization. It's designed for inventory
 management and asset tracking in industrial environments.
 .
 Features:
  * Real-time RFID tag scanning
  * GPS location tracking
  * SQLite database storage
  * Cloud API integration
  * Configurable filtering options
  * Automatic data synchronization
  * User-friendly GUI interface
  * Systemd service for automatic startup and monitoring
  * Integrated EC25 modem/GPS recovery
  * Integrated network watchdog and DNS self-heal
  * Optional preconfigured customer WiFi support
  * Automatic dhclient fallback for usb0
EOL
print_success "Control file created"

print_step "Creating post-install script..."
cat > "${BUILD_ROOT}/DEBIAN/postinst" <<'EOL'
#!/bin/bash
set -e

echo "Setting up NexusRFIDReader environment..."

DNS1="8.8.8.8"
DNS2="1.1.1.1"
ENABLE_DEFAULT_WIFI="__ENABLE_DEFAULT_WIFI__"
DEFAULT_WIFI_SSID="__DEFAULT_WIFI_SSID__"
DEFAULT_WIFI_PASSWORD="__DEFAULT_WIFI_PASSWORD__"
DEFAULT_WIFI_PROFILE_NAME="__DEFAULT_WIFI_PROFILE_NAME__"

ensure_nm_connection() {
    local con_name="$1"
    local ifname="$2"
    local type="${3:-ethernet}"
    if ! nmcli -t -f NAME connection show | grep -Fxq "${con_name}"; then
        echo "Creating NetworkManager connection '${con_name}' for ${ifname}..."
        nmcli connection add type "${type}" ifname "${ifname}" con-name "${con_name}" >/dev/null || true
    fi
}

set_resolv_conf() {
    echo "Writing /etc/resolv.conf..."
    rm -f /etc/resolv.conf
    cat > /etc/resolv.conf <<EOF2
nameserver ${DNS1}
nameserver ${DNS2}
EOF2
}

bounce_connection() {
    local con_name="$1"
    nmcli connection down "${con_name}" >/dev/null 2>&1 || true
    nmcli connection up "${con_name}" >/dev/null 2>&1 || true
}

configure_default_wifi() {
    if [ "${ENABLE_DEFAULT_WIFI}" != "true" ]; then
        echo "Default WiFi preconfiguration disabled."
        return 0
    fi

    if ! command -v nmcli >/dev/null 2>&1; then
        return 0
    fi

    if [ -z "${DEFAULT_WIFI_SSID}" ] || [ -z "${DEFAULT_WIFI_PASSWORD}" ] || [ -z "${DEFAULT_WIFI_PROFILE_NAME}" ]; then
        return 0
    fi

    echo "Configuring default WiFi profile: ${DEFAULT_WIFI_SSID}"

    if ! nmcli -t -f NAME connection show | grep -Fxq "${DEFAULT_WIFI_PROFILE_NAME}"; then
        nmcli connection add type wifi con-name "${DEFAULT_WIFI_PROFILE_NAME}" ifname wlan0 ssid "${DEFAULT_WIFI_SSID}" >/dev/null 2>&1 || true
    fi

    nmcli connection modify "${DEFAULT_WIFI_PROFILE_NAME}"         802-11-wireless.ssid "${DEFAULT_WIFI_SSID}"         802-11-wireless.mode infrastructure         wifi-sec.key-mgmt wpa-psk         wifi-sec.psk "${DEFAULT_WIFI_PASSWORD}"         connection.autoconnect yes         connection.autoconnect-priority 50         ipv4.method auto         ipv4.route-metric 200         ipv4.dns "${DNS1} ${DNS2}"         ipv4.ignore-auto-dns yes || true

    nmcli radio wifi on || true
    nmcli connection up "${DEFAULT_WIFI_PROFILE_NAME}" || true
}

SERVICE_USER=""
if [ -n "${SUDO_USER:-}" ]; then
    SERVICE_USER="$SUDO_USER"
elif [ -n "${USER:-}" ] && [ "$USER" != "root" ]; then
    SERVICE_USER="$USER"
else
    for user_dir in /home/*; do
        if [ -d "$user_dir" ]; then
            user_name=$(basename "$user_dir")
            if id "$user_name" &>/dev/null; then
                SERVICE_USER="$user_name"
                break
            fi
        fi
    done
fi

if [ -z "$SERVICE_USER" ]; then
    SERVICE_USER=$(getent passwd | awk -F: '$3 >= 1000 && $1 != "nobody" {print $1; exit}')
fi

if [ -z "$SERVICE_USER" ] || ! id "$SERVICE_USER" &>/dev/null; then
    echo "ERROR: Could not determine a valid user for the service."
    exit 1
fi

echo "Using user for service: $SERVICE_USER"

SERVICE_UID=$(id -u "$SERVICE_USER")
SERVICE_HOME=$(eval echo ~"$SERVICE_USER")
SERVICE_XAUTHORITY="${SERVICE_HOME}/.Xauthority"
SERVICE_XDG_RUNTIME_DIR="/run/user/${SERVICE_UID}"
SERVICE_DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/${SERVICE_UID}/bus"

mkdir -p "${SERVICE_HOME}/.nexusrfid"
touch "${SERVICE_HOME}/.nexusrfid/NexusRFIDReader.log" || true
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${SERVICE_HOME}/.nexusrfid"
chmod 755 "${SERVICE_HOME}/.nexusrfid"
chmod 664 "${SERVICE_HOME}/.nexusrfid/NexusRFIDReader.log" 2>/dev/null || true

touch "${SERVICE_XAUTHORITY}" 2>/dev/null || true
chown "${SERVICE_USER}:${SERVICE_USER}" "${SERVICE_XAUTHORITY}" 2>/dev/null || true
chmod 600 "${SERVICE_XAUTHORITY}" 2>/dev/null || true

if command -v nmcli >/dev/null 2>&1; then
    ensure_nm_connection "eth0" "eth0" "ethernet"
    nmcli connection modify eth0         connection.autoconnect yes         ipv4.method manual         ipv4.addresses "169.254.0.1/16"         ipv4.gateway ""         ipv4.dns ""         ipv4.ignore-auto-dns yes         ipv4.never-default yes         ipv4.route-metric 1000         ipv6.method disabled || true
    bounce_connection "eth0"

    ensure_nm_connection "eth1" "eth1" "ethernet"
    nmcli connection modify eth1         connection.autoconnect yes         ipv4.method auto         ipv4.route-metric 100         ipv4.dns "${DNS1} ${DNS2}"         ipv4.ignore-auto-dns yes || true
    bounce_connection "eth1"

    configure_default_wifi

    if nmcli device status | awk '{print $1}' | grep -Fxq "usb0"; then
        ensure_nm_connection "usb0" "usb0" "ethernet"
        nmcli connection modify usb0             connection.autoconnect yes             ipv4.method auto             ipv4.route-metric 300             ipv4.dns "${DNS1} ${DNS2}"             ipv4.ignore-auto-dns yes || true
        bounce_connection "usb0"
    fi
fi

set_resolv_conf

SERVICE_FILE="/etc/systemd/system/nexusrfid_production.service"
WATCHDOG_FILE="/etc/systemd/system/nexus-network-watchdog.service"

sed -i "s|__SERVICE_USER__|${SERVICE_USER}|g" "${SERVICE_FILE}"
sed -i "s|__XAUTHORITY_PATH__|${SERVICE_XAUTHORITY}|g" "${SERVICE_FILE}"
sed -i "s|__HOME_DIR__|${SERVICE_HOME}|g" "${SERVICE_FILE}"
sed -i "s|__XDG_RUNTIME_DIR__|${SERVICE_XDG_RUNTIME_DIR}|g" "${SERVICE_FILE}"
sed -i "s|__DBUS_SESSION_BUS_ADDRESS__|${SERVICE_DBUS_SESSION_BUS_ADDRESS}|g" "${SERVICE_FILE}"

sed -i "s|__ENABLE_DEFAULT_WIFI__|${ENABLE_DEFAULT_WIFI}|g" "${WATCHDOG_FILE}"
sed -i "s|__DEFAULT_WIFI_SSID__|${DEFAULT_WIFI_SSID}|g" "${WATCHDOG_FILE}"
sed -i "s|__DEFAULT_WIFI_PASSWORD__|${DEFAULT_WIFI_PASSWORD}|g" "${WATCHDOG_FILE}"
sed -i "s|__DEFAULT_WIFI_PROFILE_NAME__|${DEFAULT_WIFI_PROFILE_NAME}|g" "${WATCHDOG_FILE}"

systemctl daemon-reload

systemctl enable nexus-dns-fix.service >/dev/null 2>&1 || true
systemctl start nexus-dns-fix.service >/dev/null 2>&1 || true

systemctl enable nexus-ec25-recover.timer >/dev/null 2>&1 || true
systemctl start nexus-ec25-recover.service >/dev/null 2>&1 || true
systemctl start nexus-ec25-recover.timer >/dev/null 2>&1 || true

systemctl enable nexus-network-watchdog.service >/dev/null 2>&1 || true
systemctl start nexus-network-watchdog.service >/dev/null 2>&1 || true

systemctl enable nexusrfid_production.service

echo "Starting service..."
if systemctl start nexusrfid_production.service; then
    sleep 2
    if systemctl is-active --quiet nexusrfid_production.service; then
        echo "Service is running"
    else
        echo "WARNING: Service may not have started properly. Check: systemctl status nexusrfid_production.service"
    fi
else
    echo "WARNING: Failed to start service. Check: systemctl status nexusrfid_production.service"
fi

if command -v update-desktop-database &> /dev/null; then
    update-desktop-database /usr/share/applications
fi

if command -v gtk-update-icon-cache &> /dev/null; then
    gtk-update-icon-cache -f -t /usr/share/icons/hicolor
fi

echo ""
echo "NexusRFIDReader installation completed successfully!"
echo "Service will run as user: $SERVICE_USER"
if [ "${ENABLE_DEFAULT_WIFI}" = "true" ]; then
  echo "Default WiFi profile: ${DEFAULT_WIFI_PROFILE_NAME} (${DEFAULT_WIFI_SSID})"
else
  echo "Default WiFi preconfiguration: disabled"
fi
echo "To check service status: sudo systemctl status nexusrfid_production.service"
echo "To view logs: sudo journalctl -u nexusrfid_production.service -f"
EOL
chmod 0755 "${BUILD_ROOT}/DEBIAN/postinst"

sed -i "s|__ENABLE_DEFAULT_WIFI__|${ENABLE_DEFAULT_WIFI}|g" "${BUILD_ROOT}/DEBIAN/postinst"
sed -i "s|__DEFAULT_WIFI_SSID__|${DEFAULT_WIFI_SSID}|g" "${BUILD_ROOT}/DEBIAN/postinst"
sed -i "s|__DEFAULT_WIFI_PASSWORD__|${DEFAULT_WIFI_PASSWORD}|g" "${BUILD_ROOT}/DEBIAN/postinst"
sed -i "s|__DEFAULT_WIFI_PROFILE_NAME__|${DEFAULT_WIFI_PROFILE_NAME}|g" "${BUILD_ROOT}/DEBIAN/postinst"
sed -i "s|__ENABLE_DEFAULT_WIFI__|${ENABLE_DEFAULT_WIFI}|g" "${BUILD_ROOT}/etc/systemd/system/nexus-network-watchdog.service"
sed -i "s|__DEFAULT_WIFI_SSID__|${DEFAULT_WIFI_SSID}|g" "${BUILD_ROOT}/etc/systemd/system/nexus-network-watchdog.service"
sed -i "s|__DEFAULT_WIFI_PASSWORD__|${DEFAULT_WIFI_PASSWORD}|g" "${BUILD_ROOT}/etc/systemd/system/nexus-network-watchdog.service"
sed -i "s|__DEFAULT_WIFI_PROFILE_NAME__|${DEFAULT_WIFI_PROFILE_NAME}|g" "${BUILD_ROOT}/etc/systemd/system/nexus-network-watchdog.service"
print_success "Watchdog service placeholders replaced at build time"
print_success "Post-installation script created"

print_step "Creating pre-removal script..."
cat > "${BUILD_ROOT}/DEBIAN/prerm" <<'EOL'
#!/bin/bash

echo "Stopping NexusRFIDReader service..."

for unit in   nexusrfid_production.service   nexus-network-watchdog.service   nexus-ec25-recover.timer   nexus-ec25-recover.service   nexus-dns-fix.service
do
  if systemctl is-active --quiet "$unit" 2>/dev/null; then
    systemctl stop "$unit" || true
  fi
  if systemctl is-enabled --quiet "$unit" 2>/dev/null; then
    systemctl disable "$unit" || true
  fi
done

systemctl daemon-reload
pkill -f "NexusRFIDReader" || true

echo "NexusRFIDReader services stopped and disabled."
EOL
chmod 0755 "${BUILD_ROOT}/DEBIAN/prerm"
print_success "Pre-removal script created"

print_step "Creating post-removal script..."
cat > "${BUILD_ROOT}/DEBIAN/postrm" <<'EOL'
#!/bin/bash

rm -f /etc/systemd/system/nexus-dns-fix.service 2>/dev/null || true
rm -f /etc/systemd/system/nexus-network-watchdog.service 2>/dev/null || true
rm -f /etc/systemd/system/nexus-ec25-recover.service 2>/dev/null || true
rm -f /etc/systemd/system/nexus-ec25-recover.timer 2>/dev/null || true
rm -f /usr/local/bin/nexus-dns-fix.sh 2>/dev/null || true
rm -f /usr/local/bin/nexus-network-watchdog.sh 2>/dev/null || true
rm -f /usr/local/bin/nexus-ec25-recover.sh 2>/dev/null || true

systemctl daemon-reload 2>/dev/null || true
echo "Cleanup completed."
EOL
chmod 0755 "${BUILD_ROOT}/DEBIAN/postrm"
print_success "Post-removal script created"

print_step "Building the .deb package..."
dpkg-deb --build "${BUILD_ROOT}"
print_success "Package built successfully"

print_step "Cleaning up build folder..."
rm -rf "${BUILD_ROOT}"
print_success "Build folder cleaned up"

echo ""
echo -e "${GREEN}==============================================================${NC}"
echo -e "${GREEN}            PACKAGE CREATED SUCCESSFULLY!${NC}"
echo -e "${GREEN}==============================================================${NC}"
echo ""
echo -e "${WHITE}Package File:${NC} ${DEB_NAME}.deb"
echo -e "${WHITE}Package Size:${NC} $(du -h "${DEB_NAME}.deb" | cut -f1)"
echo ""
echo -e "${CYAN}Installation Instructions:${NC}"
echo -e "   ${YELLOW}1.${NC} Install the package:"
echo -e "      ${WHITE}sudo apt install ./${DEB_NAME}.deb${NC}"
echo ""
echo -e "   ${YELLOW}2.${NC} Reboot to validate startup:"
echo -e "      ${WHITE}sudo reboot${NC}"
echo ""
echo -e "${PURPLE}Customer WiFi settings to edit later:${NC}"
echo -e "   • ENABLE_DEFAULT_WIFI"
echo -e "   • DEFAULT_WIFI_SSID"
echo -e "   • DEFAULT_WIFI_PASSWORD"
echo -e "   • DEFAULT_WIFI_PROFILE_NAME"
echo ""
echo -e "${GREEN}Ready for deployment!${NC}"
