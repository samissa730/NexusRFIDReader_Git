#!/usr/bin/env bash
#
# Nexus RFID — device health: RFID reader link (antenna path), Wi‑Fi, USB tether (usb0),
# and default-route metrics aligned with scripts/install_service.sh (usb0 metric 300).
#
# Defaults match settings.py / rfid_discovery: eth0 + 169.254.0.0/16 reader IPs.
#
# Environment (optional):
#   NEXUS_RFID_IFACE          default: eth0
#   NEXUS_RFID_HOSTS          space-separated ping targets (default: 169.254.10.1 169.254.1.1)
#   NEXUS_WIFI_IFACE          default: wlan0
#   NEXUS_USB_IFACE           default: usb0
#   NEXUS_WIFI_METRIC         default: 200 (lower = preferred for internet)
#   NEXUS_USB_METRIC          default: 300
#   NEXUS_CONFIG_JSON         default: ~/.nexusrfid/config.json of invoking user or pi
#   NEXUS_CHECK_STRICT        if 1, exit 1 when RFID ping fails
#
# Optional:
#   --install-systemd-timer   install nexus-check-setup-device.service + .timer
#
# NEXUS_BOOTSTRAP_SELF_REGISTER

set -euo pipefail

: "${NEXUS_RFID_IFACE:=eth0}"
: "${NEXUS_RFID_HOSTS:=169.254.10.1 169.254.1.1}"
: "${NEXUS_WIFI_IFACE:=wlan0}"
: "${NEXUS_USB_IFACE:=usb0}"
: "${NEXUS_WIFI_METRIC:=200}"
: "${NEXUS_USB_METRIC:=300}"
: "${NEXUS_CHECK_STRICT:=0}"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }

iface_up() {
  local if=$1
  ip link show "$if" 2>/dev/null | grep -q "state UP"
}

iface_has_carrier() {
  local if=$1
  ip link show "$if" 2>/dev/null | grep -q "LOWER_UP"
}

ping_via() {
  local if=$1
  local host=$2
  ping -c 1 -W 3 -I "$if" "$host" >/dev/null 2>&1
}

rfid_hosts_from_config() {
  local cfg=${NEXUS_CONFIG_JSON:-}
  if [[ -z "$cfg" ]]; then
    local u="${SUDO_USER:-${USER:-pi}}"
    local home
    home="$(getent passwd "$u" 2>/dev/null | cut -d: -f6 || true)"
    [[ -z "$home" ]] && home="/home/$u"
    cfg="${home}/.nexusrfid/config.json"
  fi
  if [[ ! -f "$cfg" ]]; then
    return 1
  fi
  if ! command -v jq >/dev/null 2>&1; then
    return 1
  fi
  local h
  h="$(jq -r '.rfid_config.host // empty' "$cfg" 2>/dev/null || true)"
  [[ -n "$h" ]] && echo "$h"
}

ensure_usb0_lease() {
  local DHCPC=/sbin/dhclient
  [[ -x /usr/sbin/dhclient ]] && DHCPC=/usr/sbin/dhclient
  if iface_up "$NEXUS_USB_IFACE" || ip link show "$NEXUS_USB_IFACE" >/dev/null 2>&1; then
    $DHCPC "$NEXUS_USB_IFACE" 2>/dev/null || true
  fi
}

# Match nexus-usb0-network.service: prefer explicit default via usb0 with metric NEXUS_USB_METRIC
apply_usb0_default_metric() {
  local r gw
  r="$(ip route show default dev "$NEXUS_USB_IFACE" 2>/dev/null || true)"
  [[ -z "$r" ]] && return 0
  gw="$(echo "$r" | sed -n 's/.*via \([^ ]*\).*/\1/p' | head -1)"
  [[ -z "$gw" ]] && return 0
  ip route replace default via "$gw" dev "$NEXUS_USB_IFACE" metric "$NEXUS_USB_METRIC" 2>/dev/null || true
}

apply_wifi_default_metric() {
  local r gw
  r="$(ip route show default dev "$NEXUS_WIFI_IFACE" 2>/dev/null || true)"
  [[ -z "$r" ]] && return 0
  gw="$(echo "$r" | sed -n 's/.*via \([^ ]*\).*/\1/p' | head -1)"
  [[ -z "$gw" ]] && return 0
  ip route replace default via "$gw" dev "$NEXUS_WIFI_IFACE" metric "$NEXUS_WIFI_METRIC" 2>/dev/null || true
}

