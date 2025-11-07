#!/bin/bash

# NexusRFIDReader Uninstall Script for Raspberry Pi
# This script completely removes the NexusRFIDReader package and all associated files

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

PACKAGE_NAME=NexusRFIDReader
PACKAGE_NAME_CANONICAL=$(echo "$PACKAGE_NAME" | tr '[:upper:]' '[:lower:]')

echo -e "${CYAN}==============================================================${NC}"
echo -e "${CYAN}            NexusRFIDReader Uninstaller${NC}"
echo -e "${CYAN}              For Raspberry Pi${NC}"
echo -e "${CYAN}==============================================================${NC}"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}ERROR: This script must be run as root (use sudo)${NC}"
    exit 1
fi

echo -e "${YELLOW}WARNING: This will completely remove NexusRFIDReader and all its data!${NC}"
echo -e "${YELLOW}This action cannot be undone.${NC}"
echo ""
read -p "Are you sure you want to continue? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${BLUE}Uninstall cancelled.${NC}"
    exit 0
fi

echo ""

# Step 1: Stop all running processes
echo -e "${YELLOW}Step 1: Stopping NexusRFIDReader processes...${NC}"
echo -e "   ${WHITE}Stopping application processes...${NC}"
pkill -f "NexusRFIDReader" || echo -e "   ${BLUE}No running NexusRFIDReader processes found${NC}"

echo -e "   ${WHITE}Stopping monitoring processes...${NC}"
pkill -f "monitor_nexus_rfid.sh" || echo -e "   ${BLUE}No running monitoring processes found${NC}"

# Wait a moment for processes to stop
sleep 2

# Force kill if still running
pkill -9 -f "NexusRFIDReader" 2>/dev/null || true
pkill -9 -f "monitor_nexus_rfid.sh" 2>/dev/null || true

# Clean up lock file
rm -f /var/run/nexus-rfid-monitor.lock

echo -e "   ${GREEN}SUCCESS${NC} All processes stopped"

# Step 2: Remove the package using dpkg
echo -e "${YELLOW}Step 2: Removing package using dpkg...${NC}"
if dpkg -l | grep -qi "^ii.*${PACKAGE_NAME_CANONICAL}"; then
    dpkg --remove ${PACKAGE_NAME_CANONICAL} || dpkg --remove ${PACKAGE_NAME} || echo -e "   ${YELLOW}WARNING: Package removal had issues, continuing...${NC}"
    echo -e "   ${GREEN}SUCCESS${NC} Package removed"
else
    echo -e "   ${BLUE}Package not found in dpkg database${NC}"
fi

# Step 3: Purge configuration files
echo -e "${YELLOW}Step 3: Purging configuration files...${NC}"
if ! apt-get purge -y ${PACKAGE_NAME} >/dev/null 2>&1; then
    apt-get purge -y ${PACKAGE_NAME_CANONICAL} >/dev/null 2>&1 || echo -e "   ${BLUE}No configuration files to purge${NC}"
fi
echo -e "   ${GREEN}SUCCESS${NC} Configuration files purged"

# Step 4: Remove application files
echo -e "${YELLOW}Step 4: Removing application files...${NC}"

# Remove executable
if [ -f "/usr/local/bin/NexusRFIDReader" ]; then
    rm -f /usr/local/bin/NexusRFIDReader
    echo -e "   ${GREEN}SUCCESS${NC} Removed executable: /usr/local/bin/NexusRFIDReader"
fi

# Remove monitoring script
if [ -f "/usr/local/bin/monitor_nexus_rfid.sh" ]; then
    rm -f /usr/local/bin/monitor_nexus_rfid.sh
    echo -e "   ${GREEN}SUCCESS${NC} Removed monitoring script: /usr/local/bin/monitor_nexus_rfid.sh"
fi

# Remove desktop entry
if [ -f "/usr/share/applications/${PACKAGE_NAME}.desktop" ]; then
    rm -f /usr/share/applications/${PACKAGE_NAME}.desktop
    echo -e "   ${GREEN}SUCCESS${NC} Removed desktop entry: /usr/share/applications/${PACKAGE_NAME}.desktop"
fi

# Remove icon
if [ -f "/usr/share/icons/hicolor/512x512/apps/${PACKAGE_NAME}.ico" ]; then
    rm -f /usr/share/icons/hicolor/512x512/apps/${PACKAGE_NAME}.ico
    echo -e "   ${GREEN}SUCCESS${NC} Removed icon: /usr/share/icons/hicolor/512x512/apps/${PACKAGE_NAME}.ico"
fi

# Step 5: Remove data directories
echo -e "${YELLOW}Step 5: Removing data directories...${NC}"

