#!/bin/bash

# NexusRFIDReader Package Creation Script for Raspberry Pi
# This script creates a .deb package for easy installation

set -e  # Exit on any error

# Colors for beautiful output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
NC='\033[0m' # No Color

# Define package variables
PACKAGE_NAME=NexusRFIDReader
PACKAGE_VERSION=1.0
ARCHITECTURE=$(dpkg --print-architecture)
DESCRIPTION="Nexus RFID Reader - Advanced RFID scanning and GPS tracking system"
MAINTAINER="Nexus Systems"
WEBSITE="https://nexusyms.com"

echo -e "${CYAN}==============================================================${NC}"
echo -e "${CYAN}        NexusRFIDReader Package Builder${NC}"
echo -e "${CYAN}              For Raspberry Pi${NC}"
echo -e "${CYAN}==============================================================${NC}"
echo ""

# Check if we're in the right directory
if [ ! -f "main.py" ] || [ ! -f "NexusRFIDReader.spec" ]; then
    echo -e "${RED}ERROR: Please run this script from the project root directory${NC}"
    echo -e "${YELLOW}   Expected files: main.py, NexusRFIDReader.spec${NC}"
    exit 1
fi

echo -e "${BLUE}Package Information:${NC}"
echo -e "   ${WHITE}Name:${NC} $PACKAGE_NAME"
echo -e "   ${WHITE}Version:${NC} $PACKAGE_VERSION"
echo -e "   ${WHITE}Architecture:${NC} $ARCHITECTURE"
echo -e "   ${WHITE}Description:${NC} $DESCRIPTION"
echo ""

# Step 1: Build PyInstaller executable
echo -e "${YELLOW}Step 1: Building PyInstaller executable...${NC}"
if command -v pyinstaller &> /dev/null; then
    echo -e "   ${GREEN}SUCCESS${NC} PyInstaller found"
    pyinstaller --clean --onefile --icon=ui/img/icon.ico --name=NexusRFIDReader main.py
    echo -e "   ${GREEN}SUCCESS${NC} Executable built successfully"
else
    echo -e "   ${RED}ERROR: PyInstaller not found. Installing...${NC}"
    pip3 install pyinstaller
    pyinstaller --clean --onefile --icon=ui/img/icon.ico --name=NexusRFIDReader main.py
    echo -e "   ${GREEN}SUCCESS${NC} PyInstaller installed and executable built"
fi

# Check if executable was created
if [ ! -f "dist/NexusRFIDReader" ]; then
    echo -e "${RED}ERROR: Executable not created successfully${NC}"
    exit 1
fi

echo ""

# Step 2: Create directory structure
echo -e "${YELLOW}Step 2: Creating package directory structure...${NC}"
mkdir -p ${PACKAGE_NAME}-${PACKAGE_VERSION}/DEBIAN
mkdir -p ${PACKAGE_NAME}-${PACKAGE_VERSION}/usr/local/bin
mkdir -p ${PACKAGE_NAME}-${PACKAGE_VERSION}/usr/share/applications
mkdir -p ${PACKAGE_NAME}-${PACKAGE_VERSION}/usr/share/icons/hicolor/512x512/apps
mkdir -p ${PACKAGE_NAME}-${PACKAGE_VERSION}/etc/systemd/system
mkdir -p ${PACKAGE_NAME}-${PACKAGE_VERSION}/etc/default
echo -e "   ${GREEN}SUCCESS${NC} Directory structure created"

# Step 3: Copy files to package
echo -e "${YELLOW}Step 3: Copying application files...${NC}"
cp dist/NexusRFIDReader ${PACKAGE_NAME}-${PACKAGE_VERSION}/usr/local/bin/
cp ui/img/icon.ico ${PACKAGE_NAME}-${PACKAGE_VERSION}/usr/share/icons/hicolor/512x512/apps/${PACKAGE_NAME}.ico
echo -e "   ${GREEN}SUCCESS${NC} Application files copied"

# Step 4: Create monitoring script
echo -e "${YELLOW}Step 4: Creating application monitoring script...${NC}"
cat > ${PACKAGE_NAME}-${PACKAGE_VERSION}/usr/local/bin/monitor_nexus_rfid.sh <<'EOL'
#!/bin/bash

# NexusRFIDReader Monitoring Script
# Ensures the application keeps running

