#!/bin/bash
# Run docker compose with DOCKER_API_VERSION=1.41 for older Docker daemons
# (avoids "client version 1.52 is too new. Maximum supported API version is 1.41")
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
export DOCKER_API_VERSION=1.41
exec docker compose "$@"
