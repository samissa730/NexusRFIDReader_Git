#!/usr/bin/env bash

set -euo pipefail

# Get current directory and user info
cur_dir="$(cd "$(dirname "$0")" && pwd)"
project_root="$(cd "${cur_dir}/.." && pwd)"
user="$(id -u -n)"

echo "Setting up Nexus RFID Reader Application"
echo "Project root: ${project_root}"
echo "User: ${user}"

# Update system packages
echo "Updating system packages..."
sudo apt update -y

# Install system dependencies for Qt GUI applications
echo "Installing Qt and GUI dependencies..."
sudo apt install -y \
    libxcb-cursor0 \
    libxcb-cursor-dev \
    python3-dev \
    python3-pip \
    python3-venv \
    python3-setuptools \
    python3-wheel \
    build-essential \
    cmake \
    pkg-config \
    libgl1-mesa-dev \
    libglib2.0-dev

# Install additional system dependencies for RFID and networking
echo "Installing RFID and networking dependencies..."
sudo apt install -y \
    libusb-1.0-0-dev \
    libusb-1.0-0 \
    usbutils \
    network-manager \
    dhcpcd5 \
    i2c-tools \
    python3-serial \
    python3-requests \
    python3-numpy

# Install Python dependencies globally (not in venv)
echo "Installing Python dependencies globally..."
sudo pip3 install --break-system-packages -U pip

# Install PySide6 first as it's often a dependency for other packages
echo "Installing PySide6 (Qt for Python)..."
sudo pip3 install --break-system-packages PySide6

# Install other Python dependencies
echo "Installing remaining Python dependencies..."
sudo pip3 install --break-system-packages -r "${project_root}/requirements.txt"

# Make scripts executable
echo "Making scripts executable..."
chmod +x "${project_root}/scripts/run_app.sh"
chmod +x "${project_root}/scripts/install_service.sh"
chmod +x "${project_root}/scripts/uninstall_service.sh"

# Install the systemd service
echo "Installing systemd service..."
bash "${project_root}/scripts/install_service.sh"

# Enable I2C interface (useful for RFID readers)
echo "Enabling I2C interface..."
if ! grep -q "dtparam=i2c_arm=on" /boot/firmware/config.txt 2>/dev/null; then
    echo "dtparam=i2c_arm=on" | sudo tee -a /boot/firmware/config.txt
    echo "I2C enabled. Reboot required for changes to take effect."
fi

# Disable virtual keyboard (for kiosk mode)
echo "Disabling virtual keyboard..."
sudo raspi-config nonint do_squeekboard S3 2>/dev/null || echo "Virtual keyboard already disabled or not available"

# Set up GUI environment for the user
echo "Setting up GUI environment..."
mkdir -p "/home/${user}/.config"
mkdir -p "/home/${user}/.local/share/applications"

# Create desktop entry for manual launch (optional)
cat > "/home/${user}/.local/share/applications/nexus-rfid.desktop" <<EOL
[Desktop Entry]
Name=Nexus RFID Reader
Comment=Nexus RFID Reader Application
Exec=${project_root}/scripts/run_app.sh
Icon=${project_root}/ui/img/icon.ico
Terminal=false
Type=Application
Categories=Utility;
EOL

# Set proper permissions
chmod +x "/home/${user}/.local/share/applications/nexus-rfid.desktop"

# Check if service is running
echo "Checking service status..."
if systemctl is-active --quiet nexusrfid.service; then
    echo "✓ Nexus RFID service is running"
else
    echo "⚠ Nexus RFID service is not running. Starting..."
    sudo systemctl start nexusrfid.service
fi

# Display final status
echo ""
echo "=========================================="
echo "Setup completed successfully!"
echo "=========================================="
echo "Service status:"
sudo systemctl status nexusrfid.service --no-pager -l
echo ""
echo "To check logs: sudo journalctl -u nexusrfid.service -f"
echo "To restart service: sudo systemctl restart nexusrfid.service"
echo "To stop service: sudo systemctl stop nexusrfid.service"
echo "To uninstall: bash ${project_root}/scripts/uninstall_service.sh"
echo ""
echo "Desktop application available in Applications menu"
echo "=========================================="
