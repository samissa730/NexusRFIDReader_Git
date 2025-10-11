#!/bin/bash

# Determine the directory the script is run from
PROJECT_DIR=$(dirname "$(dirname "$(realpath "$0")")")

echo "Project directory: $PROJECT_DIR"

# Check if virtual environment exists and activate it
if [ -d "$PROJECT_DIR/venv" ]; then
    echo "Activating virtual environment..."
    source "$PROJECT_DIR/venv/bin/activate"
    PYTHON_PATH=$(which python)
    echo "Using Python from virtual environment: $PYTHON_PATH"
else
    echo "No virtual environment found, using system Python"
    PYTHON_PATH=$(which python3)
    echo "Using system Python: $PYTHON_PATH"
fi

# Verify main.py exists
if [ ! -f "$PROJECT_DIR/main.py" ]; then
    echo "ERROR: main.py not found at $PROJECT_DIR/main.py"
    exit 1
fi

# Run the application
echo "Starting NexusRFID Reader Application..."
cd "$PROJECT_DIR"
exec "$PYTHON_PATH" main.py
