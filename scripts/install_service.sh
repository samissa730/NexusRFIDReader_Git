#!/usr/bin/env bash

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "${PURPLE}[INSTALL]${NC} $1"
}

print_step() {
    echo -e "${CYAN}[STEP]${NC} $1"
}

# Service configuration
SERVICE_NAME="nexusrfid"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
RUN_SCRIPT="${PROJECT_ROOT}/scripts/run_app.sh"
UNIT_PATH="/etc/systemd/system/${SERVICE_NAME}.service"

# Get actual user info
SERVICE_USER=${SUDO_USER:-$(whoami)}
SERVICE_HOME=$(getent passwd "$SERVICE_USER" 2>/dev/null | cut -d: -f6)
if [ -z "$SERVICE_HOME" ]; then
    SERVICE_HOME=$(eval echo ~$SERVICE_USER)
fi
SERVICE_UID=$(id -u "$SERVICE_USER" 2>/dev/null || echo "1000")

echo "============================================================"
print_header "Installing Nexus RFID Service"
echo "============================================================"
print_status "Service name: ${SERVICE_NAME}"
print_status "Project root: ${PROJECT_ROOT}"
print_status "Run script: ${RUN_SCRIPT}"
print_status "Unit file: ${UNIT_PATH}"
print_status "Service user: ${SERVICE_USER}"
print_status "Service home: ${SERVICE_HOME}"
print_status "Service UID: ${SERVICE_UID}"
echo "============================================================"

# Ensure systemd is available and target directory exists
print_step "Checking system compatibility..."
if ! command -v systemctl >/dev/null 2>&1; then
  print_error "systemd (systemctl) is not available on this system"
  exit 1
fi
print_success "systemd detected"

print_step "Creating systemd directory..."
sudo install -d -m 755 /etc/systemd/system
print_success "systemd directory ready"

print_step "Checking run script permissions..."
if [ ! -x "${RUN_SCRIPT}" ]; then
  print_warning "Run script not executable. Making executable..."
  chmod +x "${RUN_SCRIPT}"
  print_success "Run script made executable"
else
  print_success "Run script already executable"
fi

# Ensure XAUTHORITY file exists and has proper permissions
print_step "Setting up X11 authorization..."
if [ ! -f "${SERVICE_HOME}/.Xauthority" ]; then
    print_warning "Xauthority file not found, creating..."
    touch "${SERVICE_HOME}/.Xauthority" 2>/dev/null || true
fi
if [ -f "${SERVICE_HOME}/.Xauthority" ]; then
    chown "${SERVICE_USER}:${SERVICE_USER}" "${SERVICE_HOME}/.Xauthority" 2>/dev/null || true
    chmod 600 "${SERVICE_HOME}/.Xauthority" 2>/dev/null || true
    print_success "Xauthority file configured"
fi

# Ensure nexuslocate runtime directories exist with expected permissions
print_step "Setting up nexuslocate directories..."
sudo install -d -m 755 /etc/nexuslocate /etc/nexuslocate/config /var/log/nexuslocate /opt/nexuslocate/bin
sudo install -d -m 700 /etc/nexuslocate/pki /var/lib/nexuslocate /var/lib/nexuslocate/queue
print_success "nexuslocate directories configured"

# Install Azure IoT service so the socket exists when nexusrfid runs
AZURE_IOT_UNIT="/etc/systemd/system/azure-iot.service"
IOT_SCRIPT="${PROJECT_ROOT}/Azure-IoT-Connection/iot_service.py"
if [ -f "${IOT_SCRIPT}" ]; then
  print_step "Installing Azure IoT service (nexus-iot.sock)..."
  sudo bash -c "cat > '${AZURE_IOT_UNIT}'" <<AZUREIOT
[Unit]
Description=Azure IoT Hub Connection Service
After=network.target nexus-usb0-network.service
Wants=nexus-usb0-network.service
StartLimitIntervalSec=60
StartLimitBurst=3

[Service]
Type=simple
User=root
WorkingDirectory=${PROJECT_ROOT}
ExecStart=/usr/bin/python3 ${IOT_SCRIPT}
Restart=always
RestartSec=30
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
AZUREIOT
  if [ -f "${AZURE_IOT_UNIT}" ]; then
    print_success "Azure IoT service unit installed at ${AZURE_IOT_UNIT}"
  else
    print_warning "Could not create azure-iot.service"
  fi
else
  print_warning "Azure IoT script not found at ${IOT_SCRIPT}; nexus-iot.sock will not be created"
