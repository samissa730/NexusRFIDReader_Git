#!/usr/bin/env bash
#
# network-manage-combined.sh
#
# Enterprise-grade single-file network manager for:
#   - eth1
#   - eth0
#   - wlan0
#   - EC25 SIM modem on usb0 (ECM mode)
#
# One-time install:
#   sudo ./network-manage-combined.sh install
#

set -u

LOG_TAG="[NET-ENTERPRISE]"

: "${MODEM_AT_PORT:=/dev/ttyUSB2}"

: "${DNS1:=8.8.8.8}"
: "${DNS2:=1.1.1.1}"
: "${DNS3:=9.9.9.9}"
: "${DNS4:=1.0.0.1}"
: "${DNS_TEST_HOST:=google.com}"

: "${SLEEP_SECS:=10}"
: "${USB0_DHCLIENT_TIMEOUT:=30}"
: "${USB0_WAIT_SECS:=90}"
: "${BOOT_RETRIES:=60}"
: "${BOOT_RETRY_DELAY:=5}"
: "${STABLE_SUCCESS_COUNT:=3}"
: "${DISABLE_SYSTEMD_RESOLVED:=1}"

: "${ENABLE_DEFAULT_WIFI:=false}"
: "${DEFAULT_WIFI_SSID:=}"
: "${DEFAULT_WIFI_PASSWORD:=}"
: "${DEFAULT_WIFI_PROFILE_NAME:=}"

: "${METRIC_ETH1:=100}"
: "${METRIC_ETH0:=150}"
: "${METRIC_WLAN0:=200}"
: "${METRIC_USB0:=600}"

: "${PREFER_HIGHER_PRIORITY_AFTER:=3}"

# EC25 recovery logic:
# Only reboot EC25 when usb0 is the only candidate and internet is still broken.
: "${USB0_ONLY_FAIL_THRESHOLD:=3}"
: "${MODEM_RESET_COOLDOWN_SECS:=180}"
: "${MODEM_RESET_WAIT_SECS:=45}"

SERVICE_NAME="network-manage-combined.service"
STATE_DIR="/var/lib/network-manage-combined"
STATE_FILE="${STATE_DIR}/state.env"
SCRIPT_PATH="$(readlink -f "$0")"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"

log() {
  echo "${LOG_TAG} $1"
}

have_cmd() {
  command -v "$1" >/dev/null 2>&1
}

require_root() {
  if [[ "${EUID:-0}" -ne 0 ]]; then
    log "Run with sudo"
    exit 1
  fi
}

ensure_state_dir() {
  mkdir -p "${STATE_DIR}"
}

load_state() {
  ensure_state_dir
  CURRENT_PRIMARY=""
  HIGHER_PRIORITY_SEEN=0
  USB0_ONLY_FAILS=0
  LAST_MODEM_RESET_TS=0
  if [[ -f "${STATE_FILE}" ]]; then
    # shellcheck disable=SC1090
    . "${STATE_FILE}" || true
  fi
  : "${CURRENT_PRIMARY:=}"
  : "${HIGHER_PRIORITY_SEEN:=0}"
  : "${USB0_ONLY_FAILS:=0}"
  : "${LAST_MODEM_RESET_TS:=0}"
}

save_state() {
  ensure_state_dir
  cat > "${STATE_FILE}" <<EOF
CURRENT_PRIMARY="${CURRENT_PRIMARY:-}"
HIGHER_PRIORITY_SEEN="${HIGHER_PRIORITY_SEEN:-0}"
USB0_ONLY_FAILS="${USB0_ONLY_FAILS:-0}"
LAST_MODEM_RESET_TS="${LAST_MODEM_RESET_TS:-0}"
EOF
}

iface_exists() {
  ip link show "$1" >/dev/null 2>&1
}

has_ip() {
  ip -4 addr show "$1" 2>/dev/null | grep -q 'inet '
}

get_gateway() {
  ip route show default dev "$1" 2>/dev/null | awk '/default via/ {print $3; exit}'
}

get_any_gateway_for_dev() {
  ip route show 2>/dev/null | awk -v dev="$1" '$0 ~ (" dev " dev "($| )") && $1=="default" {for(i=1;i<=NF;i++) if($i=="via"){print $(i+1); exit}}'
}

default_route_exists() {
  ip -4 route show default 2>/dev/null | grep -q .
}

