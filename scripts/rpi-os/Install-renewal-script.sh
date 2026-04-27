#!/usr/bin/env bash
#
# Nexus RFID — certificate renewal via EST (step-ca / APIM), self-contained shell.
# No azure-iot-cert-renew.py: uses openssl + curl + jq only.
#
# Reads /etc/nexuslocate/config/provisioning_config.json (or NEXUS_PROVISIONING_CONFIG):
#   estServerUrl, estBootstrapToken, certPath, keyPath, registrationId
#
# Exits 0 for SKIP (no config, no EST, no cert, jq/openssl/curl missing, or cert still valid).
# Attempts renewal when cert expires within NEXUS_CERT_RENEW_THRESHOLD_SECS.
#
# Environment (optional):
#   NEXUS_PROVISIONING_CONFIG          default: /etc/nexuslocate/config/provisioning_config.json
#   NEXUS_CERT_RENEW_THRESHOLD_SECS    default: 86400 (renew if less than this many seconds left)
#
# Optional:
#   --install-systemd-timer  install nexus-cert-renewal-host.service + .timer
#
# NEXUS_BOOTSTRAP_SELF_REGISTER — bootstrap may run: this_script --install-systemd-timer

set -euo pipefail

: "${NEXUS_PROVISIONING_CONFIG:=/etc/nexuslocate/config/provisioning_config.json}"
: "${NEXUS_CERT_RENEW_THRESHOLD_SECS:=86400}"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }

install_systemd_timer() {
  if [[ "${EUID:-0}" -ne 0 ]]; then
    log "Re-run with sudo for --install-systemd-timer"
    exit 1
  fi
  local exe
  exe="$(readlink -f "$0" 2>/dev/null || realpath "$0" 2>/dev/null || echo "$0")"
  cat >/etc/systemd/system/nexus-cert-renewal-host.service <<EOF
[Unit]
Description=Nexus Azure IoT cert renewal (EST, host shell)
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
}

extract_cn_from_cert() {
  local cert=$1
  local subj
  subj="$(openssl x509 -in "$cert" -noout -subject -nameopt sep_multiline 2>/dev/null || true)"
  echo "$subj" | sed -n 's/^[[:space:]]*commonName=//p' | head -n1
}

main() {
  if [[ "${1:-}" == "--install-systemd-timer" ]]; then
    install_systemd_timer
    exit 0
  fi

  if [[ ! -f "$NEXUS_PROVISIONING_CONFIG" ]]; then
    log "SKIP: no provisioning config at $NEXUS_PROVISIONING_CONFIG"
    exit 0
  fi

  if ! command -v jq >/dev/null 2>&1; then
    log "SKIP: jq not installed (e.g. apt install jq)"
    exit 0
  fi
  if ! command -v openssl >/dev/null 2>&1; then
    log "SKIP: openssl not found"
    exit 0
  fi
  if ! command -v curl >/dev/null 2>&1; then
    log "SKIP: curl not found"
    exit 0
  fi

  local cert_path key_path reg_id est_url token
  cert_path="$(jq -r '.certPath // "/etc/nexuslocate/pki/device.crt"' "$NEXUS_PROVISIONING_CONFIG")"
  key_path="$(jq -r '.keyPath // "/etc/nexuslocate/pki/device.key"' "$NEXUS_PROVISIONING_CONFIG")"
  reg_id="$(jq -r '.registrationId // ""' "$NEXUS_PROVISIONING_CONFIG" | tr -d '\r\n')"
  est_url="$(jq -r '.estServerUrl // ""' "$NEXUS_PROVISIONING_CONFIG" | tr -d ' \t\r\n')"
  token="$(jq -r '.estBootstrapToken // ""' "$NEXUS_PROVISIONING_CONFIG" | tr -d '\r\n')"

  if [[ -z "$est_url" || -z "$token" ]]; then
    log "SKIP: estServerUrl/estBootstrapToken not set; automatic renewal disabled"
    exit 0
  fi

  if [[ ! -f "$cert_path" ]]; then
    log "SKIP: no device cert at $cert_path (provision device first)"
    exit 0
  fi

  set +e
  openssl x509 -checkend "$NEXUS_CERT_RENEW_THRESHOLD_SECS" -noout -in "$cert_path" 2>/dev/null
  local chk=$?
  set -e
  if [[ "$chk" -eq 0 ]]; then
    log "OK: cert valid for at least ${NEXUS_CERT_RENEW_THRESHOLD_SECS}s; no renewal"
    exit 0
  fi

  local cn
  cn="$(extract_cn_from_cert "$cert_path")"
  cn="${cn:-$reg_id}"
  if [[ -z "$cn" ]]; then
    log "SKIP: could not determine CN for CSR (no CN in cert and no registrationId)"
    exit 0
  fi

  log "Renewing: cert expires within ${NEXUS_CERT_RENEW_THRESHOLD_SECS}s; CN=$cn"

  local tmpdir enroll_url http_code
  tmpdir="$(mktemp -d)"
  trap 'rm -rf "$tmpdir"' EXIT

  if ! openssl req -new -newkey rsa:2048 -nodes \
    -keyout "$tmpdir/new_key.pem" -out "$tmpdir/csr.pem" \
    -subj "/CN=${cn}" 2>/dev/null; then
    log "WARN: openssl CSR generation failed"
    exit 0
  fi

  enroll_url="${est_url%/}/simpleenroll"
  http_code="$(
    curl -sS -w '%{http_code}' -o "$tmpdir/resp.bin" \
      -X POST "$enroll_url" \
      -H "Content-Type: application/pkcs10" \
      -H "Authorization: Bearer ${token}" \
      --data-binary "@$tmpdir/csr.pem" \
      -k --connect-timeout 45 --max-time 120 || echo "000"
  )"

  if [[ "$http_code" != "200" ]]; then
    log "WARN: EST POST failed http=$http_code url=$enroll_url (renewal skipped this run)"
    exit 0
  fi

  if ! openssl x509 -inform DER -in "$tmpdir/resp.bin" -out "$tmpdir/new_cert.pem" 2>/dev/null; then
    if ! openssl x509 -in "$tmpdir/resp.bin" -out "$tmpdir/new_cert.pem" 2>/dev/null; then
      log "WARN: could not parse enrollment response as DER or PEM cert"
      exit 0
    fi
  fi

  set +e
  openssl x509 -checkend 0 -noout -in "$tmpdir/new_cert.pem" 2>/dev/null
  chk=$?
  set -e
  if [[ "$chk" -ne 0 ]]; then
    log "WARN: new certificate failed basic date check"
    exit 0
  fi

  install -m 0644 -D "$tmpdir/new_cert.pem" "$cert_path"
  install -m 0600 -D "$tmpdir/new_key.pem" "$key_path"
  log "OK: wrote $cert_path and $key_path"

  if [[ -f /etc/systemd/system/azure-iot.service ]] || [[ -f /lib/systemd/system/azure-iot.service ]]; then
    if systemctl restart azure-iot.service 2>/dev/null; then
      log "OK: restarted azure-iot.service"
    else
      log "WARN: systemctl restart azure-iot.service failed"
    fi
  fi

  exit 0
}

main "$@"