fi

# Install USB tethering (usb0) bring-up so internet is up at boot even if app service is down.
# This service runs after network.target, waits for usb0 to appear, then retries dhclient
# so that internet works regardless of nexusrfid.service state (running, stopped, or uninstalled).
USB0_UNIT="/etc/systemd/system/nexus-usb0-network.service"
print_step "Installing USB tethering (usb0) bring-up service..."
sudo bash -c "cat > '${USB0_UNIT}'" <<USB0UNIT
[Unit]
Description=Bring up USB tethering (usb0) for Nexus RFID at boot
After=network.target
# So network is up before we try; usb0 may enumerate a bit later

[Service]
Type=oneshot
# Wait for USB to enumerate so usb0 may exist
ExecStartPre=/bin/sleep 15
# Retry dhclient every 5s for up to 60s so we get a lease even if usb0 appears late
ExecStart=/bin/sh -c 'DHCPC=/sbin/dhclient; [ -x /usr/sbin/dhclient ] && DHCPC=/usr/sbin/dhclient; for _ in 1 2 3 4 5 6 7 8 9 10 11 12; do \$DHCPC usb0 2>/dev/null && break; sleep 5; done; true'
ExecStartPost=/bin/sh -c 'r=$(ip route show default dev usb0 2>/dev/null); [ -n "\$r" ] && gw=$(echo "\$r" | sed -n "s/.*via \([^ ]*\).*/\1/p") && [ -n "\$gw" ] && ip route replace default via "\$gw" dev usb0 metric 300 || true'
RemainAfterExit=yes
TimeoutStartSec=90

[Install]
WantedBy=multi-user.target
USB0UNIT
if [ -f "${USB0_UNIT}" ]; then
  print_success "nexus-usb0-network.service installed at ${USB0_UNIT}"
else
  print_warning "Could not create nexus-usb0-network.service"
fi

print_step "Creating systemd service unit file..."
sudo bash -c "cat > '${UNIT_PATH}'" <<UNIT
[Unit]
Description=Nexus RFID Application
# Start after graphical.target so UI is available; do not block on network/SIM (no network-online).
After=graphical.target azure-iot.service nexus-usb0-network.service
Wants=graphical.target azure-iot.service nexus-usb0-network.service

[Service]
Type=simple
WorkingDirectory=${PROJECT_ROOT}
# Optional: ensure usb0 has a lease if nexus-usb0-network got it late (no-op if already up)
ExecStartPre=/bin/bash -c '/usr/bin/sudo /sbin/dhclient usb0 2>/dev/null || true'
ExecStartPre=/bin/sleep 2
ExecStart=${RUN_SCRIPT}
Restart=always
RestartSec=5
User=${SERVICE_USER}
Environment=PYTHONUNBUFFERED=1
Environment=DISPLAY=:0
Environment=XAUTHORITY=${SERVICE_HOME}/.Xauthority
Environment=HOME=${SERVICE_HOME}
Environment=XDG_RUNTIME_DIR=/run/user/${SERVICE_UID}
Environment=DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/${SERVICE_UID}/bus

[Install]
WantedBy=graphical.target
UNIT

if [ -f "${UNIT_PATH}" ]; then
    print_success "Service unit file created successfully"
else
    print_error "Failed to create service unit file"
    exit 1
fi

# Fallback: start app 60s after boot if not already running (e.g. when no SIM/network and graphical chain is delayed)
# Use a helper script because systemctl start from inside a service's ExecStart can be blocked by systemd.
FALLBACK_UNIT="/etc/systemd/system/nexusrfid-start-fallback.service"
FALLBACK_TIMER="/etc/systemd/system/nexusrfid-start-fallback.timer"
FALLBACK_HELPER="/usr/local/bin/nexusrfid-fallback-start"
print_step "Installing fallback start helper and unit..."
sudo bash -c "cat > '${FALLBACK_HELPER}'" <<'HELPER'
#!/bin/sh
# Start nexusrfid from fallback timer; running from a script avoids systemd blocking systemctl-from-service.
exec /usr/bin/systemctl start nexusrfid.service
HELPER
sudo chmod 755 "${FALLBACK_HELPER}"
sudo bash -c "cat > '${FALLBACK_UNIT}'" <<FALLBACK
[Unit]
Description=Start Nexus RFID app if not running (fallback after boot)
After=graphical.target

[Service]
Type=oneshot
ExecStart=${FALLBACK_HELPER}
ExecStart=/bin/sleep 12
RemainAfterExit=yes
TimeoutStartSec=120

