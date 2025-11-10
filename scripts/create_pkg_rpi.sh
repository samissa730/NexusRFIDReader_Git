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
mkdir -p ${PACKAGE_NAME}-${PACKAGE_VERSION}/etc/skel/.config/autostart
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
DHCLIENT_CMD="sudo dhclient usb0"
DEFAULT_HOME_DIR="$(getent passwd $(logname 2>/dev/null || id -un) 2>/dev/null | cut -d: -f6)"
USER_UID="$(id -u)"

# Function to log messages
log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE"
}

# Function to ensure DHCP client runs for usb0
run_dhclient() {
    log_message "Running DHCP client for usb0 (command: $DHCLIENT_CMD)"
    if command -v sudo >/dev/null 2>&1; then
        if $DHCLIENT_CMD >> "$LOG_FILE" 2>&1; then
            log_message "Successfully executed $DHCLIENT_CMD"
        else
            log_message "Failed to execute $DHCLIENT_CMD"
        fi
    elif command -v dhclient >/dev/null 2>&1; then
        if dhclient usb0 >> "$LOG_FILE" 2>&1; then
            log_message "Successfully executed dhclient usb0 without sudo"
        else
            log_message "Failed to execute dhclient usb0"
        fi
    else
        log_message "dhclient not available on system"
    fi
}

# Check if another instance is already running
if [ -f "$LOCK_FILE" ]; then
    PID=$(cat "$LOCK_FILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        log_message "Monitor already running with PID $PID"
        exit 0
    else
        rm -f "$LOCK_FILE"
    fi
fi

# Create lock file
echo $$ > "$LOCK_FILE"

# Cleanup function
cleanup() {
    rm -f "$LOCK_FILE"
    exit 0
}

# Set up signal handlers
trap cleanup SIGTERM SIGINT

log_message "Starting NexusRFIDReader monitor (PID: $$)"

# Run DHCP client once immediately after startup
run_dhclient

# Ensure UI environment variables are set for application display
if [ -z "$DEFAULT_HOME_DIR" ]; then
    DEFAULT_HOME_DIR="$HOME"
fi
export DISPLAY=${DISPLAY:-:0}
export HOME=${HOME:-${DEFAULT_HOME_DIR:-/home/pi}}
export XAUTHORITY=${XAUTHORITY:-${HOME}/.Xauthority}
if [ -z "$XDG_RUNTIME_DIR" ]; then
    if [ -d "/run/user/$USER_UID" ]; then
        export XDG_RUNTIME_DIR="/run/user/$USER_UID"
    else
        export XDG_RUNTIME_DIR="/tmp"
    fi
fi

while true; do
    # Check if any NexusRFIDReader processes are running
    RUNNING_COUNT=$(pgrep -c "$APP_NAME" 2>/dev/null || echo "0")
    
    if [ "$RUNNING_COUNT" -eq 0 ]; then
        log_message "$APP_NAME is not running. Starting..."
        run_dhclient
        # Change to application directory before starting
        cd "$APP_WORKDIR"
        $APP_PATH &
        sleep 3
        
        # Verify it started
        NEW_COUNT=$(pgrep -c "$APP_NAME" 2>/dev/null || echo "0")
        if [ "$NEW_COUNT" -gt 0 ]; then
            log_message "$APP_NAME started successfully"
        else
            log_message "Failed to start $APP_NAME"
        fi
    elif [ "$RUNNING_COUNT" -gt 1 ]; then
        log_message "WARNING: Multiple $APP_NAME processes detected ($RUNNING_COUNT)"
        # Kill all processes and restart
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

# Step 5: Create .desktop file for application menu
echo -e "${YELLOW}Step 5: Creating desktop application entry...${NC}"
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

# Step 6: Create autostart entry
echo -e "${YELLOW}Step 6: Creating autostart configuration...${NC}"
cat > ${PACKAGE_NAME}-${PACKAGE_VERSION}/etc/skel/.config/autostart/monitor-nexus-rfid.desktop <<EOL
[Desktop Entry]
Type=Application
Exec=/usr/local/bin/monitor_nexus_rfid.sh
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
Name=Monitor Nexus RFID Reader
Comment=Ensures NexusRFIDReader keeps running
EOL
echo -e "   ${GREEN}SUCCESS${NC} Autostart configuration created"

# Step 7: Create control file
echo -e "${YELLOW}Step 7: Creating package control file...${NC}"
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

# Step 8: Create postinst script
echo -e "${YELLOW}Step 8: Creating post-installation script...${NC}"
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

# Copy autostart configurations to existing users' directories
for user_dir in /home/*; do
    if [ -d "$user_dir" -a -w "$user_dir" ]; then
        user_autostart_dir="$user_dir/.config/autostart"
        mkdir -p "$user_autostart_dir"
        cp /etc/skel/.config/autostart/monitor-nexus-rfid.desktop "$user_autostart_dir/"
        chown $(basename "$user_dir"):$(basename "$user_dir") "$user_autostart_dir/monitor-nexus-rfid.desktop"
        echo "Configured autostart for user: $(basename "$user_dir")"
    fi
done

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

echo "NexusRFIDReader installation completed successfully!"
echo "You can also start it manually from the Applications menu."

EOL

# Make the postinst script executable
chmod 0755 ${PACKAGE_NAME}-${PACKAGE_VERSION}/DEBIAN/postinst
echo -e "   ${GREEN}SUCCESS${NC} Post-installation script created"

# Step 9: Create prerm script for clean removal
echo -e "${YELLOW}Step 9: Creating pre-removal script...${NC}"
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

echo "NexusRFIDReader processes stopped."
EOL

chmod 0755 ${PACKAGE_NAME}-${PACKAGE_VERSION}/DEBIAN/prerm
echo -e "   ${GREEN}SUCCESS${NC} Pre-removal script created"

# Step 10: Build the .deb package
echo -e "${YELLOW}Step 10: Building the .deb package...${NC}"
dpkg-deb --build ${PACKAGE_NAME}-${PACKAGE_VERSION}
echo -e "   ${GREEN}SUCCESS${NC} Package built successfully"

# Step 11: Clean up build directory
echo -e "${YELLOW}Step 11: Cleaning up build files...${NC}"
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
echo -e "   ${YELLOW}2.${NC} Reboot to activate autostart:"
echo -e "      ${WHITE}sudo reboot${NC}"
echo ""
echo -e "   ${YELLOW}3.${NC} You can also find it in the Applications menu"
echo ""
echo -e "${PURPLE}Package Contents:${NC}"
echo -e "   • Executable: /usr/local/bin/NexusRFIDReader"
echo -e "   • Icon: /usr/share/icons/hicolor/512x512/apps/${PACKAGE_NAME}.ico"
echo -e "   • Desktop Entry: /usr/share/applications/${PACKAGE_NAME}.desktop"
echo -e "   • Log File: /var/log/nexus-rfid-monitor.log"
echo -e "   • Autostart: ~/.config/autostart/monitor-nexus-rfid.desktop"
echo ""
echo -e "${GREEN}Ready for deployment!${NC}"
