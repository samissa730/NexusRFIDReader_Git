#!/usr/bin/env python3
"""Docker healthcheck: GET https://127.0.0.1:9443/health, expect 200 and 'ok'."""
import sys
import ssl
import urllib.request

def main():
    url = "https://127.0.0.1:9443/health"
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, context=ctx, timeout=5) as u:
            if u.getcode() != 200:
                sys.exit(1)
            body = u.read()
            if b"ok" not in body:
                sys.exit(1)
    except Exception:
        sys.exit(1)
    sys.exit(0)

if __name__ == "__main__":
    main()
