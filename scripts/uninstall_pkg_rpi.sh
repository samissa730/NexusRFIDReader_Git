#!/bin/bash

# Define package variables
PACKAGE_NAME=NexusRFIDReader

# Request sudo permissions upfront
if [ "$EUID" -ne 0 ]; then
    echo "This script requires administrative privileges. Please run as root or use sudo."
    exit 1
fi

# Remove the monitoring script
if [ -f "/usr/local/bin/monitor_nexus_rfid.sh" ]; then
    rm -f /usr/local/bin/monitor_nexus_rfid.sh
    echo "Removed monitoring script at /usr/local/bin/monitor_nexus_rfid.sh."
fi

# Remove the binary
if [ -f "/usr/local/bin/${PACKAGE_NAME}" ]; then
    rm -f "/usr/local/bin/${PACKAGE_NAME}"
    echo "Removed binary at /usr/local/bin/${PACKAGE_NAME}."
fi

# Remove the desktop file
if [ -f "/usr/share/applications/${PACKAGE_NAME}.desktop" ]; then
    rm -f "/usr/share/applications/${PACKAGE_NAME}.desktop"
    echo "Removed desktop file at /usr/share/applications/${PACKAGE_NAME}.desktop."
fi

# Remove the icon
if [ -f "/usr/share/icons/hicolor/512x512/apps/${PACKAGE_NAME}.png" ]; then
    rm -f "/usr/share/icons/hicolor/512x512/apps/${PACKAGE_NAME}.png"
    echo "Removed icon at /usr/share/icons/hicolor/512x512/apps/${PACKAGE_NAME}.png."
fi

# Remove autostart configurations from existing users' directories
echo "Removing autostart configurations..."
find /home/*/.config/autostart -name "monitor-nexus-rfid.desktop" -exec rm -f {} \; 2>/dev/null || true

# Remove data directory (optional - ask user)
NEXUS_DATA_DIR=/var/lib/nexusrfid
if [ -d "$NEXUS_DATA_DIR" ]; then
    echo "Data directory $NEXUS_DATA_DIR exists."
    read -p "Do you want to remove the data directory? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf "$NEXUS_DATA_DIR"
        echo "Removed data directory at $NEXUS_DATA_DIR."
    else
        echo "Data directory $NEXUS_DATA_DIR preserved."
    fi
fi

echo "NexusRFID Reader package has been uninstalled successfully."