APP_NAME="NexusRFIDReader"
APP_PATH="/usr/local/bin/NexusRFIDReader"
LOG_FILE="/var/log/nexus-rfid-monitor.log"
LOCK_FILE="/var/run/nexus-rfid-monitor.lock"
APP_WORKDIR="/usr/local/bin"

log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE"
}

select_default_user() {
    awk -F: '$3 >= 1000 && $1 != "nobody" {print $1; exit}' /etc/passwd
}

TARGET_USER="${NEXUSRFID_USER:-$(select_default_user)}"
if [ -z "$TARGET_USER" ]; then
    TARGET_USER="root"
fi

TARGET_HOME="${NEXUSRFID_HOME:-$(getent passwd "$TARGET_USER" | cut -d: -f6)}"
if [ -z "$TARGET_HOME" ]; then
    TARGET_HOME="/root"
fi

TARGET_UID="${NEXUSRFID_UID:-$(id -u "$TARGET_USER" 2>/dev/null || echo 0)}"
TARGET_GID="${NEXUSRFID_GID:-$(id -g "$TARGET_USER" 2>/dev/null || echo 0)}"
TARGET_DISPLAY="${NEXUSRFID_DISPLAY:-:0}"
TARGET_XAUTHORITY="${NEXUSRFID_XAUTHORITY:-${TARGET_HOME}/.Xauthority}"
TARGET_RUNTIME_DIR="${NEXUSRFID_RUNTIME_DIR:-/tmp/nexusrfid-runtime}"

mkdir -p "$TARGET_RUNTIME_DIR"
if [ "$TARGET_UID" -gt 0 ] && [ "$TARGET_GID" -gt 0 ]; then
    chown "$TARGET_USER:$TARGET_GID" "$TARGET_RUNTIME_DIR" 2>/dev/null || true
fi
chmod 700 "$TARGET_RUNTIME_DIR" 2>/dev/null || true

log_message "Monitor starting as user $(id -un) (PID: $$)"
log_message "Configured target user: $TARGET_USER (UID: $TARGET_UID)"
log_message "Using DISPLAY=$TARGET_DISPLAY, XAUTHORITY=$TARGET_XAUTHORITY, XDG_RUNTIME_DIR=$TARGET_RUNTIME_DIR"

cleanup() {
    rm -f "$LOCK_FILE"
    exit 0
}

trap cleanup SIGTERM SIGINT

