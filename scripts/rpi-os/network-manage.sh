#!/usr/bin/env bash
#
# Nexus RFID — network management (extracted from
# create_pkg_rpi_fully_corrected_with_wifi_flag_and_dhclient_v3.sh.txt).
#
# Includes:
#   - Runtime logic from nexus-network-watchdog.sh (WiFi profile, usb0/dhclient, route priority)
#   - First-boot-style NM setup from DEBIAN/postinst (eth0 reader link, eth1, optional WiFi, usb0)
#
# Usage:
#   sudo ./network-manage.sh              One pass (DNS, metrics, WiFi/usb0, default route) — exits
#   sudo ./network-manage.sh watch        Loop every SLEEP_SECS (same as packaged watchdog service)
#   sudo ./network-manage.sh initial-setup
#                                         One-shot eth0/eth1/default WiFi/usb0 + resolv.conf (package postinst network block)
#
# Environment (override defaults below if needed):
#   ENABLE_DEFAULT_WIFI (default: true), DEFAULT_WIFI_SSID, DEFAULT_WIFI_PASSWORD, DEFAULT_WIFI_PROFILE_NAME
#   DNS1, DNS2, SLEEP_SECS, USB0_DHCLIENT_TIMEOUT
#
# Default WiFi matches create_pkg_rpi_fully_corrected_with_wifi_flag_and_dhclient_v3.sh.txt customer block.

set -u

LOG_TAG="[NET-MANAGE]"
: "${DNS1:=8.8.8.8}"
: "${DNS2:=1.1.1.1}"
: "${SLEEP_SECS:=20}"
: "${USB0_DHCLIENT_TIMEOUT:=25}"
: "${ENABLE_DEFAULT_WIFI:=true}"
: "${DEFAULT_WIFI_SSID:=LazerStarlink}"
: "${DEFAULT_WIFI_PASSWORD:=LLOS1105}"
: "${DEFAULT_WIFI_PROFILE_NAME:=LazerStarlink}"

log() { echo "${LOG_TAG} $1"; }