can_reach_ip() {
  local dev="$1"
  ping -I "$dev" -c 1 -W 4 8.8.8.8 >/dev/null 2>&1
}

dns_ok() {
  getent hosts "${DNS_TEST_HOST}" >/dev/null 2>&1
}

internet_ok() {
  default_route_exists && dns_ok
}

resolved_active() {
  systemctl is-active systemd-resolved >/dev/null 2>&1
}

resolv_conf_has_stub() {
  grep -Eq '^[[:space:]]*nameserver[[:space:]]+127\.0\.0\.53[[:space:]]*$' /etc/resolv.conf 2>/dev/null
}

write_static_resolv_conf() {
  rm -f /etc/resolv.conf 2>/dev/null || true
  {
    printf "nameserver %s\n" "${DNS1}"
    printf "nameserver %s\n" "${DNS2}"
    printf "nameserver %s\n" "${DNS3}"
    printf "nameserver %s\n" "${DNS4}"
    printf "options timeout:2 attempts:2 rotate single-request-reopen\n"
  } >/etc/resolv.conf
}

disable_systemd_resolved_if_requested() {
  if [[ "${DISABLE_SYSTEMD_RESOLVED}" != "1" ]]; then
    return 0
  fi

  if systemctl list-unit-files 2>/dev/null | grep -q '^systemd-resolved\.service'; then
    systemctl stop systemd-resolved >/dev/null 2>&1 || true
    systemctl disable systemd-resolved >/dev/null 2>&1 || true
  fi
}

fix_dns() {
  disable_systemd_resolved_if_requested
  write_static_resolv_conf
}

push_nm_dns_to_connections() {
  have_cmd nmcli || return 0

  local con
  for con in usb0 eth1 eth0 "${DEFAULT_WIFI_PROFILE_NAME:-}"; do
    [[ -n "${con}" ]] || continue
    nmcli -t -f NAME connection show 2>/dev/null | grep -Fxq "${con}" || continue
    nmcli connection modify "${con}" \
      ipv4.dns "${DNS1} ${DNS2} ${DNS3} ${DNS4}" \
      ipv4.ignore-auto-dns yes >/dev/null 2>&1 || true
  done
}

ensure_nm_connection() {
  have_cmd nmcli || return 0
  local con_name="$1"
  local ifname="$2"
  local type="${3:-ethernet}"

  if ! nmcli -t -f NAME connection show 2>/dev/null | grep -Fxq "${con_name}"; then
    log "Creating NetworkManager connection '${con_name}' for ${ifname}"
    nmcli connection add type "${type}" ifname "${ifname}" con-name "${con_name}" >/dev/null 2>&1 || true
  fi
}

active_connection_name_for_dev() {
  have_cmd nmcli || return 1
  nmcli -t -f GENERAL.CONNECTION device show "$1" 2>/dev/null | sed -n 's/^GENERAL.CONNECTION://p' | head -n1
}

is_device_connected_to() {
  local dev="$1"
  local con="$2"
  local active
  active="$(active_connection_name_for_dev "$dev" || true)"
  [[ -n "${active}" && "${active}" == "${con}" ]]
}

ensure_metric_dev() {
  have_cmd nmcli || return 0
  local dev="$1"
  local metric="$2"
  iface_exists "$dev" || return 0

  local name
  name="$(active_connection_name_for_dev "$dev" || true)"
  if [[ -n "${name:-}" && "${name}" != "--" ]]; then
    nmcli connection modify "$name" ipv4.route-metric "${metric}" >/dev/null 2>&1 || true
  fi
}

ensure_default_wifi_profile() {
  [[ "${ENABLE_DEFAULT_WIFI}" == "true" ]] || return 0
  [[ -n "${DEFAULT_WIFI_SSID}" && -n "${DEFAULT_WIFI_PASSWORD}" && -n "${DEFAULT_WIFI_PROFILE_NAME}" ]] || return 0
  have_cmd nmcli || return 0

  if ! nmcli -t -f NAME connection show 2>/dev/null | grep -Fxq "${DEFAULT_WIFI_PROFILE_NAME}"; then
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
    ipv4.route-metric "${METRIC_WLAN0}" \
    ipv4.dns "${DNS1} ${DNS2} ${DNS3} ${DNS4}" \
    ipv4.ignore-auto-dns yes \
    ipv6.method disabled >/dev/null 2>&1 || true

  nmcli radio wifi on >/dev/null 2>&1 || true

  if ! is_device_connected_to "wlan0" "${DEFAULT_WIFI_PROFILE_NAME}"; then
    nmcli connection up "${DEFAULT_WIFI_PROFILE_NAME}" >/dev/null 2>&1 || true
  fi
}

