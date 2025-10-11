#!/bin/bash

# Define the systemd service name
SERVICE_NAME="nexusrfid"

# Stop and disable the user service
systemctl --user stop "$SERVICE_NAME" 2>/dev/null
systemctl --user disable "$SERVICE_NAME" 2>/dev/null

# Remove the service file
USER_SYSTEMD_DIR="$HOME/.config/systemd/user"
SERVICE_FILE="$USER_SYSTEMD_DIR/$SERVICE_NAME.service"

if [ -f "$SERVICE_FILE" ]; then
    rm -f "$SERVICE_FILE"
    echo "Removed user service file at $SERVICE_FILE"
else
    echo "User service file $SERVICE_FILE was not found"
fi

# Reload systemd user configuration
systemctl --user daemon-reload

echo "NexusRFID user service has been uninstalled successfully."
