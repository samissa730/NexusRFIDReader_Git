# Docker Migration Blueprint (RFID + Azure IoT)

This blueprint describes how to replace the current systemd-based runtime
(`nexusrfid_production.service` + `azure-iot.service`) with a containerized
runtime while preserving production behavior.

## Goal

Run the same production responsibilities from Docker:

- Kiosk GUI application (`main.py` / `NexusRFIDReader`)
- Azure IoT bridge (`Azure-IoT-Connection/iot_service.py`)
- Local IPC socket between app and IoT service (`/var/run/nexus-iot.sock`)
- Host network and USB/GPS/RFID access
- Persistent device config/data

## Recommended Runtime Model

Use one production container with a startup script that launches:

1. `iot_service.py`
2. `main.py`

This keeps the same process split as today, without requiring systemd inside
the container.

Why this model:

- Easier than running systemd as PID 1 in container.
- Matches current architecture (GUI app talks to IoT process over Unix socket).
- Keeps failure handling inside one entrypoint script and Docker restart policy.

## Host Responsibilities (stay outside container)

These are host-level concerns and should not be moved into container internals:

- Bring up `usb0` (`dhclient`, route metrics, retry behavior)
- Device reboot/start-at-boot policy
- X server/Wayland session and display permissions

You can keep a small host shell/bootstrap script for these duties before
starting the container.

## Container Responsibilities

- Run IoT bridge process continuously.
- Run GUI app process continuously.
- Expose logs to stdout/stderr for `docker logs`.
- Exit non-zero if either process crashes unexpectedly (so Docker can restart).

## Required Host Mounts / Runtime Flags

- `/tmp/.X11-unix:/tmp/.X11-unix` (X socket)
- `DISPLAY=:0`
- `XAUTHORITY` bind mount (user-specific)
- `/etc/nexuslocate/config:/etc/nexuslocate/config` and `/etc/nexuslocate/pki:/etc/nexuslocate/pki` (device provisioning + certs)
- `/var/lib/nexusrfid:/var/lib/nexusrfid` (app data)
- `/var/run/nexus-iot.sock` path writable in container (tmpfs or volume)
- `/dev` device access for serial/GPS readers (minimum: required tty devices)
- `network_mode: host` (recommended to preserve current networking behavior)

## Security Posture

Start broad for validation, then tighten:

Phase 1:
- `privileged: true` (fastest path for hardware validation)

Phase 2 hardening:
- Remove privileged mode
- Add only required `devices`, `cap_add`, and writeable mounts
- Run as non-root for GUI where feasible

## OTA Strategy Options

Current code path in `iot_service.py` uses periodic `download.py` worker when
`deviceUpdate` fields exist. In Docker, choose one update model:

1. Keep existing `download.py` behavior (inside container) for continuity.
2. Replace with image-based OTA:
   - Device receives update signal
   - Pull new image tag
   - Recreate container

If switching to image-based OTA, do not run package-based updater in parallel.

## Delivery Phases

### Phase A - Technical PoC (single device)

- Build image locally.
- Run container with host network + display + device mounts.
- Validate:
  - GUI opens
  - RFID reads
  - GPS works
  - IoT socket and uploads work

### Phase B - Pilot (small fleet)

- Add versioned image tags.
- Add health checks and watchdog behavior.
- Add rollback command and documented runbook.

### Phase C - Production rollout

- Harden runtime permissions.
- Wire deployment pipeline to publish image.
- Update ops docs and incident playbooks.

## Validation Checklist

- App process starts and renders on kiosk display.
- IoT service starts and creates `/var/run/nexus-iot.sock`.
- Scan path works end-to-end (RFID -> socket -> IoT Hub).
- Reboot persistence works.
- Unplug/replug network and GPS/reader scenarios recover.
- Container restart recovers both processes.

## Files Added for Initial Implementation

- `docker/prod/Dockerfile`
- `docker/prod/entrypoint.sh`
- `docker/prod/compose.rpi.yml`
- `.dockerignore`

These are starter artifacts to accelerate Phase A.