check_rfid_path() {
  local ok=1
  if ! iface_has_carrier "$NEXUS_RFID_IFACE" && ! iface_up "$NEXUS_RFID_IFACE"; then
    log "WARN: $NEXUS_RFID_IFACE is down or no carrier (RFID / antenna path)."
    ok=0
  else
    log "OK: $NEXUS_RFID_IFACE link up."
  fi

  local hosts=($NEXUS_RFID_HOSTS)
  local extra
  extra="$(rfid_hosts_from_config || true)"
  [[ -n "$extra" ]] && hosts+=("$extra")

  local h hit=0
  for h in "${hosts[@]}"; do
    [[ -z "$h" ]] && continue
    if ping_via "$NEXUS_RFID_IFACE" "$h"; then
      log "OK: ping $h via $NEXUS_RFID_IFACE"
      hit=1
      break
    fi
  done

  if [[ "$hit" -eq 0 ]]; then
    log "WARN: No response from RFID hosts via $NEXUS_RFID_IFACE (${hosts[*]})."
    ok=0
  fi

  if command -v arp-scan >/dev/null 2>&1 && iface_up "$NEXUS_RFID_IFACE"; then
    log "INFO: arp-scan 169.254.0.0/16 on $NEXUS_RFID_IFACE (first lines):"
    arp-scan --interface "$NEXUS_RFID_IFACE" 169.254.0.0/16 2>/dev/null | head -20 || true
  fi

  echo "$ok"
}

check_wifi() {
  if ! ip link show "$NEXUS_WIFI_IFACE" >/dev/null 2>&1; then
    log "INFO: No $NEXUS_WIFI_IFACE (Wi‑Fi optional)."
    return 0
  fi
  if iface_up "$NEXUS_WIFI_IFACE"; then
    log "OK: $NEXUS_WIFI_IFACE is up."
  else
    log "WARN: $NEXUS_WIFI_IFACE present but not UP."
  fi
}

install_systemd_timer() {
  if [[ "${EUID:-0}" -ne 0 ]]; then
    log "Re-run with sudo for --install-systemd-timer"
    exit 1
  fi
  local exe
  exe="$(readlink -f "$0" 2>/dev/null || realpath "$0" 2>/dev/null || echo "$0")"
  cat >/etc/systemd/system/nexus-check-setup-device.service <<EOF
[Unit]
Description=Nexus device network / RFID health check
After=network.target

[Service]
Type=oneshot
ExecStart=$exe
StandardOutput=journal
StandardError=journal
EOF
  cat >/etc/systemd/system/nexus-check-setup-device.timer <<EOF
[Unit]
Description=Timer for Nexus device check

[Timer]
OnBootSec=2min
OnUnitActiveSec=10min
AccuracySec=1min
Persistent=true

[Install]
WantedBy=timers.target
EOF
  systemctl daemon-reload
  systemctl enable nexus-check-setup-device.timer
  systemctl start nexus-check-setup-device.timer
  log "Installed nexus-check-setup-device.timer"
}

main() {
  if [[ "${1:-}" == "--install-systemd-timer" ]]; then
    install_systemd_timer
    exit 0
  fi

  if [[ "${EUID:-0}" -ne 0 ]]; then
    log "WARN: Not root — dhclient / ip route metric tweaks may be skipped; run with sudo for full fixes."
  fi

  check_wifi

  if [[ "${EUID:-0}" -eq 0 ]]; then
    ensure_usb0_lease
    apply_wifi_default_metric
    apply_usb0_default_metric
    log "OK: Default route metrics applied (wifi=$NEXUS_WIFI_METRIC usb0=$NEXUS_USB_METRIC where routes exist)."
  fi

  local rfid_ok
  rfid_ok="$(check_rfid_path)"
  if [[ "$rfid_ok" != "1" && "$NEXUS_CHECK_STRICT" == "1" ]]; then
    log "ERROR: Strict mode: RFID path check failed."
    exit 1
  fi

  log "Device check finished."
}

main "$@"
