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

# Define the systemd service name
SERVICE_NAME="nexusrfid"

# Create user systemd directory if it doesn't exist
USER_SYSTEMD_DIR="$HOME/.config/systemd/user"
mkdir -p "$USER_SYSTEMD_DIR"

# Create the systemd user service file content
SERVICE_CONTENT="[Unit]
Description=NexusRFID Reader Application
After=graphical-session.target

[Service]
Type=simple
ExecStart=$PROJECT_DIR/scripts/run_app.sh
WorkingDirectory=$PROJECT_DIR
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1
Environment=QT_DEBUG_PLUGINS=1
Environment=DISPLAY=:0
Environment=XDG_RUNTIME_DIR=/run/user/%i
Environment=WAYLAND_DISPLAY=wayland-0
Environment=QT_QPA_PLATFORM=xcb
StandardOutput=journal
StandardError=journal
SyslogIdentifier=nexusrfid

[Install]
WantedBy=default.target
"

# Save service file
SERVICE_FILE="$USER_SYSTEMD_DIR/$SERVICE_NAME.service"

echo "$SERVICE_CONTENT" > "$SERVICE_FILE"
echo "Created user service file at $SERVICE_FILE"

# Reload systemd user configuration
systemctl --user daemon-reload

# Enable the service to start on login
systemctl --user enable "$SERVICE_NAME"

# Start the service immediately
systemctl --user start "$SERVICE_NAME"

# Check the status of the service
systemctl --user status "$SERVICE_NAME"

echo ""
echo "Service installed as user service!"
echo "To manage the service:"
echo "  systemctl --user status nexusrfid"
echo "  systemctl --user stop nexusrfid"
echo "  systemctl --user start nexusrfid"
echo "  systemctl --user restart nexusrfid"
echo "  journalctl --user -u nexusrfid -f"
