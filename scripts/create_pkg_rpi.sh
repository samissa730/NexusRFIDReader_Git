#!/bin/bash

# Define package variables
PACKAGE_NAME=NexusRFIDReader
PACKAGE_VERSION=1.0
ARCHITECTURE=$(dpkg --print-architecture)
DESCRIPTION="NexusRFID Reader Application for RFID and GPS data reading."
MAINTAINER="NexusRFID Team"

# Create directory structure
echo "Creating directory structure..."
mkdir -p ${PACKAGE_NAME}-${PACKAGE_VERSION}/DEBIAN
mkdir -p ${PACKAGE_NAME}-${PACKAGE_VERSION}/usr/local/bin
mkdir -p ${PACKAGE_NAME}-${PACKAGE_VERSION}/usr/share/applications
mkdir -p ${PACKAGE_NAME}-${PACKAGE_VERSION}/usr/share/icons/hicolor/512x512/apps
mkdir -p ${PACKAGE_NAME}-${PACKAGE_VERSION}/etc/skel/.config/autostart

# Copy files to package
echo "Copying files..."
cp NexusRFIDReader ${PACKAGE_NAME}-${PACKAGE_VERSION}/usr/local/bin/
cp ui/img/icon.png ${PACKAGE_NAME}-${PACKAGE_VERSION}/usr/share/icons/hicolor/512x512/apps/${PACKAGE_NAME}.png 2>/dev/null || echo "Icon not found, skipping..."

# Create the monitoring script
echo "Creating monitoring script..."
cat > ${PACKAGE_NAME}-${PACKAGE_VERSION}/usr/local/bin/monitor_nexus_rfid.sh <<'EOL'
#!/bin/bash

APP_NAME="NexusRFIDReader"
APP_PATH="/usr/local/bin/NexusRFIDReader"

while true; do
    if ! pgrep -x "$APP_NAME" > /dev/null; then
        echo "$APP_NAME is not running. Starting..."
        $APP_PATH &
    else
        echo "$APP_NAME is running."
    fi
    sleep 5
done
EOL

chmod +x ${PACKAGE_NAME}-${PACKAGE_VERSION}/usr/local/bin/monitor_nexus_rfid.sh

# Create .desktop file for application menu
echo "Creating application .desktop file..."
cat > ${PACKAGE_NAME}-${PACKAGE_VERSION}/usr/share/applications/${PACKAGE_NAME}.desktop <<EOL
[Desktop Entry]
Version=1.0
Name=NexusRFID Reader
Comment=NexusRFID Reader Application for RFID and GPS data reading
Exec=/usr/local/bin/NexusRFIDReader
Icon=${PACKAGE_NAME}
Terminal=false
Type=Application
Categories=Utility;
EOL

# Create autostart entry to run the monitoring script on login
echo "Creating autostart entry..."
cat > ${PACKAGE_NAME}-${PACKAGE_VERSION}/etc/skel/.config/autostart/monitor-nexus-rfid.desktop <<EOL
[Desktop Entry]
Type=Application
Exec=/usr/local/bin/monitor_nexus_rfid.sh
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
Name=Monitor NexusRFID Reader
EOL

# Create control file
echo "Creating DEBIAN control file..."
cat > ${PACKAGE_NAME}-${PACKAGE_VERSION}/DEBIAN/control <<EOL
Package: ${PACKAGE_NAME}
Version: ${PACKAGE_VERSION}
Section: utils
Priority: optional
Architecture: ${ARCHITECTURE}
Maintainer: ${MAINTAINER}
Depends: libxcb-xinerama0, libxcb-cursor0, libx11-xcb1, libxcb1, libxfixes3, libxi6, libxrender1, libxcb-render0, libxcb-shape0, libxcb-xfixes0, x11-xserver-utils
Description: ${DESCRIPTION}
EOL

# Create postinst script to set up the environment
echo "Creating postinst script..."
cat > ${PACKAGE_NAME}-${PACKAGE_VERSION}/DEBIAN/postinst <<'EOL'
#!/bin/bash

set -e

# Create a data directory for NexusRFIDReader
NEXUS_DATA_DIR=/var/lib/nexusrfid
if [ ! -d "$NEXUS_DATA_DIR" ]; then
    mkdir -p "$NEXUS_DATA_DIR"
    chmod -R 750 "$NEXUS_DATA_DIR"
    echo "Created writable directory at $NEXUS_DATA_DIR for NexusRFIDReader data."
fi

# Copy autostart configurations to existing users' directories
for user_dir in /home/*; do
    if [ -d "$user_dir" -a -w "$user_dir" ]; then
        user_autostart_dir="$user_dir/.config/autostart"
        mkdir -p "$user_autostart_dir"
        cp /etc/skel/.config/autostart/monitor-nexus-rfid.desktop "$user_autostart_dir/"
        chown $(basename "$user_dir"):$(basename "$user_dir") "$user_autostart_dir/monitor-nexus-rfid.desktop"
    fi
done

EOL

# Make the postinst script executable
chmod 0755 ${PACKAGE_NAME}-${PACKAGE_VERSION}/DEBIAN/postinst

# Build the .deb package
echo "Building the .deb package..."
dpkg-deb --build ${PACKAGE_NAME}-${PACKAGE_VERSION}

# Clean up the build directory
echo "Cleaning up..."
rm -rf ${PACKAGE_NAME}-${PACKAGE_VERSION}

echo "Package ${PACKAGE_NAME}-${PACKAGE_VERSION}.deb has been created successfully."
echo "To install: sudo apt install ./${PACKAGE_NAME}-${PACKAGE_VERSION}.deb"