modem_port_ready() {
  [[ -c "${MODEM_AT_PORT}" ]]
}

send_at() {
  local cmd="$1"
  local timeout_secs="${2:-4}"
  local out=""

  modem_port_ready || return 1

  stty -F "${MODEM_AT_PORT}" 115200 raw -echo -echoe -echok -echonl -icanon min 0 time 10 >/dev/null 2>&1 || true
  timeout 1 dd if="${MODEM_AT_PORT}" of=/dev/null bs=256 iflag=nonblock status=none 2>/dev/null || true

  printf "%s\r" "${cmd}" > "${MODEM_AT_PORT}"

  out="$(timeout "${timeout_secs}" stdbuf -o0 cat "${MODEM_AT_PORT}" 2>/dev/null | tr -d '\000' | sed '/^$/d' || true)"
  printf "%s\n" "${out}"
  return 0
}

at_ok() {
  send_at "AT" 3 | grep -q "OK"
}

get_usbnet_mode() {
  local rsp
  rsp="$(send_at 'AT+QCFG="usbnet"' 4 || true)"
  printf "%s\n" "${rsp}" | sed -n 's/.*+QCFG: "usbnet",\([0-9]\+\).*/\1/p' | head -n1
}

set_usbnet_ecm_if_needed() {
  modem_port_ready || return 0

  if ! at_ok; then
    log "AT port exists but modem did not answer; skipping ECM mode change this pass"
    return 0
  fi

  local mode
  mode="$(get_usbnet_mode || true)"

  if [[ "${mode:-}" == "1" ]]; then
    return 0
  fi

  log "Switching EC25 to ECM mode"
  send_at 'AT+QCFG="usbnet",1' 5 >/dev/null || true
  sleep 1
  log "Rebooting modem because usbnet mode changed"
  send_at 'AT+CFUN=1,1' 3 >/dev/null || true
  sleep 5
}

reboot_ec25_modem() {
  modem_port_ready || return 1

  if ! at_ok; then
    send_at 'AT+CFUN=1,1' 3 >/dev/null || true
    log "Cannot reboot EC25: modem AT port not responding"
    return 1
  fi

  log "Rebooting EC25 with AT+CFUN=1,1"
  send_at 'AT+CFUN=1,1' 3 >/dev/null || true

  load_state
  LAST_MODEM_RESET_TS="$(date +%s)"
  USB0_ONLY_FAILS=0
  save_state
  return 0
}

wait_for_usb0() {
  local i
  for ((i=0; i<USB0_WAIT_SECS; i++)); do
    if iface_exists usb0; then
      return 0
    fi
    sleep 1
  done
  return 1
}

ensure_usb0_profile() {
  have_cmd nmcli || return 0

  ensure_nm_connection "usb0" "usb0" "ethernet"
  nmcli connection modify usb0 \
    connection.autoconnect yes \
    connection.autoconnect-priority 10 \
    ipv4.method auto \
    ipv4.route-metric "${METRIC_USB0}" \
    ipv4.dns "${DNS1} ${DNS2} ${DNS3} ${DNS4}" \
    ipv4.ignore-auto-dns yes \
    ipv6.method disabled >/dev/null 2>&1 || true
}

renew_usb0_dhcp() {
  iface_exists usb0 || return 1

  if have_cmd nmcli; then
    if ! is_device_connected_to "usb0" "usb0"; then
      nmcli device connect usb0 >/dev/null 2>&1 || true
      nmcli connection up usb0 >/dev/null 2>&1 || true
    fi
  fi

  if have_cmd dhclient; then
    dhclient -r usb0 >/dev/null 2>&1 || true
    if timeout "${USB0_DHCLIENT_TIMEOUT}" dhclient usb0 >/tmp/network-manage-usb0-dhclient.log 2>&1; then
      log "usb0 DHCP renewed"
      return 0
    fi
    log "dhclient on usb0 failed"
    cat /tmp/network-manage-usb0-dhclient.log 2>/dev/null || true
  fi

  return 1
}