fix_dns() {
  rm -f /etc/resolv.conf 2>/dev/null || true
  printf "nameserver %s\nnameserver %s\n" "${DNS1}" "${DNS2}" >/etc/resolv.conf 2>/dev/null || true
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

  nmcli connection modify usb0 \
    connection.autoconnect yes \
    ipv4.method auto \
    ipv4.route-metric 300 \
    ipv4.dns "${DNS1} ${DNS2}" \
    ipv4.ignore-auto-dns yes >/dev/null 2>&1 || true
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
  fi
  log "dhclient usb0 failed or timed out"
  cat /tmp/nexus-dhclient-usb0.log 2>/dev/null || true
  return 1
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

# Single iteration (watchdog body once).
run_network_pass() {
  fix_dns

  ensure_metric eth1 100
  ensure_metric wlan0 200
  ensure_metric usb0 300

  ensure_wifi_profile
  ensure_usb0_connection

  local ETH1_GW WLAN0_GW USB0_GW
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
}

run_watch_loop() {
  while true; do
    run_network_pass
    sleep "${SLEEP_SECS}"
  done
}

# --- postinst-style initial NetworkManager + resolv.conf (no app/user logic) ---

ensure_nm_connection() {
  local con_name="$1"
  local ifname="$2"
  local type="${3:-ethernet}"
  if ! nmcli -t -f NAME connection show | grep -Fxq "${con_name}"; then
    log "Creating NetworkManager connection '${con_name}' for ${ifname}..."
    nmcli connection add type "${type}" ifname "${ifname}" con-name "${con_name}" >/dev/null || true
  fi
}

bounce_connection() {
  local con_name="$1"
  nmcli connection down "${con_name}" >/dev/null 2>&1 || true
  nmcli connection up "${con_name}" >/dev/null 2>&1 || true
}

configure_default_wifi_initial() {
  if [ "${ENABLE_DEFAULT_WIFI:-false}" != "true" ]; then
    log "Default WiFi preconfiguration disabled (ENABLE_DEFAULT_WIFI != true)."
    return 0
  fi

  if ! command -v nmcli >/dev/null 2>&1; then
    return 0
  fi

  if [ -z "${DEFAULT_WIFI_SSID:-}" ] || [ -z "${DEFAULT_WIFI_PASSWORD:-}" ] || [ -z "${DEFAULT_WIFI_PROFILE_NAME:-}" ]; then
    log "Default WiFi env vars incomplete; skipping WiFi profile."
    return 0
  fi

  log "Configuring default WiFi profile: ${DEFAULT_WIFI_SSID}"

  if ! nmcli -t -f NAME connection show | grep -Fxq "${DEFAULT_WIFI_PROFILE_NAME}"; then
    nmcli connection add type wifi con-name "${DEFAULT_WIFI_PROFILE_NAME}" ifname wlan0 ssid "${DEFAULT_WIFI_SSID}" >/dev/null 2>&1 || true
  fi

  nmcli connection modify "${DEFAULT_WIFI_PROFILE_NAME}" \
    802-11-wireless.ssid "${DEFAULT_WIFI_SSID}" \
    802-11-wireless.mode infrastructure \
    wifi-sec.key-mgmt wpa-psk \
    wifi-sec.psk "${DEFAULT_WIFI_PASSWORD}" \
    connection.autoconnect yes \
    connection.autoconnect-priority 50 \
    ipv4.method auto \
    ipv4.route-metric 200 \
    ipv4.dns "${DNS1} ${DNS2}" \
    ipv4.ignore-auto-dns yes || true

  nmcli radio wifi on || true
  nmcli connection up "${DEFAULT_WIFI_PROFILE_NAME}" || true
}

set_resolv_conf() {
  log "Writing /etc/resolv.conf..."
  rm -f /etc/resolv.conf
  printf "nameserver %s\nnameserver %s\n" "${DNS1}" "${DNS2}" >/etc/resolv.conf
}

run_initial_setup() {
  if [[ "${EUID:-0}" -ne 0 ]]; then
    log "initial-setup requires root (sudo)."
    exit 1
  fi

  if ! command -v nmcli >/dev/null 2>&1; then
    log "nmcli not found; only resolv.conf will be updated."
    set_resolv_conf
    exit 0
  fi

  ensure_nm_connection "eth0" "eth0" "ethernet"
  nmcli connection modify eth0 \
    connection.autoconnect yes \
    ipv4.method manual \
    ipv4.addresses "169.254.0.1/16" \
    ipv4.gateway "" \
    ipv4.dns "" \
    ipv4.ignore-auto-dns yes \
    ipv4.never-default yes \
    ipv4.route-metric 1000 \
    ipv6.method disabled || true
  bounce_connection "eth0"

  ensure_nm_connection "eth1" "eth1" "ethernet"
  nmcli connection modify eth1 \
    connection.autoconnect yes \
    ipv4.method auto \
    ipv4.route-metric 100 \
    ipv4.dns "${DNS1} ${DNS2}" \
    ipv4.ignore-auto-dns yes || true
  bounce_connection "eth1"

  configure_default_wifi_initial

  if nmcli device status | awk '{print $1}' | grep -Fxq "usb0"; then
    ensure_nm_connection "usb0" "usb0" "ethernet"
    nmcli connection modify usb0 \
      connection.autoconnect yes \
      ipv4.method auto \
      ipv4.route-metric 300 \
      ipv4.dns "${DNS1} ${DNS2}" \
      ipv4.ignore-auto-dns yes || true
    bounce_connection "usb0"
  fi

  set_resolv_conf
  log "initial-setup finished."
}

usage() {
  cat <<EOF
Usage: $(basename "$0") [command]

  (no args)     Run one network pass (DNS, NM metrics, WiFi/usb0, default route)
  once          Same as above
  watch         Loop forever every SLEEP_SECS (packaged watchdog behavior)
  initial-setup Apply eth0/eth1/optional WiFi/usb0 + resolv.conf (needs root)

WiFi (defaults match package builder; override with env):
  ENABLE_DEFAULT_WIFI=true|false  (default: true)
  DEFAULT_WIFI_SSID, DEFAULT_WIFI_PASSWORD, DEFAULT_WIFI_PROFILE_NAME
EOF
}

main() {
  local cmd="${1:-once}"
  case "$cmd" in
    -h|--help|help)
      usage
      exit 0
      ;;
    watch|--watch|daemon)
      if [[ "${EUID:-0}" -ne 0 ]]; then
        log "watch mode needs root for ip route / resolv.conf."
        exit 1
      fi
      run_watch_loop
      ;;
    once|--once|"")
      if [[ "${EUID:-0}" -ne 0 ]]; then
        log "Run with sudo for route and DNS changes."
        exit 1
      fi
      run_network_pass
      ;;
    initial-setup|--initial-setup|install-interfaces)
      run_initial_setup
      ;;
    *)
      usage
      exit 1
      ;;
  esac
}

main "${1:-once}"
