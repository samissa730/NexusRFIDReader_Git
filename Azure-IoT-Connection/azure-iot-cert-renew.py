#!/usr/bin/env python3
"""
Systemd-triggered X.509 certificate renewal for Azure IoT (EST).

Reads provisioning config, checks device cert expiry. If time left < threshold,
re-enrolls via EST, writes new cert/key, and restarts azure-iot.service.

Designed to be run by azure-iot-cert-renew.service (systemd timer).
Requires estServerUrl and estBootstrapToken in provisioning_config.json
(device_setup saves these when configured).

Usage:
  python3 azure-iot-cert-renew.py [--threshold SECS]
  Default threshold: 86400 (renew when less than 24 hours left).
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Run from /opt/nexuslocate/bin; same dir as est_client
_script_dir = Path(__file__).resolve().parent
if str(_script_dir) not in sys.path:
    sys.path.insert(0, str(_script_dir))

CONFIG_PATH = Path("/etc/nexuslocate/config/provisioning_config.json")
DEFAULT_THRESHOLD_SECS = 86400  # 24 hours


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check device cert expiry and renew via EST if needed (systemd timer)."
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=DEFAULT_THRESHOLD_SECS,
        help=f"Renew when time left (seconds) < this (default: {DEFAULT_THRESHOLD_SECS})",
    )
    args = parser.parse_args()

    _log(f"START pid={os.getpid()} threshold={args.threshold}s")

    if not CONFIG_PATH.is_file():
        _log("SKIP: No provisioning config; run device_setup.py first.")
        return 0

    try:
        config = json.loads(CONFIG_PATH.read_text())
    except Exception as e:
        _log(f"ERROR: Failed to read config: {e}")
        return 1

    cert_path = Path(config.get("certPath") or "/etc/nexuslocate/pki/device.crt")
    key_path = Path(config.get("keyPath") or "/etc/nexuslocate/pki/device.key")
    registration_id = config.get("registrationId") or ""
    est_server_url = (config.get("estServerUrl") or "").strip()
    est_bootstrap_token = (config.get("estBootstrapToken") or "").strip()

    if not est_server_url or not est_bootstrap_token:
        _log("SKIP: estServerUrl/estBootstrapToken not in config; automatic renewal disabled.")
        return 0

    if not cert_path.is_file():
        _log(f"ERROR: No cert at {cert_path}. Run device_setup.py first.")
        return 1

    try:
        from est_client import (
            enroll_certificate_via_est,
            generate_csr_and_key_pem,
            get_cert_cn_and_expiry,
            verify_certificate,
        )
    except ImportError as e:
        _log(f"ERROR: est_client not available: {e}")
        return 1

    try:
        cert_pem = cert_path.read_bytes()
        cn, not_after = get_cert_cn_and_expiry(cert_pem)
        if not_after is None:
            _log("ERROR: Could not read cert expiry.")
            return 1

        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        if not_after.tzinfo is not None:
            not_after_naive = not_after.replace(tzinfo=None)
        else:
            not_after_naive = not_after
        time_left_secs = (not_after_naive - now_utc).total_seconds()

        _log(
            f"Current cert CN={cn} expires {not_after_naive} "
            f"time_left={int(time_left_secs)}s threshold={args.threshold}s"
        )

        if time_left_secs >= args.threshold:
            _log(
                f"OK: Cert valid for {int(time_left_secs)}s (>= {args.threshold}s), no renewal."
            )
            return 0

        _log(f"Renewing: time left {int(time_left_secs)}s < {args.threshold}s for CN={cn}")

        rid = (cn or registration_id or "device").strip()
        if not rid:
            _log("ERROR: No registration ID or CN for renewal.")
            return 1

        key_pem, csr_pem = generate_csr_and_key_pem(rid)
        _log(f"Calling EST {est_server_url} for CN={rid}...")
        cert_pem_new, chain_pem = enroll_certificate_via_est(
            est_server_url, est_bootstrap_token, csr_pem, verify_ssl=False
        )
        _log("Verifying new certificate...")
        if not verify_certificate(cert_pem_new, chain_pem or None):
            _log("ERROR: New cert failed verification.")
            return 1

        cert_path.parent.mkdir(parents=True, exist_ok=True)
        cert_path.write_bytes(cert_pem_new)
        key_path.write_bytes(key_pem)
        try:
            key_path.chmod(0o600)
        except Exception:
            pass

        cn2, not_after2 = get_cert_cn_and_expiry(cert_pem_new)
        _log(f"Wrote {cert_path} {key_path}")
        _log(f"OK: Renewed cert for CN={cn2}, expires {not_after2}")

        _log("Restarting azure-iot.service...")
        r = subprocess.run(
            ["systemctl", "restart", "azure-iot.service"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if r.returncode != 0:
            _log(f"WARNING: systemctl restart failed: {r.stderr or r.stdout}")
        else:
            _log("OK: azure-iot.service restarted.")
        return 0

    except Exception as e:
        _log(f"ERROR: Renewal failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
