#!/bin/bash

# Determine the directory the script is run from
PROJECT_DIR=$(dirname "$(realpath "$0")/..")

# Get the Python interpreter path
PYTHON_PATH=$(which python3)
if [ -z "$PYTHON_PATH" ]; then
    echo "Python3 is not installed. Please install Python3."
    exit 1
fi

# Check if virtual environment exists and activate it
if [ -d "$PROJECT_DIR/venv" ]; then
    echo "Activating virtual environment..."
    source "$PROJECT_DIR/venv/bin/activate"
fi

# Run the application
echo "Starting NexusRFID Reader Application..."
cd "$PROJECT_DIR"
exec "$PYTHON_PATH" main.py
