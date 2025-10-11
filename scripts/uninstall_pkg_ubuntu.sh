#!/bin/bash

# Define package variables
PACKAGE_NAME=NexusRFIDReader
PACKAGE_VERSION=1.0

# Request sudo permissions upfront
if [ "$EUID" -ne 0 ]; then
    echo "This script requires administrative privileges. Please run as root or use sudo."
    exit 1
fi

# Stop and disable the service
systemctl stop ${PACKAGE_NAME}.service 2>/dev/null
systemctl disable ${PACKAGE_NAME}.service 2>/dev/null

# Remove the systemd service file and its symlink, if they exist
SYSTEMD_SERVICE_FILE=/etc/systemd/system/${PACKAGE_NAME}.service
SYSTEMD_SYMLINK_FILE=/etc/systemd/system/multi-user.target.wants/${PACKAGE_NAME}.service

if [ -f "${SYSTEMD_SERVICE_FILE}" ]; then
    rm -f "${SYSTEMD_SERVICE_FILE}"
    echo "Removed systemd service file at ${SYSTEMD_SERVICE_FILE}."
else
    echo "Systemd service file ${SYSTEMD_SERVICE_FILE} was not found."
fi

if [ -L "${SYSTEMD_SYMLINK_FILE}" ]; then
    rm -f "${SYSTEMD_SYMLINK_FILE}"
    echo "Removed systemd symlink at ${SYSTEMD_SYMLINK_FILE}."
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

# Reload systemd
systemctl daemon-reload

echo "NexusRFID Reader package has been uninstalled successfully."
