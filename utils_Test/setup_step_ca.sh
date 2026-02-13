#!/bin/bash
# Setup script for step-ca EST server in Docker
# This script initializes step-ca and prepares it for EST enrollment testing

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "  Setting up step-ca EST Server"
echo "=========================================="

# Create directories
echo "Creating directories..."
mkdir -p step-ca-data step-ca-config

# Check if CA is already initialized
if [ -f "step-ca-data/config/ca.json" ]; then
    echo "✓ CA already initialized"
    echo "  To reinitialize, delete step-ca-data/ and step-ca-config/ directories"
else
    echo "Initializing step-ca..."
    echo ""
    echo "You will be prompted for:"
    echo "  - CA name (default: Nexus IoT CA)"
    echo "  - DNS names (default: localhost)"
    echo "  - Provisioner name (default: admin)"
    echo "  - Provisioner password (default: changeme)"
    echo ""
    
    # Initialize CA using Docker
    docker run --rm -it \
        -v "$(pwd)/step-ca-data:/home/step" \
        smallstep/step-ca:latest \
        step ca init \
        --name "Nexus IoT CA" \
        --dns localhost \
        --address :8443 \
        --provisioner admin \
        --password-file <(echo "changeme")
    
    echo ""
    echo "✓ CA initialized"
fi

# Copy config to config directory
if [ -f "step-ca-data/config/ca.json" ]; then
    echo "Copying configuration..."
    cp step-ca-data/config/ca.json step-ca-config/ 2>/dev/null || true
    
    # Copy intermediate CA key if it exists
    if [ -f "step-ca-data/secrets/intermediate_ca_key" ]; then
        mkdir -p step-ca-config/secrets
        cp step-ca-data/secrets/intermediate_ca_key step-ca-config/secrets/ 2>/dev/null || true
    fi
    
    echo "✓ Configuration copied"
fi

# Enable EST in ca.json
echo "Enabling EST in configuration..."
if [ -f "step-ca-config/ca.json" ]; then
    # Use Python to add EST configuration
    python3 << 'PYTHON_SCRIPT'
import json
import sys

config_path = "step-ca-config/ca.json"
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

echo ""
echo "=========================================="
echo "  Setup Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Start the EST server:"
echo "   docker-compose up -d"
echo ""
echo "2. Check server status:"
echo "   docker-compose logs -f step-ca"
echo ""
echo "3. Test EST enrollment:"
echo "   python test_est_enrollment.py"
echo ""
echo "Bootstrap token: changeme"
echo "EST Server URL: https://localhost:8443/est"
echo ""