if [ -f "$LOCK_FILE" ]; then
    PID=$(cat "$LOCK_FILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        log_message "Monitor already running with PID $PID"
        exit 0
    else
        rm -f "$LOCK_FILE"
    fi
fi

echo $$ > "$LOCK_FILE"

launch_application() {
    log_message "Attempting to launch $APP_NAME for user $TARGET_USER"
    if command -v runuser >/dev/null 2>&1; then
        runuser -u "$TARGET_USER" -- env DISPLAY="$TARGET_DISPLAY" HOME="$TARGET_HOME" XAUTHORITY="$TARGET_XAUTHORITY" XDG_RUNTIME_DIR="$TARGET_RUNTIME_DIR" "$APP_PATH" >> "$LOG_FILE" 2>&1 &
    elif command -v sudo >/dev/null 2>&1; then
        sudo -u "$TARGET_USER" env DISPLAY="$TARGET_DISPLAY" HOME="$TARGET_HOME" XAUTHORITY="$TARGET_XAUTHORITY" XDG_RUNTIME_DIR="$TARGET_RUNTIME_DIR" "$APP_PATH" >> "$LOG_FILE" 2>&1 &
    else
        su - "$TARGET_USER" -c "env DISPLAY='$TARGET_DISPLAY' HOME='$TARGET_HOME' XAUTHORITY='$TARGET_XAUTHORITY' XDG_RUNTIME_DIR='$TARGET_RUNTIME_DIR' '$APP_PATH'" >> "$LOG_FILE" 2>&1 &
    fi
}

while true; do
    RUNNING_COUNT=$(pgrep -c "$APP_NAME" 2>/dev/null || echo "0")

    if [ "$RUNNING_COUNT" -eq 0 ]; then
        log_message "$APP_NAME is not running. Starting..."
        cd "$APP_WORKDIR"
        launch_application
        sleep 3

        NEW_COUNT=$(pgrep -c "$APP_NAME" 2>/dev/null || echo "0")
        if [ "$NEW_COUNT" -gt 0 ]; then
            log_message "$APP_NAME started successfully"
        else
            log_message "Failed to start $APP_NAME"
        fi
    elif [ "$RUNNING_COUNT" -gt 1 ]; then
        log_message "WARNING: Multiple $APP_NAME processes detected ($RUNNING_COUNT)"
        pkill -f "$APP_NAME"
        sleep 2
        log_message "Killed all $APP_NAME processes, will restart on next cycle"
    else
        log_message "$APP_NAME is running normally (1 process)"
    fi

    sleep 15
done
EOL

chmod +x ${PACKAGE_NAME}-${PACKAGE_VERSION}/usr/local/bin/monitor_nexus_rfid.sh
echo -e "   ${GREEN}SUCCESS${NC} Monitoring script created"

# Step 5: Create systemd service for USB0 DHCP
echo -e "${YELLOW}Step 5: Creating systemd service for USB0 DHCP...${NC}"
cat > ${PACKAGE_NAME}-${PACKAGE_VERSION}/etc/systemd/system/nexusrfid-dhcp.service <<'EOL'
[Unit]
Description=Obtain DHCP lease for NexusRFID USB0 interface
DefaultDependencies=no
After=local-fs.target
Wants=network-pre.target
Before=network-pre.target
Before=network.target
Before=multi-user.target
Before=graphical.target

[Service]
Type=oneshot
ExecStart=/sbin/dhclient usb0
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOL
echo -e "   ${GREEN}SUCCESS${NC} Systemd service created"

# Step 6: Create default service environment configuration
echo -e "${YELLOW}Step 6: Creating default service environment file...${NC}"
cat > ${PACKAGE_NAME}-${PACKAGE_VERSION}/etc/default/nexusrfid <<'EOL'
# Environment overrides for NexusRFID systemd services
# Values can be customized after installation
# NEXUSRFID_USER=rfid
# NEXUSRFID_HOME=/home/rfid
# NEXUSRFID_DISPLAY=:0
# NEXUSRFID_XAUTHORITY=/home/rfid/.Xauthority
# NEXUSRFID_RUNTIME_DIR=/tmp/nexusrfid-runtime
# NEXUSRFID_UID=1000
# NEXUSRFID_GID=1000
EOL
chmod 0644 ${PACKAGE_NAME}-${PACKAGE_VERSION}/etc/default/nexusrfid
echo -e "   ${GREEN}SUCCESS${NC} Service environment file created"

# Step 7: Create systemd service for application monitor
echo -e "${YELLOW}Step 7: Creating systemd service for NexusRFID monitor...${NC}"
cat > ${PACKAGE_NAME}-${PACKAGE_VERSION}/etc/systemd/system/nexusrfid-monitor.service <<'EOL'
[Unit]
Description=NexusRFIDReader Monitor Service
After=network.target nexusrfid-dhcp.service multi-user.target
Wants=nexusrfid-dhcp.service

[Service]
Type=simple
EnvironmentFile=-/etc/default/nexusrfid
ExecStart=/usr/local/bin/monitor_nexus_rfid.sh
Restart=always
RestartSec=10
KillMode=process

[Install]
WantedBy=graphical.target
EOL
echo -e "   ${GREEN}SUCCESS${NC} Monitor systemd service created"

# Step 8: Create .desktop file for application menu
echo -e "${YELLOW}Step 8: Creating desktop application entry...${NC}"
cat > ${PACKAGE_NAME}-${PACKAGE_VERSION}/usr/share/applications/${PACKAGE_NAME}.desktop <<EOL
[Desktop Entry]
Version=1.0
Name=Nexus RFID Reader
Comment=Advanced RFID scanning and GPS tracking system
Exec=/usr/local/bin/NexusRFIDReader
Icon=${PACKAGE_NAME}
Terminal=false
Type=Application
Categories=Utility;Office;
Keywords=RFID;GPS;Inventory;Tracking;
StartupNotify=true
EOL
echo -e "   ${GREEN}SUCCESS${NC} Desktop entry created"

# Step 9: Create control file
echo -e "${YELLOW}Step 9: Creating package control file...${NC}"
cat > ${PACKAGE_NAME}-${PACKAGE_VERSION}/DEBIAN/control <<EOL
Package: ${PACKAGE_NAME}
Version: ${PACKAGE_VERSION}
Section: utils
Priority: optional
Architecture: ${ARCHITECTURE}
Maintainer: ${MAINTAINER} <support@nexusyms.com>
Homepage: ${WEBSITE}
Depends: libxcb-xinerama0, libxcb-cursor0, libx11-xcb1, libxcb1, libxfixes3, libxi6, libxrender1, libxcb-render0, libxcb-shape0, libxcb-xfixes0, x11-xserver-utils, python3, python3-pip, arp-scan, isc-dhcp-client
Description: ${DESCRIPTION}
 This application provides advanced RFID scanning capabilities with GPS tracking,
 real-time data processing, and cloud synchronization. It's designed for inventory
 management and asset tracking in industrial environments.
 .
 Features:
  * Real-time RFID tag scanning
  * GPS location tracking
  * SQLite database storage
  * Cloud API integration
  * Configurable filtering options
  * Automatic data synchronization
  * User-friendly GUI interface
EOL
echo -e "   ${GREEN}SUCCESS${NC} Control file created"

# Step 10: Create post-installation script
echo -e "${YELLOW}Step 10: Creating post-installation script...${NC}"
cat > ${PACKAGE_NAME}-${PACKAGE_VERSION}/DEBIAN/postinst <<'EOL'
#!/bin/bash

set -e

echo "Setting up NexusRFIDReader environment..."

# Ensure arp-scan is installed
if ! dpkg -s arp-scan >/dev/null 2>&1; then
    echo "Installing arp-scan dependency..."
    if command -v apt-get >/dev/null 2>&1; then
        apt-get update
        apt-get install -y arp-scan
    else
        echo "apt-get not found. Please install arp-scan manually." >&2
        exit 1
    fi
fi

# Create log directory
LOG_DIR=/var/log
if [ ! -d "$LOG_DIR" ]; then
    mkdir -p "$LOG_DIR"
fi

# Set up log file for monitoring script
touch /var/log/nexus-rfid-monitor.log
chmod 644 /var/log/nexus-rfid-monitor.log
chown root:root /var/log/nexus-rfid-monitor.log

# Create run directory for lock files
mkdir -p /var/run
chmod 755 /var/run

# Determine default user for GUI execution and configure environment file
CONFIG_FILE=/etc/default/nexusrfid
if [ ! -f "$CONFIG_FILE" ] || ! grep -Eq '^[^#[:space:]]' "$CONFIG_FILE"; then
    DEFAULT_USER=$(awk -F: '$3 >= 1000 && $1 != "nobody" {print $1; exit}' /etc/passwd)
    if [ -n "$DEFAULT_USER" ]; then
        DEFAULT_HOME=$(getent passwd "$DEFAULT_USER" | cut -d: -f6)
        DEFAULT_UID=$(id -u "$DEFAULT_USER")
        DEFAULT_GID=$(id -g "$DEFAULT_USER")
        cat > "$CONFIG_FILE" <<EOF
# Auto-generated by NexusRFIDReader post-install script
NEXUSRFID_USER=${DEFAULT_USER}
NEXUSRFID_HOME=${DEFAULT_HOME}
NEXUSRFID_DISPLAY=:0
NEXUSRFID_XAUTHORITY=${DEFAULT_HOME}/.Xauthority
NEXUSRFID_RUNTIME_DIR=/tmp/nexusrfid-runtime
NEXUSRFID_UID=${DEFAULT_UID}
NEXUSRFID_GID=${DEFAULT_GID}
EOF
        chmod 0644 "$CONFIG_FILE"
        echo "Configured /etc/default/nexusrfid for user ${DEFAULT_USER}"
    else
        echo "WARNING: No suitable non-root user found for NexusRFID GUI launch. Please edit /etc/default/nexusrfid manually."
    fi
fi

# Update desktop database
if command -v update-desktop-database &> /dev/null; then
    update-desktop-database /usr/share/applications
    echo "Updated desktop database"
fi

# Update icon cache
if command -v gtk-update-icon-cache &> /dev/null; then
    gtk-update-icon-cache -f -t /usr/share/icons/hicolor
    echo "Updated icon cache"
fi

# Enable and start DHCP systemd service
if command -v systemctl &> /dev/null; then
    systemctl daemon-reload
    systemctl enable nexusrfid-dhcp.service
    systemctl start nexusrfid-dhcp.service || true
    systemctl enable nexusrfid-monitor.service
    systemctl start nexusrfid-monitor.service || true
    echo "Enabled NexusRFID systemd services (dhcp, monitor)"
else
    echo "systemctl not available; please enable nexusrfid services manually if needed."
fi

echo "NexusRFIDReader installation completed successfully!"
echo "You can also start it manually from the Applications menu."

EOL

# Make the postinst script executable
chmod 0755 ${PACKAGE_NAME}-${PACKAGE_VERSION}/DEBIAN/postinst
echo -e "   ${GREEN}SUCCESS${NC} Post-installation script created"

# Step 11: Create pre-removal script
echo -e "${YELLOW}Step 11: Creating pre-removal script...${NC}"
cat > ${PACKAGE_NAME}-${PACKAGE_VERSION}/DEBIAN/prerm <<'EOL'
#!/bin/bash

echo "Stopping NexusRFIDReader processes..."

# Stop monitoring script first
pkill -f "monitor_nexus_rfid.sh" || true

# Stop all NexusRFIDReader processes
pkill -f "NexusRFIDReader" || true

# Wait a moment for graceful shutdown
sleep 2

# Force kill if still running
pkill -9 -f "NexusRFIDReader" || true
pkill -9 -f "monitor_nexus_rfid.sh" || true

# Clean up lock file
rm -f /var/run/nexus-rfid-monitor.lock

# Disable and stop systemd services
if command -v systemctl &> /dev/null; then
    systemctl stop nexusrfid-monitor.service || true
    systemctl stop nexusrfid-dhcp.service || true
    systemctl disable nexusrfid-monitor.service || true
    systemctl disable nexusrfid-dhcp.service || true
    systemctl daemon-reload
fi

echo "NexusRFIDReader processes stopped."
EOL

chmod 0755 ${PACKAGE_NAME}-${PACKAGE_VERSION}/DEBIAN/prerm
echo -e "   ${GREEN}SUCCESS${NC} Pre-removal script created"

# Step 12: Build the .deb package
echo -e "${YELLOW}Step 12: Building the .deb package...${NC}"
dpkg-deb --build ${PACKAGE_NAME}-${PACKAGE_VERSION}
echo -e "   ${GREEN}SUCCESS${NC} Package built successfully"

# Step 13: Clean up build directory
echo -e "${YELLOW}Step 13: Cleaning up build files...${NC}"
rm -rf ${PACKAGE_NAME}-${PACKAGE_VERSION}
echo -e "   ${GREEN}SUCCESS${NC} Build files cleaned up"

echo ""
echo -e "${GREEN}==============================================================${NC}"
echo -e "${GREEN}            PACKAGE CREATED SUCCESSFULLY!${NC}"
echo -e "${GREEN}==============================================================${NC}"
echo ""
echo -e "${WHITE}Package File:${NC} ${PACKAGE_NAME}-${PACKAGE_VERSION}.deb"
echo -e "${WHITE}Package Size:${NC} $(du -h ${PACKAGE_NAME}-${PACKAGE_VERSION}.deb | cut -f1)"
echo ""
echo -e "${CYAN}Installation Instructions:${NC}"
echo -e "   ${YELLOW}1.${NC} Install the package:"
echo -e "      ${WHITE}sudo apt install ./${PACKAGE_NAME}-${PACKAGE_VERSION}.deb${NC}"
echo ""
echo -e "   ${YELLOW}2.${NC} Reboot to activate system services:"
echo -e "      ${WHITE}sudo reboot${NC}"
echo ""
echo -e "   ${YELLOW}3.${NC} You can also find it in the Applications menu"
echo ""
echo -e "${PURPLE}Package Contents:${NC}"
echo -e "   • Executable: /usr/local/bin/NexusRFIDReader"
echo -e "   • Icon: /usr/share/icons/hicolor/512x512/apps/${PACKAGE_NAME}.ico"
echo -e "   • Desktop Entry: /usr/share/applications/${PACKAGE_NAME}.desktop"
echo -e "   • DHCP Service: /etc/systemd/system/nexusrfid-dhcp.service"
echo -e "   • Monitor Service: /etc/systemd/system/nexusrfid-monitor.service"
echo -e "   • Log File: /var/log/nexus-rfid-monitor.log"
echo ""
echo -e "${GREEN}Ready for deployment!${NC}"
