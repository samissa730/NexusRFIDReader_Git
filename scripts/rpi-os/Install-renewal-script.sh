#!/usr/bin/env bash
#
# Nexus RFID — certificate renewal via EST (step-ca / APIM EST URL).
# Delegates to Azure-IoT-Connection/azure-iot-cert-renew.py (same logic as azure-iot-cert-renew.service).
#
# Config: /etc/azureiotpnp/provisioning_config.json (estServerUrl, estBootstrapToken, certPath, keyPath).
#
# Environment (optional):
#   NEXUS_CERT_RENEW_THRESHOLD_SECS  passed as --threshold (default: 86400)
#   NEXUS_PROJECT_ROOT               search path for repo copy (default: /opt/nexusrfid)
#   NEXUS_AZURE_IOT_DIR              override dir containing azure-iot-cert-renew.py and est_client.py
#
# Optional:
#   --install-systemd-timer  install nexus-cert-renewal-host.service + .timer wrapping this script
#
# NEXUS_BOOTSTRAP_SELF_REGISTER — bootstrap may run: this_script --install-systemd-timer

set -euo pipefail

: "${NEXUS_CERT_RENEW_THRESHOLD_SECS:=86400}"
: "${NEXUS_PROJECT_ROOT:=/opt/nexusrfid}"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }

resolve_renew_script() {
  if [[ -n "${NEXUS_AZURE_IOT_DIR:-}" && -f "${NEXUS_AZURE_IOT_DIR}/azure-iot-cert-renew.py" ]]; then
    echo "${NEXUS_AZURE_IOT_DIR}/azure-iot-cert-renew.py"
    return 0
  fi
  local candidates=(
    "/opt/azure-iot/azure-iot-cert-renew.py"
    "${NEXUS_PROJECT_ROOT}/Azure-IoT-Connection/azure-iot-cert-renew.py"
  )
  local c
  for c in "${candidates[@]}"; do
    if [[ -f "$c" ]]; then
      echo "$c"
      return 0
    fi
  done
  return 1
}

resolve_pythonpath() {
  local py=$1
  local dir
  dir="$(dirname "$py")"
  echo "$dir"
}

main() {
  if [[ "${1:-}" == "--install-systemd-timer" ]]; then
    if [[ "${EUID:-0}" -ne 0 ]]; then
      log "Re-run with sudo for --install-systemd-timer"
      exit 1
    fi
    local exe
    exe="$(readlink -f "$0" 2>/dev/null || realpath "$0" 2>/dev/null || echo "$0")"
    cat >/etc/systemd/system/nexus-cert-renewal-host.service <<EOF
[Unit]
Description=Nexus Azure IoT cert renewal (host wrapper)
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=root
ExecStart=$exe
StandardOutput=journal
StandardError=journal
EOF
    cat >/etc/systemd/system/nexus-cert-renewal-host.timer <<EOF
[Unit]
Description=Timer for Nexus cert renewal

[Timer]
OnBootSec=5min
OnUnitActiveSec=12h
AccuracySec=5min
Persistent=true
RandomizedDelaySec=300

[Install]
WantedBy=timers.target
EOF
    systemctl daemon-reload
    systemctl enable nexus-cert-renewal-host.timer
    systemctl start nexus-cert-renewal-host.timer
    log "Installed nexus-cert-renewal-host.timer"
    exit 0
  fi

  local renew_py
  if ! renew_py="$(resolve_renew_script)"; then
    log "ERROR: azure-iot-cert-renew.py not found. Set NEXUS_AZURE_IOT_DIR or install under /opt/azure-iot."
    exit 1
  fi

  local est_dir
  est_dir="$(resolve_pythonpath "$renew_py")"
  log "Using $renew_py (PYTHONPATH=$est_dir)"

  if [[ ! -f /etc/azureiotpnp/provisioning_config.json ]]; then
    log "SKIP: No /etc/azureiotpnp/provisioning_config.json"
    exit 0
  fi

  export PYTHONPATH="${est_dir}${PYTHONPATH:+:$PYTHONPATH}"
  exec /usr/bin/python3 "$renew_py" --threshold "$NEXUS_CERT_RENEW_THRESHOLD_SECS"
}

main "$@"
