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

echo -e "${CYAN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║                    NexusRFIDReader Package Builder           ║${NC}"
echo -e "${CYAN}║                      For Raspberry Pi                        ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check if we're in the right directory
if [ ! -f "main.py" ] || [ ! -f "NexusRFIDReader.spec" ]; then
    echo -e "${RED}❌ Error: Please run this script from the project root directory${NC}"
    echo -e "${YELLOW}   Expected files: main.py, NexusRFIDReader.spec${NC}"
    exit 1
fi

echo -e "${BLUE}📋 Package Information:${NC}"
echo -e "   ${WHITE}Name:${NC} $PACKAGE_NAME"
echo -e "   ${WHITE}Version:${NC} $PACKAGE_VERSION"
echo -e "   ${WHITE}Architecture:${NC} $ARCHITECTURE"
echo -e "   ${WHITE}Description:${NC} $DESCRIPTION"
echo ""

# Step 1: Build PyInstaller executable
echo -e "${YELLOW}🔨 Step 1: Building PyInstaller executable...${NC}"
if command -v pyinstaller &> /dev/null; then
    echo -e "   ${GREEN}✓${NC} PyInstaller found"
    pyinstaller --clean --onefile --icon=ui/img/icon.ico --name=NexusRFIDReader main.py
    echo -e "   ${GREEN}✓${NC} Executable built successfully"
else
    echo -e "   ${RED}❌ PyInstaller not found. Installing...${NC}"
    pip3 install pyinstaller
    pyinstaller --clean --onefile --icon=ui/img/icon.ico --name=NexusRFIDReader main.py
    echo -e "   ${GREEN}✓${NC} PyInstaller installed and executable built"
fi

# Check if executable was created
if [ ! -f "dist/NexusRFIDReader" ]; then
    echo -e "${RED}❌ Error: Executable not created successfully${NC}"
    exit 1
fi

echo ""

# Step 2: Create directory structure
echo -e "${YELLOW}📁 Step 2: Creating package directory structure...${NC}"
mkdir -p ${PACKAGE_NAME}-${PACKAGE_VERSION}/DEBIAN
mkdir -p ${PACKAGE_NAME}-${PACKAGE_VERSION}/usr/local/bin
mkdir -p ${PACKAGE_NAME}-${PACKAGE_VERSION}/usr/share/applications
mkdir -p ${PACKAGE_NAME}-${PACKAGE_VERSION}/usr/share/icons/hicolor/512x512/apps
mkdir -p ${PACKAGE_NAME}-${PACKAGE_VERSION}/etc/skel/.config/autostart
mkdir -p ${PACKAGE_NAME}-${PACKAGE_VERSION}/var/lib/nexusrfid
echo -e "   ${GREEN}✓${NC} Directory structure created"

# Step 3: Copy files to package
echo -e "${YELLOW}📦 Step 3: Copying application files...${NC}"
cp dist/NexusRFIDReader ${PACKAGE_NAME}-${PACKAGE_VERSION}/usr/local/bin/
cp ui/img/icon.ico ${PACKAGE_NAME}-${PACKAGE_VERSION}/usr/share/icons/hicolor/512x512/apps/${PACKAGE_NAME}.ico
echo -e "   ${GREEN}✓${NC} Application files copied"

# Step 4: Create monitoring script
echo -e "${YELLOW}🔍 Step 4: Creating application monitoring script...${NC}"
cat > ${PACKAGE_NAME}-${PACKAGE_VERSION}/usr/local/bin/monitor_nexus_rfid.sh <<'EOL'
#!/bin/bash

# NexusRFIDReader Monitoring Script
# Ensures the application keeps running

APP_NAME="NexusRFIDReader"
APP_PATH="/usr/local/bin/NexusRFIDReader"
LOG_FILE="/var/log/nexus-rfid-monitor.log"

# Function to log messages
log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE"
}

log_message "Starting NexusRFIDReader monitor"

while true; do
    if ! pgrep -x "$APP_NAME" > /dev/null; then
        log_message "$APP_NAME is not running. Starting..."
        $APP_PATH &
        sleep 2
        if pgrep -x "$APP_NAME" > /dev/null; then
            log_message "$APP_NAME started successfully"
        else
            log_message "Failed to start $APP_NAME"
        fi
    else
        log_message "$APP_NAME is running normally"
    fi
    sleep 10
done
EOL

chmod +x ${PACKAGE_NAME}-${PACKAGE_VERSION}/usr/local/bin/monitor_nexus_rfid.sh
echo -e "   ${GREEN}✓${NC} Monitoring script created"

# Step 5: Create .desktop file for application menu
echo -e "${YELLOW}🖥️  Step 5: Creating desktop application entry...${NC}"
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
echo -e "   ${GREEN}✓${NC} Desktop entry created"

# Step 6: Create autostart entry
echo -e "${YELLOW}🚀 Step 6: Creating autostart configuration...${NC}"
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
echo -e "   ${GREEN}✓${NC} Autostart configuration created"

