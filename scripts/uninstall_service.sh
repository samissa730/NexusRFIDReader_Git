#!/bin/bash

# Define the systemd service name
SERVICE_NAME="nexusrfid"

# Request sudo permissions upfront
if [ "$EUID" -ne 0 ]; then
    echo "This script requires administrative privileges. Please run as root or use sudo."
    exit 1
fi

# Stop the service if it's running
systemctl stop "$SERVICE_NAME" 2>/dev/null

# Disable the service
systemctl disable "$SERVICE_NAME" 2>/dev/null

# Remove the service file
SERVICE_FILE="/etc/systemd/system/$SERVICE_NAME.service"
if [ -f "$SERVICE_FILE" ]; then
    rm -f "$SERVICE_FILE"
    echo "Removed systemd service file at $SERVICE_FILE"
else
    echo "Service file $SERVICE_FILE was not found"
fi

# Reload systemd
systemctl daemon-reload

echo "NexusRFID service has been uninstalled successfully."
