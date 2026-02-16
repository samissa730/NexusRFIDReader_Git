#!/usr/bin/env python3
"""Docker healthcheck: verify port 9443 is open (TCP only). Avoids doing HTTP/HTTPS
to the same single-worker gunicorn, which would block the worker and cause timeouts."""
import sys
import socket

def main():
    try:
        with socket.create_connection(("127.0.0.1", 9443), timeout=3) as _:
            pass
    except Exception:
        sys.exit(1)
    sys.exit(0)

if __name__ == "__main__":
    main()