bring_up_eth_profiles() {
  have_cmd nmcli || return 0

  if iface_exists eth1; then
    ensure_nm_connection "eth1" "eth1" "ethernet"
    nmcli connection modify eth1 \
      connection.autoconnect yes \
      ipv4.method auto \
      ipv4.route-metric "${METRIC_ETH1}" \
      ipv4.dns "${DNS1} ${DNS2} ${DNS3} ${DNS4}" \
      ipv4.ignore-auto-dns yes \
      ipv6.method disabled >/dev/null 2>&1 || true

    if ! is_device_connected_to "eth1" "eth1"; then
      nmcli connection up eth1 >/dev/null 2>&1 || true
    fi
  fi

  if iface_exists eth0; then
    ensure_nm_connection "eth0" "eth0" "ethernet"
    nmcli connection modify eth0 \
      connection.autoconnect yes \
      ipv4.method auto \
      ipv4.route-metric "${METRIC_ETH0}" \
      ipv4.dns "${DNS1} ${DNS2} ${DNS3} ${DNS4}" \
      ipv4.ignore-auto-dns yes \
      ipv6.method disabled >/dev/null 2>&1 || true

    if ! is_device_connected_to "eth0" "eth0"; then
      nmcli connection up eth0 >/dev/null 2>&1 || true
    fi
  fi
}

promote_route() {
  local iface="$1"
  local metric="$2"
  local gw
  gw="$(get_gateway "$iface")"
  [[ -n "${gw}" ]] || gw="$(get_any_gateway_for_dev "$iface")"
  [[ -n "${gw}" ]] || return 1
  ip route replace default via "${gw}" dev "${iface}" metric "${metric}"
  return 0
}

remove_default_for_dev() {
  local dev="$1"
  while ip route show default dev "${dev}" 2>/dev/null | grep -q .; do
    ip route del default dev "${dev}" 2>/dev/null || break
  done
}

drop_other_defaults() {
  local keep="$1"
  local dev
  for dev in eth1 eth0 wlan0 usb0; do
    [[ "${dev}" == "${keep}" ]] && continue
    remove_default_for_dev "${dev}"
  done
}

enforce_single_default_route() {
  local primary="$1"
  case "${primary}" in
    eth1)
      promote_route eth1 "${METRIC_ETH1}" || true
      drop_other_defaults eth1
      ;;
    eth0)
      promote_route eth0 "${METRIC_ETH0}" || true
      drop_other_defaults eth0
      ;;
    wlan0)
      promote_route wlan0 "${METRIC_WLAN0}" || true
      drop_other_defaults wlan0
      ;;
    usb0)
      promote_route usb0 "${METRIC_USB0}" || true
      drop_other_defaults usb0
      ;;
    *)
      ;;
  esac
}

validate_interface() {
  local dev="$1"
  iface_exists "${dev}" || return 1
  has_ip "${dev}" || return 1
  [[ -n "$(get_gateway "${dev}")" ]] || [[ -n "$(get_any_gateway_for_dev "${dev}")" ]] || return 1
  can_reach_ip "${dev}" || return 1
  return 0
}

usb0_route_present() {
  iface_exists usb0 || return 1
  has_ip usb0 || return 1
  [[ -n "$(get_gateway usb0)" ]] || [[ -n "$(get_any_gateway_for_dev usb0)" ]] || return 1
  return 0
}

higher_priority_interface_ok() {
  validate_interface eth1 && return 0
  validate_interface eth0 && return 0
  validate_interface wlan0 && return 0
  return 1
}

interface_rank() {
  case "$1" in
    eth1) echo 1 ;;
    eth0) echo 2 ;;
    wlan0) echo 3 ;;
    usb0) echo 4 ;;
    *) echo 99 ;;
  esac
}

best_available_interface() {
  if validate_interface eth1; then echo "eth1"; return 0; fi
  if validate_interface eth0; then echo "eth0"; return 0; fi
  if validate_interface wlan0; then echo "wlan0"; return 0; fi
  if validate_interface usb0; then echo "usb0"; return 0; fi
  return 1
}

only_usb0_candidate_or_stuck() {
  higher_priority_interface_ok && return 1

  validate_interface usb0 && return 0
  usb0_route_present && return 0

  return 1
}

