#!/usr/bin/env bash
#
# First-boot / bootstrap helper for Raspberry Pi OS images that ship maintenance scripts.
# Ensures each script is driven by a systemd timer and runs once immediately if idle.
#
# Expected image scripts (first match wins per role):
#   - Scan container watchdog: Install-scan-container.sh, install-scan-container.sh
#   - Certificate renewal:     Install-renewal-script.sh, install-renewal-script.sh
#   - Device health / network:   check-setup-device.sh
#
# Behaviour:
#   1. Resolve each script under NEXUS_SCRIPT_SEARCH_DIRS.
#   2. If a .service under /etc/systemd/system already ExecStart='s that script, use its .timer
#      (image self-registration).
#   3. Otherwise install nexus-bootstrap-<role>.service + .timer and enable them.
#   4. Enable + start timers; start the associated .service now if not running (oneshot or idle).
#
# Environment (optional):
#   NEXUS_SCRIPT_SEARCH_DIRS   Space-separated dirs (default below)
#   NEXUS_TIMER_USER           User= for generated units (default: root)
#   NEXUS_SCAN_INTERVAL        OnUnitActiveSec for scan timer (default: 5min)
#   NEXUS_RENEW_INTERVAL       For renewal timer (default: 12h)
#   NEXUS_HEALTH_INTERVAL      For health timer (default: 10min)
#   NEXUS_BOOT_DELAY           OnBootSec for first fire after boot (default: 2min)
#   NEXUS_FORCE_INSTALL_UNITS  If 1, always write nexus-bootstrap-* units (overwrite)

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m'

print_status() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[OK]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARN]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }
print_header() { echo -e "${PURPLE}[BOOTSTRAP]${NC} $1"; }
print_step() { echo -e "${CYAN}[STEP]${NC} $1"; }

: "${NEXUS_TIMER_USER:=root}"
: "${NEXUS_SCAN_INTERVAL:=5min}"
: "${NEXUS_RENEW_INTERVAL:=12h}"
: "${NEXUS_HEALTH_INTERVAL:=10min}"
: "${NEXUS_BOOT_DELAY:=2min}"
: "${NEXUS_FORCE_INSTALL_UNITS:=0}"

_DEFAULT_SEARCH=(
  "/usr/local/sbin"
  "/usr/local/bin"
  "/usr/bin"
  "/opt/nexus/bin"
  "/opt/nexus/scripts"
  "/opt/nexusrfid/scripts/rpi-os"
  "/usr/lib/nexus"
)
if [[ -z "${NEXUS_SCRIPT_SEARCH_DIRS:-}" ]]; then
  NEXUS_SCRIPT_SEARCH_DIRS="${_DEFAULT_SEARCH[*]}"
fi

# Directory containing this script (useful if you copy the trio next to bootstrap)
_THIS_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
_EXTRA_DIR="${NEXUS_EXTRA_SCRIPT_DIR:-}"

require_root() {
  if [[ "${EUID:-$(id -u)}" -ne 0 ]] && ! command -v sudo >/dev/null 2>&1; then
    print_error "Run as root or ensure sudo is available."
    exit 1
  fi
}

as_root() {
  if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
    "$@"
  else
    sudo "$@"
  fi
}

find_script() {
  local -n _names=$1
  local d name
  for name in "${_names[@]}"; do
    for d in $_NEXUS_DIRS; do
      [[ -z "$d" || ! -d "$d" ]] && continue
      if [[ -f "$d/$name" ]]; then
        echo "$d/$name"
        return 0
      fi
    done
  done
  return 1
}

# Find a unit .service whose ExecStart= line mentions the script basename or full path.
find_service_unit_for_script() {
  local script_path=$1
  local base
  base="$(basename -- "$script_path")"
  local f line
  while IFS= read -r -d '' f; do
    while IFS= read -r line || [[ -n "$line" ]]; do
      [[ "$line" =~ ^[[:space:]]*ExecStart= ]] || continue
      if [[ "$line" == *"${base}"* ]] || [[ "$line" == *"${script_path}"* ]]; then
        echo "$f"
        return 0
      fi
    done < "$f"
  done < <(find /etc/systemd/system -maxdepth 1 -name '*.service' -type f -print0 2>/dev/null)
  return 1
}

