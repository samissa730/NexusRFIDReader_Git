#!/bin/bash
# Quick test script for EST enrollment
# This script checks prerequisites and runs the EST enrollment test

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "  Quick EST Enrollment Test"
echo "=========================================="

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "✗ Docker is not running. Please start Docker first."
    exit 1
fi
echo "✓ Docker is running"

# Check if step-ca container is running
if ! docker-compose ps | grep -q "step-ca-est-test.*Up"; then
    echo ""
    echo "⚠ EST server is not running. Starting it..."
    docker-compose up -d
    echo "Waiting for server to start..."
    sleep 5
fi

# Check if server is healthy
if docker-compose ps | grep -q "step-ca-est-test.*Up"; then
    echo "✓ EST server is running"
else
    echo "✗ EST server failed to start. Check logs:"
    echo "  docker-compose logs step-ca"
    exit 1
fi

# Check Python dependencies
echo ""
echo "Checking Python dependencies..."
if python3 -c "import cryptography" 2>/dev/null; then
    echo "✓ cryptography installed"
else
    echo "✗ cryptography not installed. Installing..."
    pip install cryptography requests
fi

if python3 -c "import requests" 2>/dev/null; then
    echo "✓ requests installed"
else
    echo "✗ requests not installed. Installing..."
    pip install requests
fi

# Run the test
echo ""
echo "=========================================="
echo "  Running EST Enrollment Test"
echo "=========================================="
python3 test_est_enrollment.py

echo ""
echo "=========================================="
echo "  Test Complete!"
echo "=========================================="
