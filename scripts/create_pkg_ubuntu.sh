#!/bin/bash

# Define package variables
PACKAGE_NAME=NexusRFIDReader
PACKAGE_VERSION=1.0
ARCHITECTURE=$(dpkg --print-architecture)
DESCRIPTION="NexusRFID Reader Application for RFID and GPS data reading."
MAINTAINER="NexusRFID Team"

# Create directory structure for the package
echo "Creating directory structure..."
mkdir -p ${PACKAGE_NAME}-${PACKAGE_VERSION}/DEBIAN
mkdir -p ${PACKAGE_NAME}-${PACKAGE_VERSION}/usr/local/bin
mkdir -p ${PACKAGE_NAME}-${PACKAGE_VERSION}/usr/share/applications
mkdir -p ${PACKAGE_NAME}-${PACKAGE_VERSION}/usr/share/icons/hicolor/512x512/apps
mkdir -p ${PACKAGE_NAME}-${PACKAGE_VERSION}/etc/systemd/system

# Copy files to package
echo "Copying files..."
cp NexusRFIDReader ${PACKAGE_NAME}-${PACKAGE_VERSION}/usr/local/bin/
cp ui/img/icon.png ${PACKAGE_NAME}-${PACKAGE_VERSION}/usr/share/icons/hicolor/512x512/apps/${PACKAGE_NAME}.png 2>/dev/null || echo "Icon not found, skipping..."

# Make the binary executable
chmod 0755 ${PACKAGE_NAME}-${PACKAGE_VERSION}/usr/local/bin/NexusRFIDReader

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

# Create systemd service file
echo "Creating systemd service file..."
cat > ${PACKAGE_NAME}-${PACKAGE_VERSION}/etc/systemd/system/${PACKAGE_NAME}.service <<EOL
[Unit]
Description=NexusRFID Reader Application
After=network.target
Wants=display-manager.service

[Service]
Type=simple
WorkingDirectory=/var/lib/nexusrfid
ExecStart=/usr/local/bin/NexusRFIDReader
Environment=QT_DEBUG_PLUGINS=1
Environment=DISPLAY=:0
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=nexusrfid

[Install]
WantedBy=multi-user.target
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

# Create postinst script to configure system
echo "Creating postinst script..."
cat > ${PACKAGE_NAME}-${PACKAGE_VERSION}/DEBIAN/postinst <<'EOL'
#!/bin/bash
set -e

NEXUS_DATA_DIR=/var/lib/nexusrfid

# Create the data directory if it doesn't exist and fix permissions
if [ ! -d "$NEXUS_DATA_DIR" ]; then
    mkdir -p "$NEXUS_DATA_DIR"
fi

# Set permissions to allow root to access this directory
chown -R root:root "$NEXUS_DATA_DIR"
chmod -R 755 "$NEXUS_DATA_DIR"

# Reload systemd manager configuration, enable the service, and start it
systemctl daemon-reload
systemctl enable NexusRFIDReader.service
systemctl start NexusRFIDReader.service
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