# Given /path/foo.service return foo
unit_basename() {
  basename -- "$1" .service
}

# Find timer that triggers svc_basename.service
find_timer_for_service() {
  local svc_basename=$1
  local f
  while IFS= read -r -d '' f; do
    if grep -qE "^Unit=${svc_basename}\\.service\\>" "$f" 2>/dev/null; then
      echo "$f"
      return 0
    fi
  done < <(find /etc/systemd/system -maxdepth 1 -name '*.timer' -type f -print0 2>/dev/null)
  return 1
}

write_bootstrap_units() {
  local role=$1
  local script_path=$2
  local interval=$3
  local svc="nexus-bootstrap-${role}.service"
  local tmr="nexus-bootstrap-${role}.timer"
  local svc_path="/etc/systemd/system/${svc}"
  local tmr_path="/etc/systemd/system/${tmr}"

  print_step "Installing fallback units: ${tmr}"

  as_root tee "$svc_path" >/dev/null <<EOF
[Unit]
Description=Nexus bootstrap: ${role} (${script_path})
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=${script_path}
User=${NEXUS_TIMER_USER}
EOF

  as_root tee "$tmr_path" >/dev/null <<EOF
[Unit]
Description=Timer for Nexus bootstrap ${role}

[Timer]
OnBootSec=${NEXUS_BOOT_DELAY}
OnUnitActiveSec=${interval}
AccuracySec=1min
Persistent=true

[Install]
WantedBy=timers.target
EOF

  as_root systemctl daemon-reload
  as_root systemctl enable "$tmr"
  as_root systemctl start "$tmr"
  print_success "Enabled and started ${tmr}"
}

# Image shipped a .service but no .timer — only add a timer pointing at that service.
install_bootstrap_timer_for_existing_service() {
  local role=$1
  local svc_name=$2
  local interval=$3
  local tmr="nexus-bootstrap-${role}.timer"
  local tmr_path="/etc/systemd/system/${tmr}"

  print_step "Installing timer-only unit: ${tmr} → ${svc_name}.service"

  as_root tee "$tmr_path" >/dev/null <<EOF
[Unit]
Description=Nexus bootstrap timer for ${svc_name}.service (${role})

[Timer]
OnBootSec=${NEXUS_BOOT_DELAY}
OnUnitActiveSec=${interval}
Unit=${svc_name}.service
AccuracySec=1min
Persistent=true

[Install]
WantedBy=timers.target
EOF

  as_root systemctl daemon-reload
  as_root systemctl enable "$tmr"
  as_root systemctl start "$tmr"
  print_success "Enabled and started ${tmr}"
}

ensure_timer_and_run_now() {
  local role=$1
  local script_path=$2
  local interval=$3
  local svc_unit timer_unit svc_name

  if [[ ! -x "$script_path" ]]; then
    print_warning "Script not executable, chmod +x: $script_path"
    as_root chmod +x "$script_path" || true
  fi

  if [[ "$NEXUS_FORCE_INSTALL_UNITS" == "1" ]]; then
    write_bootstrap_units "$role" "$script_path" "$interval"
    svc_name="nexus-bootstrap-${role}.service"
  else
    svc_unit="$(find_service_unit_for_script "$script_path" || true)"
    if [[ -n "$svc_unit" ]]; then
      svc_name="$(unit_basename "$svc_unit")"
      timer_unit="$(find_timer_for_service "$svc_name" || true)"
      if [[ -n "$timer_unit" ]]; then
        print_status "Using existing units for ${role}: $(basename "$timer_unit") → ${svc_name}.service"
        as_root systemctl daemon-reload
        as_root systemctl enable "$(basename "$timer_unit")"
        as_root systemctl start "$(basename "$timer_unit")"
      else
        print_warning "Service ${svc_name}.service has no matching .timer; installing bootstrap timer only."
        install_bootstrap_timer_for_existing_service "$role" "$svc_name" "$interval"
      fi
    else
      print_status "No existing systemd service references ${script_path}; installing bootstrap units."
      write_bootstrap_units "$role" "$script_path" "$interval"
      svc_name="nexus-bootstrap-${role}.service"
    fi
  fi

  # Run now if the service is not active (covers oneshot and simple that exited)
  if as_root systemctl is-active --quiet "${svc_name}" 2>/dev/null; then
    print_success "${svc_name} already active — skipping immediate start."
  else
    print_step "Starting ${svc_name} now (immediate run)"
    if as_root systemctl start "${svc_name}"; then
      print_success "Started ${svc_name}"
    else
      print_warning "systemctl start ${svc_name} failed — check logs: journalctl -u ${svc_name} -b"
    fi
  fi
}

