#!/usr/bin/env python3
"""
Cron-based automatic certificate renewal for localtesting.

Runs once per cron invocation: reads current device cert, checks time left until
expiry. If time left < threshold (default 60s), re-enrolls via EST and overwrites
cert/key/chain. Uses a lockfile so overlapping cron runs do not run renewal twice.

Usage:
  python auto_renew_cert.py [--threshold SECS] [--cert-dir DIR]
  Or from crontab (every 2 minutes):
  */2 * * * * /usr/bin/python3 /path/to/localtesting/auto_renew_cert.py >> /path/to/localtesting/auto_renew.log 2>&1

Requires:
  - Docker step-ca + EST running (https://localhost:9443/est)
  - An initial cert already present (run test_est_enrollment.py or test_renew_workflow.py once)
"""

import argparse
import fcntl
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent))

from utils_Test.est_client import (
    enroll_certificate_via_est,
    get_ca_certs,
    verify_certificate,
)
from utils_Test.test_x509_est_device_setup import (
    generate_csr_and_key_pem,
    get_cert_cn_and_expiry,
)

EST_SERVER_URL = "https://127.0.0.1:9443/est"
BOOTSTRAP_TOKEN = "changeme"
REGISTRATION_ID = "test-device-renew"
DEFAULT_CERT_DIR = SCRIPT_DIR / "renew_workflow_output"
DEFAULT_THRESHOLD_SECS = 60
LOCK_FILE = ".auto_renew.lock"
STALE_LOCK_SECS = 90  # If lock file is older than this, remove it so we can proceed (must be < cron interval, e.g. 2 min)


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def _try_lock(cert_dir: Path):
    """Acquire exclusive lock in cert_dir. Returns (True, open_file) or (False, None). Caller must close file to release lock."""
    lock_path = cert_dir / LOCK_FILE
    f = None
    try:
        cert_dir.mkdir(parents=True, exist_ok=True)
        f = open(lock_path, "w")
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        f.write(str(os.getpid()))
        f.flush()
        return True, f
    except (BlockingIOError, OSError):
        if f is not None:
            try:
                f.close()
            except Exception:
                pass
        return False, None
    except Exception:
        if f is not None:
            try:
                f.close()
            except Exception:
                pass
        return False, None


def main() -> int:
    parser = argparse.ArgumentParser(description="Cron: check cert expiry and renew via EST if needed")
    parser.add_argument(
        "--threshold",
        type=int,
        default=DEFAULT_THRESHOLD_SECS,
        help=f"Renew when time left (seconds) < this (default: {DEFAULT_THRESHOLD_SECS})",
    )
    parser.add_argument(
        "--cert-dir",
        type=Path,
        default=DEFAULT_CERT_DIR,
        help=f"Directory containing device_cert.pem (default: {DEFAULT_CERT_DIR})",
    )
    args = parser.parse_args()
    cert_dir = args.cert_dir.resolve()
    cert_path = cert_dir / "device_cert.pem"
    key_path = cert_dir / "device_key.pem"
    chain_path = cert_dir / "device_chain.pem"

    _log(f"START pid={os.getpid()} cert_dir={cert_dir} threshold={args.threshold}s")

    if not cert_path.is_file():
        _log(f"ERROR: No cert at {cert_path}. Run test_est_enrollment.py or test_renew_workflow.py first.")
        return 1

    # Remove stale lock file (e.g. left behind by crashed run) so we don't skip forever
    lock_path = cert_dir / LOCK_FILE
    if lock_path.is_file():
        try:
            age_secs = (datetime.now(timezone.utc).timestamp() - lock_path.stat().st_mtime)
            if age_secs > STALE_LOCK_SECS:
                lock_path.unlink()
                _log(f"Removed stale lock file (age {int(age_secs)}s > {STALE_LOCK_SECS}s).")
            else:
                _log(f"Lock file exists, age {int(age_secs)}s (stale if > {STALE_LOCK_SECS}s).")
        except Exception as ex:
            _log(f"WARN: Could not stat/remove lock file: {ex}")
    else:
        _log("No existing lock file.")

    acquired, lock_file = _try_lock(cert_dir)
    if not acquired:
        _log("SKIP: Another renewal in progress (lock held).")
        return 0

    _log("Lock acquired.")

    try:
        cert_pem = cert_path.read_bytes()
        cn, not_after = get_cert_cn_and_expiry(cert_pem)
        if not_after is None:
            _log("ERROR: Could not read cert expiry.")
            return 1

        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        if not_after.tzinfo is not None:
            not_after = not_after.replace(tzinfo=None)
        time_left_secs = (not_after - now_utc).total_seconds()

        _log(f"Current cert CN={cn} expires {not_after} time_left={int(time_left_secs)}s threshold={args.threshold}s")

        if time_left_secs >= args.threshold:
            _log(f"OK: Cert valid for {int(time_left_secs)}s (>= {args.threshold}s), no renewal.")
            return 0

        _log(f"Renewing: time left {int(time_left_secs)}s < {args.threshold}s for CN={cn}")

        _log("Generating new CSR and key...")
        key_pem, csr_pem = generate_csr_and_key_pem(REGISTRATION_ID)
        _log(f"Calling EST {EST_SERVER_URL} for CN={REGISTRATION_ID}...")
        cert_pem_new, chain_pem = enroll_certificate_via_est(
            EST_SERVER_URL, BOOTSTRAP_TOKEN, csr_pem, verify_ssl=False
        )
        _log("Verifying new certificate...")
        if not verify_certificate(cert_pem_new, chain_pem or None):
            _log("ERROR: New cert failed verification.")
            return 1

        cert_dir.mkdir(parents=True, exist_ok=True)
        cert_path.write_bytes(cert_pem_new)
        key_path.write_bytes(key_pem)
        if chain_pem:
            chain_path.write_bytes(chain_pem)
        try:
            key_path.chmod(0o600)
        except Exception:
            pass

        cn2, not_after2 = get_cert_cn_and_expiry(cert_pem_new)
        _log(f"Wrote {cert_path} {key_path}" + (f" {chain_path}" if chain_pem else ""))
        _log(f"OK: Renewed cert for CN={cn2}, expires {not_after2}")
        return 0
    except Exception as e:
        _log(f"ERROR: Renewal failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        if lock_file is not None:
            try:
                lock_file.close()
            except Exception:
                pass
        try:
            (cert_dir / LOCK_FILE).unlink(missing_ok=True)
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
