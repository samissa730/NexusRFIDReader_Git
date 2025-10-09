#!/bin/bash
set -euo pipefail

# Build NexusRFIDReader executable on Linux/RPi using PyInstaller and spec
# Usage: build.sh [--target win|linux]  (default: linux)

APP_NAME=NexusRFIDReader
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)
PROJECT_ROOT=$(realpath "$SCRIPT_DIR/../../")
SPEC_FILE="$PROJECT_ROOT/NexusRFIDReader.spec"

TARGET=linux
if [[ "${1:-}" == "--target" && -n "${2:-}" ]]; then
  TARGET="$2"
fi

if [ ! -f "$SPEC_FILE" ]; then
  echo "Spec file not found at $SPEC_FILE"
  exit 1
fi

cd "$PROJECT_ROOT"

if [[ "$TARGET" == "linux" ]]; then
  pyinstaller --clean --noconfirm "$SPEC_FILE"
  echo "Build completed. See dist/$APP_NAME/$APP_NAME"
elif [[ "$TARGET" == "win" ]]; then
  if ! command -v docker >/dev/null 2>&1; then
    echo "Docker not found. Install Docker or run the Windows build on Windows."
    exit 1
  fi
  echo "Building Windows binary via Docker (wine/pyinstaller) container..."
  docker run --rm -v "$PROJECT_ROOT":"/src" cdrx/pyinstaller-windows:python3 bash -lc \
    "cd /src && pyinstaller --clean --noconfirm NexusRFIDReader.spec"
  echo "Windows build completed under dist/NexusRFIDReader/NexusRFIDReader.exe"
else
  echo "Unknown target: $TARGET"
  exit 1
fi

