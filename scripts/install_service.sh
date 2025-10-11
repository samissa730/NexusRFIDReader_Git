#!/bin/bash

# Determine the directory the script is run from
SCRIPT_DIR=$(dirname "$(realpath "$0")")
PROJECT_DIR=$(dirname "$SCRIPT_DIR")

echo "Script directory: $SCRIPT_DIR"
echo "Project directory: $PROJECT_DIR"
echo "Main.py path: $PROJECT_DIR/main.py"

# Verify main.py exists
if [ ! -f "$PROJECT_DIR/main.py" ]; then
    echo "ERROR: main.py not found at $PROJECT_DIR/main.py"
    exit 1
fi

# Get the Python interpreter path
PYTHON_PATH=$(which python3)
if [ -z "$PYTHON_PATH" ]; then
    echo "Python3 is not installed. Please install Python3."
    exit 1
fi

# Define the systemd service name
SERVICE_NAME="nexusrfid"

# Create the systemd service file content
SERVICE_CONTENT="[Unit]
Description=NexusRFID Reader Application
After=network.target
Wants=display-manager.service

[Service]
Type=simple
ExecStart=$PYTHON_PATH $PROJECT_DIR/main.py
WorkingDirectory=$PROJECT_DIR
Restart=always
RestartSec=5
User=$(whoami)
Environment=PYTHONUNBUFFERED=1
Environment=QT_DEBUG_PLUGINS=1
Environment=DISPLAY=:0
StandardOutput=journal
StandardError=journal
SyslogIdentifier=nexusrfid

[Install]
WantedBy=multi-user.target
"

# Save service file
SERVICE_FILE="/etc/systemd/system/$SERVICE_NAME.service"

# Request sudo permissions upfront
if [ "$EUID" -ne 0 ]; then
    echo "This script requires administrative privileges. Please run as root or use sudo."
    exit 1
fi

echo "$SERVICE_CONTENT" > "$SERVICE_FILE"
# Set permissions
chmod 644 "$SERVICE_FILE"
# Reload systemd to register the new service
systemctl daemon-reload
# Enable the service to start on boot
systemctl enable "$SERVICE_NAME"
# Start the service immediately
systemctl start "$SERVICE_NAME"
# Check the status of the service
systemctl status "$SERVICE_NAME"
