#!/bin/bash

# Determine the directory the script is run from
SCRIPT_DIR=$(dirname "$(realpath "$0")")
PROJECT_DIR=$(dirname "$SCRIPT_DIR")

echo "Script directory: $SCRIPT_DIR"
echo "Project directory: $PROJECT_DIR"
echo "Main.py path: $PROJECT_DIR/main.py"

# Verify run_app.sh exists and make it executable
if [ ! -f "$PROJECT_DIR/scripts/run_app.sh" ]; then
    echo "ERROR: run_app.sh not found at $PROJECT_DIR/scripts/run_app.sh"
    exit 1
fi
chmod +x "$PROJECT_DIR/scripts/run_app.sh"
echo "Made run_app.sh executable"

# Check if virtual environment exists and use it, otherwise use system python
if [ -f "$PROJECT_DIR/venv/bin/python" ]; then
    PYTHON_PATH="$PROJECT_DIR/venv/bin/python"
    echo "Using virtual environment Python: $PYTHON_PATH"
elif [ -f "$PROJECT_DIR/venv/bin/python3" ]; then
    PYTHON_PATH="$PROJECT_DIR/venv/bin/python3"
    echo "Using virtual environment Python3: $PYTHON_PATH"
else
    PYTHON_PATH=$(which python3)
    echo "Using system Python3: $PYTHON_PATH"
    if [ -z "$PYTHON_PATH" ]; then
        echo "Python3 is not installed. Please install Python3."
        exit 1
    fi
fi

# Define the systemd service name
SERVICE_NAME="nexusrfid"

# Create the systemd service file content
SERVICE_CONTENT="[Unit]
Description=NexusRFID Reader Application
After=network.target graphical-session.target
Wants=graphical-session.target

[Service]
Type=simple
ExecStart=$PROJECT_DIR/scripts/run_app.sh
WorkingDirectory=$PROJECT_DIR
Restart=always
RestartSec=5
User=$(whoami)
Environment=PYTHONUNBUFFERED=1
Environment=QT_DEBUG_PLUGINS=1
Environment=DISPLAY=:0
Environment=XDG_RUNTIME_DIR=/run/user/$(id -u)
Environment=WAYLAND_DISPLAY=wayland-0
Environment=QT_QPA_PLATFORM=xcb
StandardOutput=journal
StandardError=journal
SyslogIdentifier=nexusrfid

[Install]
WantedBy=graphical.target
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