maybe_recover_usb0_only_failure() {
  load_state

  only_usb0_candidate_or_stuck || {
    USB0_ONLY_FAILS=0
    save_state
    return 0
  }

  if internet_ok; then
    USB0_ONLY_FAILS=0
    save_state
    return 0
  fi

  USB0_ONLY_FAILS=$((USB0_ONLY_FAILS + 1))
  log "usb0-only/stuck mode and internet still broken (${USB0_ONLY_FAILS}/${USB0_ONLY_FAIL_THRESHOLD})"
  save_state

  if (( USB0_ONLY_FAILS < USB0_ONLY_FAIL_THRESHOLD )); then
    return 0
  fi

  local now
  now="$(date +%s)"
  if (( now - LAST_MODEM_RESET_TS < MODEM_RESET_COOLDOWN_SECS )); then
    log "Skipping EC25 reboot: cooldown active"
    return 0
  fi

  reboot_ec25_modem || return 0

  log "Waiting ${MODEM_RESET_WAIT_SECS}s for EC25 to come back"
  sleep "${MODEM_RESET_WAIT_SECS}"

  wait_for_usb0 || true
  ensure_usb0_profile
  renew_usb0_dhcp || true
  fix_dns
  push_nm_dns_to_connections

  return 0
}

decide_primary_interface() {
  load_state

  local best=""
  best="$(best_available_interface || true)"

  if [[ -z "${best}" ]]; then
    if usb0_route_present && ! higher_priority_interface_ok; then
      CURRENT_PRIMARY="usb0"
      HIGHER_PRIORITY_SEEN=0
      save_state
      echo "${CURRENT_PRIMARY}"
      return 0
    fi

    CURRENT_PRIMARY=""
    HIGHER_PRIORITY_SEEN=0
    save_state
    echo ""
    return 1
  fi

  if [[ -z "${CURRENT_PRIMARY}" ]]; then
    CURRENT_PRIMARY="${best}"
    HIGHER_PRIORITY_SEEN=0
    save_state
    echo "${CURRENT_PRIMARY}"
    return 0
  fi

  if ! validate_interface "${CURRENT_PRIMARY}"; then
    if [[ "${CURRENT_PRIMARY}" == "usb0" ]] && usb0_route_present && ! higher_priority_interface_ok; then
      echo "${CURRENT_PRIMARY}"
      return 0
    fi
    CURRENT_PRIMARY="${best}"
    HIGHER_PRIORITY_SEEN=0
    save_state
    echo "${CURRENT_PRIMARY}"
    return 0
  fi

  local current_rank best_rank
  current_rank="$(interface_rank "${CURRENT_PRIMARY}")"
  best_rank="$(interface_rank "${best}")"

  if [[ "${best}" == "${CURRENT_PRIMARY}" ]]; then
    HIGHER_PRIORITY_SEEN=0
    save_state
    echo "${CURRENT_PRIMARY}"
    return 0
  fi

  if (( best_rank < current_rank )); then
    HIGHER_PRIORITY_SEEN=$((HIGHER_PRIORITY_SEEN + 1))
    if (( HIGHER_PRIORITY_SEEN >= PREFER_HIGHER_PRIORITY_AFTER )); then
      log "Switching primary from ${CURRENT_PRIMARY} to higher-priority ${best}"
      CURRENT_PRIMARY="${best}"
      HIGHER_PRIORITY_SEEN=0
    fi
  else
    HIGHER_PRIORITY_SEEN=0
  fi

  save_state
  echo "${CURRENT_PRIMARY}"
  return 0
}

repair_dns_if_broken() {
  if dns_ok; then
    return 0
  fi

  log "DNS broken; repairing"
  if resolved_active && resolv_conf_has_stub; then
    log "systemd-resolved stub detected"
  fi

  fix_dns
  push_nm_dns_to_connections

  if dns_ok; then
    log "DNS restored"
    return 0
  fi

  log "DNS still failing after repair"
  return 1
}

show_state() {
  log "---- state ----"
  ip -4 addr show 2>/dev/null || true
  ip route 2>/dev/null || true
  echo "--- /etc/resolv.conf ---"
  cat /etc/resolv.conf 2>/dev/null || true
  echo "--- nmcli device status ---"
  nmcli device status 2>/dev/null || true
  echo "--- state file ---"
  [[ -f "${STATE_FILE}" ]] && cat "${STATE_FILE}" || true
  log "--------------"
}

