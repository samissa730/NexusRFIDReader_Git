#!/bin/bash

# Build script for NexusRFID Reader using PyInstaller
# This script creates a standalone executable for the application

echo "Building NexusRFID Reader executable..."

# Check if PyInstaller is installed
if ! command -v pyinstaller &> /dev/null; then
    echo "PyInstaller is not installed. Installing..."
    pip install pyinstaller
fi

# Determine the platform
PLATFORM=$(uname -s)
echo "Building for platform: $PLATFORM"

# Set the icon path
ICON_PATH="ui/img/icon.png"
if [ ! -f "$ICON_PATH" ]; then
    echo "Warning: Icon file not found at $ICON_PATH"
    ICON_PATH=""
fi

# Build command based on platform
if [ "$PLATFORM" = "Linux" ]; then
    # Linux build
    if [ -n "$ICON_PATH" ]; then
        pyinstaller --clean --onefile --icon="$ICON_PATH" --name=NexusRFIDReader main.py
    else
        pyinstaller --clean --onefile --name=NexusRFIDReader main.py
    fi
elif [ "$PLATFORM" = "Darwin" ]; then
    # macOS build
    if [ -n "$ICON_PATH" ]; then
        pyinstaller --clean --onefile --icon="$ICON_PATH" --name=NexusRFIDReader main.py
    else
        pyinstaller --clean --onefile --name=NexusRFIDReader main.py
    fi
else
    echo "Unsupported platform: $PLATFORM"
    exit 1
fi

# Check if build was successful
if [ -f "dist/NexusRFIDReader" ]; then
    echo "Build successful! Executable created at: dist/NexusRFIDReader"
    chmod +x dist/NexusRFIDReader
else
    echo "Build failed!"
    exit 1
fi