# Optional: image scripts may support self-registration via this hook.
try_script_self_register() {
  local script_path=$1
  if [[ ! -f "$script_path" ]]; then
    return 1
  fi
  if grep -qE '^#.*NEXUS_BOOTSTRAP_SELF_REGISTER|^# NEXUS_BOOTSTRAP_SELF_REGISTER' "$script_path" 2>/dev/null; then
    print_step "Script declares NEXUS_BOOTSTRAP_SELF_REGISTER — running: $script_path --install-systemd-timer"
    if as_root bash "$script_path" --install-systemd-timer; then
      print_success "Self-register completed for $(basename "$script_path")"
      return 0
    fi
  fi
  return 1
}

main() {
  print_header "Nexus RPi device timer bootstrap"
  echo "============================================================"

  require_root

  if ! command -v systemctl >/dev/null 2>&1; then
    print_error "systemd (systemctl) not found."
    exit 1
  fi

  as_root install -d -m 755 /etc/systemd/system

  # Build search path list (extra dir + standard + this script dir)
  _NEXUS_DIRS=""
  [[ -n "$_EXTRA_DIR" ]] && _NEXUS_DIRS+="$_EXTRA_DIR "
  _NEXUS_DIRS+="$NEXUS_SCRIPT_SEARCH_DIRS "
  _NEXUS_DIRS+="$_THIS_DIR "

  local scan_names=(Install-scan-container.sh install-scan-container.sh)
  local renew_names=(Install-renewal-script.sh install-renewal-script.sh)
  local health_names=(check-setup-device.sh)

  local scan renew health

  scan="$(find_script scan_names || true)"
  renew="$(find_script renew_names || true)"
  health="$(find_script health_names || true)"

  if [[ -z "$scan" ]]; then
    print_error "Scan container script not found. Set NEXUS_SCRIPT_SEARCH_DIRS or NEXUS_EXTRA_SCRIPT_DIR."
    exit 1
  fi
  if [[ -z "$renew" ]]; then
    print_warning "Renewal script not found — skipping."
  fi
  if [[ -z "$health" ]]; then
    print_warning "Device check script not found — skipping."
  fi

  print_status "Resolved: scan=$(basename "$scan") fullpath=$scan"
  [[ -n "$renew" ]] && print_status "Resolved: renewal=$(basename "$renew") fullpath=$renew"
  [[ -n "$health" ]] && print_status "Resolved: health=$(basename "$health") fullpath=$health"

  # Self-register only when not forcing our units
  if [[ "$NEXUS_FORCE_INSTALL_UNITS" != "1" ]]; then
    try_script_self_register "$scan" || true
    [[ -n "$renew" ]] && { try_script_self_register "$renew" || true; }
    [[ -n "$health" ]] && { try_script_self_register "$health" || true; }
  fi

  ensure_timer_and_run_now "scan-container" "$scan" "$NEXUS_SCAN_INTERVAL"
  [[ -n "$renew" ]] && ensure_timer_and_run_now "cert-renewal" "$renew" "$NEXUS_RENEW_INTERVAL"
  [[ -n "$health" ]] && ensure_timer_and_run_now "check-setup-device" "$health" "$NEXUS_HEALTH_INTERVAL"

  echo "============================================================"
  print_success "Bootstrap finished."
  print_status "List timers: systemctl list-timers --all | grep -E 'nexus|scan|renew|setup'"
}

main "$@"