ensure_boot_connectivity() {
  fix_dns
  push_nm_dns_to_connections

  bring_up_eth_profiles
  ensure_default_wifi_profile

  # Only prepare SIM if no higher-priority working internet exists
  if ! higher_priority_interface_ok; then
    set_usbnet_ecm_if_needed

    if wait_for_usb0; then
      ensure_usb0_profile
      ensure_metric_dev usb0 "${METRIC_USB0}"
      if ! has_ip usb0 || [[ -z "$(get_gateway usb0)" && -z "$(get_any_gateway_for_dev usb0)" ]]; then
        renew_usb0_dhcp || true
      fi
    fi
  else
    remove_default_for_dev usb0
  fi

  return 0
}

run_network_pass() {
  fix_dns
  push_nm_dns_to_connections

  bring_up_eth_profiles
  ensure_default_wifi_profile

  ensure_metric_dev eth1 "${METRIC_ETH1}"
  ensure_metric_dev eth0 "${METRIC_ETH0}"
  ensure_metric_dev wlan0 "${METRIC_WLAN0}"
  ensure_metric_dev usb0 "${METRIC_USB0}"

  load_state

  if ! higher_priority_interface_ok; then
    if iface_exists usb0; then
      ensure_usb0_profile

      if [[ "${CURRENT_PRIMARY:-}" == "usb0" ]] || ! internet_ok || usb0_route_present; then
        if ! has_ip usb0 || [[ -z "$(get_gateway usb0)" && -z "$(get_any_gateway_for_dev usb0)" ]]; then
          log "usb0 missing IP/gateway; renewing DHCP"
          renew_usb0_dhcp || true
        fi
      fi
    else
      set_usbnet_ecm_if_needed
      wait_for_usb0 || true
      if iface_exists usb0; then
        ensure_usb0_profile
        if [[ "${CURRENT_PRIMARY:-}" == "usb0" ]] || ! internet_ok || usb0_route_present; then
          renew_usb0_dhcp || true
        fi
      fi
    fi
  else
    # A higher-priority interface has real internet, so keep SIM passive.
    remove_default_for_dev usb0
  fi

  repair_dns_if_broken || true
  maybe_recover_usb0_only_failure

  local primary=""
  primary="$(decide_primary_interface || true)"

  if [[ -n "${primary}" ]]; then
    enforce_single_default_route "${primary}"
    log "Using ${primary}"
  else
    log "No healthy interface yet"
  fi
}

run_boot_pass() {
  local i
  local stable_count=0

  for ((i=1; i<=BOOT_RETRIES; i++)); do
    log "Boot attempt ${i}/${BOOT_RETRIES}"
    ensure_boot_connectivity || true
    run_network_pass

    if internet_ok; then
      stable_count=$((stable_count + 1))
      log "Connectivity OK (${stable_count}/${STABLE_SUCCESS_COUNT})"
      if (( stable_count >= STABLE_SUCCESS_COUNT )); then
        log "Internet is stable: route + DNS OK"
        return 0
      fi
    else
      stable_count=0
      log "Connectivity not stable yet"
    fi

    sleep "${BOOT_RETRY_DELAY}"
  done

  log "Boot retries exhausted"
  show_state
  return 1
}

run_watch_loop() {
  while true; do
    run_network_pass
    sleep "${SLEEP_SECS}"
  done
}

run_initial_setup() {
  fix_dns
  bring_up_eth_profiles
  ensure_default_wifi_profile

  if ! higher_priority_interface_ok; then
    set_usbnet_ecm_if_needed
    wait_for_usb0 || true
    if iface_exists usb0; then
      ensure_usb0_profile
      renew_usb0_dhcp || true
    fi
  else
    remove_default_for_dev usb0
  fi

  push_nm_dns_to_connections
  ensure_state_dir
  log "initial-setup finished"
}