[Install]
WantedBy=multi-user.target
FALLBACK
sudo bash -c "cat > '${FALLBACK_TIMER}'" <<TIMER
[Unit]
Description=Run Nexus RFID start fallback 60s after boot
# No After=graphical so timer runs 60s after boot even without network/SIM

[Timer]
OnBootSec=25
Persistent=no
Unit=nexusrfid-start-fallback.service

[Install]
WantedBy=timers.target
TIMER
if [ -f "${FALLBACK_TIMER}" ]; then
    sudo systemctl enable nexusrfid-start-fallback.timer 2>/dev/null || true
    print_success "nexusrfid-start-fallback.timer enabled (starts app 60s after boot if not running)"
else
    print_warning "Could not create fallback timer"
fi

print_step "Reloading systemd daemon..."
sudo systemctl daemon-reload
if [ $? -eq 0 ]; then
    print_success "systemd daemon reloaded"
else
    print_error "Failed to reload systemd daemon"
    exit 1
fi

# Enable and start USB tethering (usb0) so internet is up at boot before app/IoT
if [ -f "${USB0_UNIT}" ]; then
    print_step "Enabling and starting nexus-usb0-network.service..."
    sudo systemctl enable nexus-usb0-network.service 2>/dev/null || true
    sudo systemctl start nexus-usb0-network.service 2>/dev/null || true
    if systemctl is-active --quiet nexus-usb0-network.service 2>/dev/null; then
        print_success "nexus-usb0-network.service started (usb0 bring-up at boot)"
    else
        print_warning "nexus-usb0-network.service may not have started (usb0 may not be present yet)"
    fi
fi

# Enable and start Azure IoT service first so /var/run/nexus-iot.sock exists
if [ -f "${AZURE_IOT_UNIT}" ]; then
    print_step "Enabling and starting Azure IoT service..."
    sudo systemctl enable azure-iot.service 2>/dev/null || true
    sudo systemctl start azure-iot.service 2>/dev/null || true
    sleep 3
    if systemctl is-active --quiet azure-iot.service 2>/dev/null; then
        print_success "Azure IoT service is running (nexus-iot.sock created)"
    else
        print_warning "Azure IoT service may not have started; check: sudo systemctl status azure-iot.service"
    fi
fi

print_step "Enabling service for automatic startup..."
sudo systemctl enable "${SERVICE_NAME}.service"
if systemctl is-enabled --quiet "${SERVICE_NAME}.service"; then
    print_success "Service enabled for startup"
else
    print_error "Failed to enable service"
    exit 1
fi

print_step "Starting service..."
sudo systemctl restart "${SERVICE_NAME}.service"

# Wait a moment for the service to start
sleep 2

# Verify service is running
if systemctl is-active --quiet "${SERVICE_NAME}.service"; then
    print_success "Service started successfully"
else
    print_warning "Service may not have started properly"
    print_status "Check service status with: systemctl status ${SERVICE_NAME}.service"
fi

# Display final status
echo ""
echo "============================================================"
print_header "Installation Complete!"
echo "============================================================"
print_success "Service ${SERVICE_NAME}.service installed and configured"

# Show current service status
print_step "Current service status:"
sudo systemctl status "${SERVICE_NAME}.service" --no-pager -l

echo ""
echo "============================================================"
print_header "Service Management Commands:"
echo "============================================================"
print_status "Check status:    sudo systemctl status ${SERVICE_NAME}.service"
print_status "View logs:       sudo journalctl -u ${SERVICE_NAME}.service -f"
print_status "Restart service: sudo systemctl restart ${SERVICE_NAME}.service"
print_status "Stop service:    sudo systemctl stop ${SERVICE_NAME}.service"
print_status "Disable service: sudo systemctl disable ${SERVICE_NAME}.service"
if [ -f "${AZURE_IOT_UNIT}" ]; then
echo ""
print_status "Azure IoT (nexus-iot.sock):"
print_status "  Status:  sudo systemctl status azure-iot.service"
print_status "  Logs:    sudo journalctl -u azure-iot.service -f"
print_status "  Restart: sudo systemctl restart azure-iot.service"
fi
if [ -f "${USB0_UNIT}" ]; then
echo ""
print_status "USB tethering (usb0 at boot):"
print_status "  Status:  sudo systemctl status nexus-usb0-network.service"
fi
echo ""
print_success "Service will automatically start on system boot"
echo "============================================================"