# Step 7: Create control file
echo -e "${YELLOW}📋 Step 7: Creating package control file...${NC}"
cat > ${PACKAGE_NAME}-${PACKAGE_VERSION}/DEBIAN/control <<EOL
Package: ${PACKAGE_NAME}
Version: ${PACKAGE_VERSION}
Section: utils
Priority: optional
Architecture: ${ARCHITECTURE}
Maintainer: ${MAINTAINER} <support@nexusyms.com>
Homepage: ${WEBSITE}
Depends: libxcb-xinerama0, libxcb-cursor0, libx11-xcb1, libxcb1, libxfixes3, libxi6, libxrender1, libxcb-render0, libxcb-shape0, libxcb-xfixes0, x11-xserver-utils, python3, python3-pip
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
echo -e "   ${GREEN}✓${NC} Control file created"

# Step 8: Create postinst script
echo -e "${YELLOW}⚙️  Step 8: Creating post-installation script...${NC}"
cat > ${PACKAGE_NAME}-${PACKAGE_VERSION}/DEBIAN/postinst <<'EOL'
#!/bin/bash

set -e

echo "Setting up NexusRFIDReader environment..."

# Create data directory with proper permissions
RFID_DATA_DIR=/var/lib/nexusrfid
if [ ! -d "$RFID_DATA_DIR" ]; then
    mkdir -p "$RFID_DATA_DIR"
    chmod -R 755 "$RFID_DATA_DIR"
    echo "Created data directory at $RFID_DATA_DIR"
fi

# Create log directory
LOG_DIR=/var/log
if [ ! -d "$LOG_DIR" ]; then
    mkdir -p "$LOG_DIR"
fi

# Set up log file for monitoring script
touch /var/log/nexus-rfid-monitor.log
chmod 644 /var/log/nexus-rfid-monitor.log

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
echo "The application will start automatically on next login."
echo "You can also start it manually from the Applications menu."

EOL

# Make the postinst script executable
chmod 0755 ${PACKAGE_NAME}-${PACKAGE_VERSION}/DEBIAN/postinst
echo -e "   ${GREEN}✓${NC} Post-installation script created"

# Step 9: Create prerm script for clean removal
echo -e "${YELLOW}🧹 Step 9: Creating pre-removal script...${NC}"
cat > ${PACKAGE_NAME}-${PACKAGE_VERSION}/DEBIAN/prerm <<'EOL'
#!/bin/bash

echo "Stopping NexusRFIDReader processes..."

# Stop the application if running
pkill -f "NexusRFIDReader" || true
pkill -f "monitor_nexus_rfid.sh" || true

echo "NexusRFIDReader processes stopped."
EOL

chmod 0755 ${PACKAGE_NAME}-${PACKAGE_VERSION}/DEBIAN/prerm
echo -e "   ${GREEN}✓${NC} Pre-removal script created"

# Step 10: Build the .deb package
echo -e "${YELLOW}📦 Step 10: Building the .deb package...${NC}"
dpkg-deb --build ${PACKAGE_NAME}-${PACKAGE_VERSION}
echo -e "   ${GREEN}✓${NC} Package built successfully"

# Step 11: Clean up build directory
echo -e "${YELLOW}🧹 Step 11: Cleaning up build files...${NC}"
rm -rf ${PACKAGE_NAME}-${PACKAGE_VERSION}
echo -e "   ${GREEN}✓${NC} Build files cleaned up"

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                    🎉 PACKAGE CREATED SUCCESSFULLY! 🎉        ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${WHITE}📦 Package File:${NC} ${PACKAGE_NAME}-${PACKAGE_VERSION}.deb"
echo -e "${WHITE}📏 Package Size:${NC} $(du -h ${PACKAGE_NAME}-${PACKAGE_VERSION}.deb | cut -f1)"
echo ""
echo -e "${CYAN}🚀 Installation Instructions:${NC}"
echo -e "   ${YELLOW}1.${NC} Install the package:"
echo -e "      ${WHITE}sudo apt install ./${PACKAGE_NAME}-${PACKAGE_VERSION}.deb${NC}"
echo ""
echo -e "   ${YELLOW}2.${NC} Reboot to activate autostart:"
echo -e "      ${WHITE}sudo reboot${NC}"
echo ""
echo -e "   ${YELLOW}3.${NC} The application will start automatically on login"
echo -e "   ${YELLOW}4.${NC} You can also find it in the Applications menu"
echo ""
echo -e "${PURPLE}📋 Package Contents:${NC}"
echo -e "   • Executable: /usr/local/bin/NexusRFIDReader"
echo -e "   • Icon: /usr/share/icons/hicolor/512x512/apps/${PACKAGE_NAME}.ico"
echo -e "   • Desktop Entry: /usr/share/applications/${PACKAGE_NAME}.desktop"
echo -e "   • Data Directory: /var/lib/nexusrfid"
echo -e "   • Log File: /var/log/nexus-rfid-monitor.log"
echo -e "   • Autostart: ~/.config/autostart/monitor-nexus-rfid.desktop"
echo ""
echo -e "${GREEN}✨ Ready for deployment! ✨${NC}"