# Remove main data directory
RFID_DATA_DIR=/var/lib/nexusrfid
if [ -d "$RFID_DATA_DIR" ]; then
    echo -e "   ${WHITE}Found data directory: $RFID_DATA_DIR${NC}"
    echo -e "   ${YELLOW}WARNING: This directory may contain important data!${NC}"
    read -p "   Remove data directory? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf "$RFID_DATA_DIR"
        echo -e "   ${GREEN}SUCCESS${NC} Removed data directory: $RFID_DATA_DIR"
    else
        echo -e "   ${BLUE}Data directory preserved: $RFID_DATA_DIR${NC}"
    fi
else
    echo -e "   ${BLUE}No data directory found${NC}"
fi

# Step 6: Clean up autostart entries
echo -e "${YELLOW}Step 6: Removing autostart entries...${NC}"
AUTOSTART_REMOVED=0
for user_dir in /home/*; do
    if [ -d "$user_dir" ]; then
        user_autostart_dir="$user_dir/.config/autostart"
        autostart_file="$user_autostart_dir/monitor-nexus-rfid.desktop"
        if [ -f "$autostart_file" ]; then
            rm -f "$autostart_file"
            echo -e "   ${GREEN}SUCCESS${NC} Removed autostart for user: $(basename "$user_dir")"
            AUTOSTART_REMOVED=1
        fi
    fi
done

if [ $AUTOSTART_REMOVED -eq 0 ]; then
    echo -e "   ${BLUE}No autostart entries found${NC}"
fi

# Step 7: Remove log files
echo -e "${YELLOW}Step 7: Cleaning up log files...${NC}"
if [ -f "/var/log/nexus-rfid-monitor.log" ]; then
    echo -e "   ${WHITE}Found log file: /var/log/nexus-rfid-monitor.log${NC}"
    read -p "   Remove log file? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -f /var/log/nexus-rfid-monitor.log
        echo -e "   ${GREEN}SUCCESS${NC} Removed log file: /var/log/nexus-rfid-monitor.log"
    else
        echo -e "   ${BLUE}Log file preserved: /var/log/nexus-rfid-monitor.log${NC}"
    fi
else
    echo -e "   ${BLUE}No log file found${NC}"
fi

# Step 8: Update system databases
echo -e "${YELLOW}Step 8: Updating system databases...${NC}"

# Update desktop database
if command -v update-desktop-database &> /dev/null; then
    update-desktop-database /usr/share/applications 2>/dev/null || true
    echo -e "   ${GREEN}SUCCESS${NC} Updated desktop database"
fi

# Update icon cache
if command -v gtk-update-icon-cache &> /dev/null; then
    gtk-update-icon-cache -f -t /usr/share/icons/hicolor 2>/dev/null || true
    echo -e "   ${GREEN}SUCCESS${NC} Updated icon cache"
fi

# Step 9: Clean up package cache
echo -e "${YELLOW}Step 9: Cleaning up package cache...${NC}"
apt-get autoremove -y 2>/dev/null || true
apt-get autoclean 2>/dev/null || true
echo -e "   ${GREEN}SUCCESS${NC} Package cache cleaned"

# Step 10: Final verification
echo -e "${YELLOW}Step 10: Final verification...${NC}"
REMAINING_FILES=0

# Check for remaining files
if [ -f "/usr/local/bin/NexusRFIDReader" ] || \
   [ -f "/usr/local/bin/monitor_nexus_rfid.sh" ] || \
   [ -f "/usr/share/applications/${PACKAGE_NAME}.desktop" ] || \
   [ -f "/usr/share/icons/hicolor/512x512/apps/${PACKAGE_NAME}.ico" ]; then
    REMAINING_FILES=1
fi

if [ $REMAINING_FILES -eq 0 ]; then
    echo -e "   ${GREEN}SUCCESS${NC} All application files removed successfully"
else
    echo -e "   ${YELLOW}WARNING: Some files may still remain${NC}"
fi

echo ""
echo -e "${GREEN}==============================================================${NC}"
echo -e "${GREEN}            UNINSTALLATION COMPLETED!${NC}"
echo -e "${GREEN}==============================================================${NC}"
echo ""
echo -e "${CYAN}Summary of removed components:${NC}"
echo -e "   • Application executable"
echo -e "   • Monitoring script"
echo -e "   • Desktop entry"
echo -e "   • Application icon"
echo -e "   • Autostart configurations"
echo -e "   • Package database entries"
echo ""
echo -e "${PURPLE}Preserved components (if you chose to keep them):${NC}"
echo -e "   • Data directory: /var/lib/nexusrfid"
echo -e "   • Log file: /var/log/nexus-rfid-monitor.log"
echo ""
echo -e "${BLUE}Note:${NC}"
echo -e "   • You may need to log out and log back in for all changes to take effect"
echo -e "   • If you want to reinstall, run the installation script again"
echo ""
echo -e "${GREEN}NexusRFIDReader has been completely removed!${NC}"