install_service() {
  log "Installing systemd service ${SERVICE_NAME}"

  cat > "/etc/systemd/system/${SERVICE_NAME}" <<EOF
[Unit]
Description=Combined Enterprise Network Manager for Ethernet WiFi and EC25 SIM
Wants=network-online.target NetworkManager.service
After=network-online.target NetworkManager.service ModemManager.service systemd-udev-settle.service
StartLimitIntervalSec=0

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=${SCRIPT_DIR}
ExecStart=${SCRIPT_PATH} watch
ExecStartPre=/bin/chmod +x ${SCRIPT_PATH}
Restart=always
RestartSec=5
Environment=MODEM_AT_PORT=${MODEM_AT_PORT}
Environment=DISABLE_SYSTEMD_RESOLVED=${DISABLE_SYSTEMD_RESOLVED}
Environment=BOOT_RETRIES=${BOOT_RETRIES}
Environment=BOOT_RETRY_DELAY=${BOOT_RETRY_DELAY}
Environment=STABLE_SUCCESS_COUNT=${STABLE_SUCCESS_COUNT}
Environment=USB0_WAIT_SECS=${USB0_WAIT_SECS}
Environment=USB0_DHCLIENT_TIMEOUT=${USB0_DHCLIENT_TIMEOUT}
Environment=SLEEP_SECS=${SLEEP_SECS}
Environment=DNS1=${DNS1}
Environment=DNS2=${DNS2}
Environment=DNS3=${DNS3}
Environment=DNS4=${DNS4}
Environment=ENABLE_DEFAULT_WIFI=${ENABLE_DEFAULT_WIFI}
Environment=DEFAULT_WIFI_SSID=${DEFAULT_WIFI_SSID}
Environment=DEFAULT_WIFI_PASSWORD=${DEFAULT_WIFI_PASSWORD}
Environment=DEFAULT_WIFI_PROFILE_NAME=${DEFAULT_WIFI_PROFILE_NAME}
Environment=METRIC_ETH1=${METRIC_ETH1}
Environment=METRIC_ETH0=${METRIC_ETH0}
Environment=METRIC_WLAN0=${METRIC_WLAN0}
Environment=METRIC_USB0=${METRIC_USB0}
Environment=PREFER_HIGHER_PRIORITY_AFTER=${PREFER_HIGHER_PRIORITY_AFTER}
Environment=USB0_ONLY_FAIL_THRESHOLD=${USB0_ONLY_FAIL_THRESHOLD}
Environment=MODEM_RESET_COOLDOWN_SECS=${MODEM_RESET_COOLDOWN_SECS}
Environment=MODEM_RESET_WAIT_SECS=${MODEM_RESET_WAIT_SECS}
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

  systemctl daemon-reload
  systemctl enable "${SERVICE_NAME}"
  systemctl restart "${SERVICE_NAME}"

  log "Service installed and started"
  systemctl --no-pager --full status "${SERVICE_NAME}" || true
}

uninstall_service() {
  log "Removing systemd service ${SERVICE_NAME}"
  systemctl stop "${SERVICE_NAME}" >/dev/null 2>&1 || true
  systemctl disable "${SERVICE_NAME}" >/dev/null 2>&1 || true
  rm -f "/etc/systemd/system/${SERVICE_NAME}"
  systemctl daemon-reload
  systemctl reset-failed >/dev/null 2>&1 || true
  rm -f "${STATE_FILE}" >/dev/null 2>&1 || true
  log "Service removed"
}

status_cmd() {
  show_state
  echo
  systemctl --no-pager --full status "${SERVICE_NAME}" 2>/dev/null || true
}

usage() {
  cat <<EOF
Usage: $(basename "$0") [install|once|watch|initial-setup|status|uninstall|help]

Commands:
  install        One-time setup: configure and install auto-start service
  once           Bring up best available internet source and wait until stable
  watch          Keep monitoring and repairing connectivity forever
  initial-setup  Prepare Ethernet/WiFi/SIM state once
  status         Show current network and service state
  uninstall      Remove installed auto-start service
  help           Show this help

Priority:
  eth1 > eth0 > wlan0 > usb0

Recommended:
  sudo ./$(basename "$0") install
EOF
}

main() {
  local cmd="${1:-install}"

  require_root

  case "${cmd}" in
    install)
      chmod +x "${SCRIPT_PATH}" >/dev/null 2>&1 || true
      run_initial_setup
      run_boot_pass || true
      install_service
      ;;
    once)
      run_boot_pass
      ;;
    watch)
      run_watch_loop
      ;;
    initial-setup)
      run_initial_setup
      ;;
    status)
      status_cmd
      ;;
    uninstall)
      uninstall_service
      ;;
    help|-h|--help)
      usage
      ;;
    *)
      usage
      exit 1
      ;;
  esac
}

main "${1:-install}"
