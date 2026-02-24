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
    echo -e "${PURPLE}[UNINSTALL]${NC} $1"
}

print_step() {
    echo -e "${CYAN}[STEP]${NC} $1"
}

# Service configuration
SERVICE_NAME="nexusrfid"
UNIT_PATH="/etc/systemd/system/${SERVICE_NAME}.service"
USB0_UNIT="/etc/systemd/system/nexus-usb0-network.service"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

echo "============================================================"
print_header "Uninstalling Nexus RFID Service"
echo "============================================================"
print_status "Service: ${SERVICE_NAME}"
print_status "Unit file: ${UNIT_PATH}"
print_status "Project root: ${PROJECT_ROOT}"
echo "============================================================"

# Check if systemd is available
if ! command -v systemctl >/dev/null 2>&1; then
    print_error "systemd (systemctl) is not available on this system"
    exit 1
fi

# Check if service exists and is running
print_step "Checking service status..."
if systemctl list-units --type=service --all | grep -q "${SERVICE_NAME}.service"; then
    if systemctl is-active --quiet "${SERVICE_NAME}.service"; then
        print_warning "Service is currently running. Stopping..."
        sudo systemctl stop "${SERVICE_NAME}.service" && print_success "Service stopped" || print_error "Failed to stop service"
    else
        print_status "Service is not running"
    fi
    
    if systemctl is-enabled --quiet "${SERVICE_NAME}.service" 2>/dev/null; then
        print_step "Disabling service from startup..."
        sudo systemctl disable "${SERVICE_NAME}.service" && print_success "Service disabled" || print_error "Failed to disable service"
    else
        print_status "Service is not enabled for startup"
    fi
else
    print_warning "Service ${SERVICE_NAME}.service not found in systemctl"
fi

# Remove service unit file
print_step "Removing service unit file..."
if [ -f "${UNIT_PATH}" ]; then
    sudo rm -f "${UNIT_PATH}"
    if [ ! -f "${UNIT_PATH}" ]; then
        print_success "Service unit file removed"
    else
        print_error "Failed to remove service unit file"
        exit 1
    fi
else
    print_warning "Service unit file not found at ${UNIT_PATH}"
fi

# Remove fallback start timer, service, and helper script
print_step "Removing nexusrfid-start-fallback timer..."
FALLBACK_TIMER="/etc/systemd/system/nexusrfid-start-fallback.timer"
FALLBACK_UNIT="/etc/systemd/system/nexusrfid-start-fallback.service"
FALLBACK_HELPER="/usr/local/bin/nexusrfid-fallback-start"
if systemctl is-enabled --quiet nexusrfid-start-fallback.timer 2>/dev/null; then
    sudo systemctl disable nexusrfid-start-fallback.timer 2>/dev/null || true
fi
sudo rm -f "${FALLBACK_TIMER}" "${FALLBACK_UNIT}" "${FALLBACK_HELPER}" 2>/dev/null || true
print_success "Fallback timer and helper removed"

# Keep nexus-usb0-network.service installed so internet (USB tethering) keeps working
# after uninstall. Only remove the main app unit.
print_step "Leaving nexus-usb0-network.service in place (keeps USB tethering internet working)..."
if [ -f "${USB0_UNIT}" ]; then
    print_success "nexus-usb0-network.service left enabled; internet over usb0 will continue to work"
else
    print_status "nexus-usb0-network.service not found (nothing to keep)"
fi

# Reload systemd daemon
print_step "Reloading systemd daemon..."
sudo systemctl daemon-reload && print_success "Systemd daemon reloaded" || print_error "Failed to reload systemd daemon"

# Optional cleanup of desktop entry
print_step "Cleaning up desktop entry..."
user="$(id -u -n)"
desktop_file="/home/${user}/.local/share/applications/nexus-rfid.desktop"
if [ -f "${desktop_file}" ]; then
    rm -f "${desktop_file}"
    print_success "Desktop entry removed"
else
    print_status "Desktop entry not found"
fi

# Final verification (nexus-usb0-network is left on purpose for internet)
print_step "Verifying uninstallation..."
if ! systemctl list-units --type=service --all | grep -q "${SERVICE_NAME}.service" && [ ! -f "${UNIT_PATH}" ]; then
    echo ""
    echo "============================================================"
    print_header "Uninstallation Complete!"
    echo "============================================================"
    print_success "Service ${SERVICE_NAME}.service has been completely removed"
    print_success "Desktop entry removed (if existed)"
    print_status "nexus-usb0-network.service was left installed so internet over usb0 keeps working"
    print_status "To remove it too: sudo systemctl disable nexus-usb0-network.service && sudo rm ${USB0_UNIT} && sudo systemctl daemon-reload"
    echo "============================================================"
else
    echo ""
    print_error "Uninstallation may not be complete. Please check manually:"
    print_status "Check service: systemctl status ${SERVICE_NAME}.service"
    print_status "Check unit file: ls -la ${UNIT_PATH}"
    exit 1
fi