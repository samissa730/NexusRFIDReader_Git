#!/usr/bin/env python3
"""Docker healthcheck: verify the main process (gunicorn) is running.
We do NOT connect to port 9443 from inside the container: a TCP connect and
immediate close would leave gunicorn's worker blocked waiting for an HTTP
request (long read timeout), tying up the single worker and causing SSL
timeouts for clients. So we only check that PID 1 is alive."""

import os
import sys

def main():
    # PID 1 in container is gunicorn master; if it's gone, we're unhealthy
    try:
        os.kill(1, 0)
    except OSError:
        sys.exit(1)
    sys.exit(0)

if __name__ == "__main__":
    main()
