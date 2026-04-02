#!/usr/bin/env bash
#
# Nexus RFID — pull/run the production container (matches docker/prod/compose.rpi.yml).
# Intended to run periodically via systemd timer (see scripts/bootstrap-rpi-device-timers.sh).
#
# Behaviour:
#   - Uses docker, or podman if docker is missing.
#   - If NEXUS_COMPOSE_FILE is set and exists: `compose pull` + `compose up -d`.
#   - Else: pull NEXUS_CONTAINER_IMAGE, recreate container if image changed, not running, or unhealthy.
#
# Environment (optional):
#   NEXUS_COMPOSE_FILE       e.g. /opt/nexusrfid/docker/prod/compose.rpi.yml
#   NEXUS_CONTAINER_IMAGE    default: docker.io/nexusrfid/nexusrfid:prod
#   NEXUS_CONTAINER_NAME     default: nexusrfid-prod
#   DISPLAY                  default: :0
#   XAUTHORITY               default: /home/pi/.Xauthority
#   NEXUS_PI_USER            default: pi (for XAUTHORITY path)
#
# Optional self-register for bootstrap (see scripts/bootstrap-rpi-device-timers.sh):
#   --install-systemd-timer  install nexus-scan-container.service + .timer

set -euo pipefail

# NEXUS_BOOTSTRAP_SELF_REGISTER

: "${NEXUS_CONTAINER_IMAGE:=docker.io/nexusrfid/nexusrfid:prod}"
: "${NEXUS_CONTAINER_NAME:=nexusrfid-prod}"
: "${NEXUS_PI_USER:=pi}"
: "${DISPLAY:=:0}"
: "${XAUTHORITY:=/home/${NEXUS_PI_USER}/.Xauthority}"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }

ctr_cmd() {
  if command -v docker >/dev/null 2>&1; then
    echo docker
  elif command -v podman >/dev/null 2>&1; then
    echo podman
  else
    log "ERROR: Neither docker nor podman found."
    exit 1
  fi
}

compose_up() {
  local compose_file=$1
  local dir
  dir="$(cd "$(dirname "$compose_file")" && pwd)"
  local base
  base="$(basename "$compose_file")"
  log "Compose mode: pull + up in $dir ($base)"
  ( cd "$dir" && $CTR compose -f "$base" pull && $CTR compose -f "$base" up -d --remove-orphans )
}

container_run_id() {
  $CTR inspect --format '{{.Image}}' "$NEXUS_CONTAINER_NAME" 2>/dev/null || true
}

image_id() {
  $CTR inspect --format '{{.Id}}' "$NEXUS_CONTAINER_IMAGE" 2>/dev/null || true
}

container_state() {
  $CTR inspect --format '{{.State.Status}}' "$NEXUS_CONTAINER_NAME" 2>/dev/null || echo "missing"
}

run_container_raw() {
  log "Starting container $NEXUS_CONTAINER_NAME from $NEXUS_CONTAINER_IMAGE"
  $CTR rm -f "$NEXUS_CONTAINER_NAME" 2>/dev/null || true
  # Mirrors docker/prod/compose.rpi.yml
  $CTR run -d \
    --name "$NEXUS_CONTAINER_NAME" \
    --restart always \
    --network host \
    --privileged \
    -e "DISPLAY=${DISPLAY}" \
    -e "XAUTHORITY=${XAUTHORITY}" \
    -e QT_X11_NO_MITSHM=1 \
    -v /tmp/.X11-unix:/tmp/.X11-unix \
    -v /etc/azureiotpnp:/etc/azureiotpnp \
    -v /var/lib/nexusrfid:/var/lib/nexusrfid \
    -v "${XAUTHORITY}:${XAUTHORITY}:ro" \
    -v /dev:/dev \
    "$NEXUS_CONTAINER_IMAGE"
}

ensure_raw() {
  log "Pulling $NEXUS_CONTAINER_IMAGE ..."
  $CTR pull "$NEXUS_CONTAINER_IMAGE"

  local running_img latest_img state
  running_img="$(container_run_id)"
  latest_img="$(image_id)"
  state="$(container_state)"

  if [[ "$state" == "running" && -n "$running_img" && -n "$latest_img" && "$running_img" == "$latest_img" ]]; then
    log "OK: Container running on current local image."
    return 0
  fi

  if [[ "$state" == "running" ]]; then
    log "Recreating: new image or refresh needed (state=$state)."
  elif [[ "$state" == "missing" ]]; then
    log "Container absent; creating."
  else
    log "Container state=$state; recreating."
  fi

  run_container_raw
  log "OK: Container $NEXUS_CONTAINER_NAME is up."
}

install_systemd_timer() {
  local svc="/etc/systemd/system/nexus-scan-container.service"
  local tmr="/etc/systemd/system/nexus-scan-container.timer"
  local exe
  exe="$(readlink -f "$0" 2>/dev/null || realpath "$0" 2>/dev/null || echo "$0")"
  if [[ "${EUID:-0}" -ne 0 ]]; then
    log "Re-run with sudo for --install-systemd-timer"
    exit 1
  fi
  cat >"$svc" <<EOF
[Unit]
Description=Nexus RFID container pull/run watchdog
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=$exe
StandardOutput=journal
StandardError=journal
EOF
  cat >"$tmr" <<EOF
[Unit]
Description=Timer for Nexus container watchdog

[Timer]
OnBootSec=3min
OnUnitActiveSec=5min
AccuracySec=1min
Persistent=true

[Install]
WantedBy=timers.target
EOF
  systemctl daemon-reload
  systemctl enable nexus-scan-container.timer
  systemctl start nexus-scan-container.timer
  log "Installed and started nexus-scan-container.timer"
}

main() {
  if [[ "${1:-}" == "--install-systemd-timer" ]]; then
    install_systemd_timer
    exit 0
  fi

  CTR="$(ctr_cmd)"
  log "Runtime: $CTR"

  if [[ -n "${NEXUS_COMPOSE_FILE:-}" && -f "$NEXUS_COMPOSE_FILE" ]]; then
    compose_up "$NEXUS_COMPOSE_FILE"
    log "OK: compose up complete."
    exit 0
  fi

  ensure_raw
}

main "$@"
