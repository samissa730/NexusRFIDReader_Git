#!/bin/bash
# Setup script for step-ca EST server in Docker
# This script initializes step-ca and prepares it for EST enrollment testing

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "  Setting up step-ca EST Server"
echo "=========================================="

# Create directories (secrets needed for password file before init)
echo "Creating directories..."
mkdir -p step-ca-data step-ca-data/secrets step-ca-config

# Create password file so Docker container can read it (process substitution doesn't work inside container).
# Container runs as non-root user; if script is run with sudo, file would be root-only so use 644.
STEPCA_PASSWORD="${STEPCA_PASSWORD:-changeme}"
echo "Using CA password: ${STEPCA_PASSWORD}"
printf '%s' "$STEPCA_PASSWORD" > step-ca-data/secrets/password
chmod 644 step-ca-data/secrets/password

# Check if CA is already initialized
if [ -f "step-ca-data/config/ca.json" ]; then
    echo "✓ CA already initialized"
    echo "  To reinitialize, delete step-ca-data/ and step-ca-config/ directories"
else
    echo "Initializing step-ca..."
    echo ""
    
    # Initialize CA using Docker (password from file - works inside container)
    docker run --rm -it \
        -v "$(pwd)/step-ca-data:/home/step" \
        smallstep/step-ca:latest \
        step ca init \
        --name "Nexus IoT CA" \
        --dns localhost \
        --address ":8443" \
        --provisioner admin \
        --password-file /home/step/secrets/password
    
    echo ""
    echo "✓ CA initialized"
fi

# Copy config to config directory for reference
if [ -f "step-ca-data/config/ca.json" ]; then
    echo "Copying configuration..."
    mkdir -p step-ca-config/config
    cp step-ca-data/config/ca.json step-ca-config/config/ 2>/dev/null || true
    echo "✓ Configuration copied"
fi

# Enable EST in ca.json (in step-ca-data - this is what the container uses)
echo "Enabling EST in configuration..."
if [ -f "step-ca-data/config/ca.json" ]; then
    # Use Python to add EST configuration
    python3 << 'PYTHON_SCRIPT'
import json
import sys

config_path = "step-ca-data/config/ca.json"
try:
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    # Add EST configuration if not present
    if "est" not in config:
        config["est"] = {
            "enabled": True,
            "bootstrapToken": "changeme"
        }
        
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        print("✓ EST enabled in configuration")
    else:
        print("✓ EST already configured")
        
except Exception as e:
    print(f"Error updating config: {e}")
    sys.exit(1)
PYTHON_SCRIPT
else
    echo "✗ Configuration file not found. Please initialize CA first."
    exit 1
fi

# Ensure step-ca can read password when running (container uses /home/step)
if [ ! -f "step-ca-data/secrets/password" ]; then
    printf '%s' "${STEPCA_PASSWORD:-changeme}" > step-ca-data/secrets/password
    chmod 644 step-ca-data/secrets/password
    echo "✓ Password file created for container"
fi

echo ""
echo "=========================================="
echo "  Setup Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. If step-ca container is already running, stop it first:"
echo "   docker compose down"
echo ""
echo "2. Start the EST server:"
echo "   docker compose up -d"
echo ""
echo "3. Check server status:"
echo "   docker compose logs -f step-ca"
echo ""
echo "4. Test EST enrollment:"
echo "   python test_est_enrollment.py"
echo ""
echo "Bootstrap token: changeme"
echo "EST Server URL: https://localhost:8443/est"
echo ""
