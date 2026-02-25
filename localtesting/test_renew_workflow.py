#!/usr/bin/env python3
"""
Test 5-minute short-lived cert and renew workflow with local step-ca + EST.

- First enrollment: get device cert (valid 5m), verify and save.
- Optional: wait 5+ minutes then renew (re-enroll) and verify new cert works.
- Use saved certs with Azure IoT (group enrollment with CA) to connect and send data.

Usage:
    python test_renew_workflow.py              # Enroll once + re-enroll once (no wait)
    python test_renew_workflow.py --wait-renew # Enroll, wait 5m10s, renew, verify

Before running:
    cd localtesting && docker compose up -d --build
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils_Test.est_client import (
    enroll_certificate_via_est,
    get_ca_certs,
    verify_certificate,
)
from utils_Test.test_x509_est_device_setup import (
    generate_csr_and_key_pem,
    get_cert_cn_and_expiry,
)

# Same as localtesting docker-compose: EST at 9443, token changeme
EST_SERVER_URL = "https://127.0.0.1:9443/est"
BOOTSTRAP_TOKEN = "changeme"
REGISTRATION_ID = "test-device-renew"
OUTPUT_DIR = Path(__file__).parent / "renew_workflow_output"


def _section(title: str) -> None:
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def _info(msg: str) -> None:
    print(f"  {msg}")


def _ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def _err(msg: str) -> None:
    print(f"  ✗ {msg}")


def _serial(cert_pem: bytes) -> int:
    from cryptography.hazmat.backends import default_backend
    from cryptography import x509
    cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
    return cert.serial_number


def run_quick_renew_test() -> bool:
    """Enroll once, then re-enroll immediately (same CN). Verifies renewal path works."""
    _section("1. First enrollment (5-min short-lived cert)")
    OUTPUT_DIR.mkdir(exist_ok=True)
    key_pem, csr_pem = generate_csr_and_key_pem(REGISTRATION_ID)
    cert_pem_1, chain_pem = enroll_certificate_via_est(
        EST_SERVER_URL, BOOTSTRAP_TOKEN, csr_pem, verify_ssl=False
    )
    cn, not_after = get_cert_cn_and_expiry(cert_pem_1)
    _ok(f"Certificate issued for CN={cn}, expires {not_after}")
    if not verify_certificate(cert_pem_1, chain_pem or None):
        _err("First cert failed verification")
        return False
    _ok("First cert valid")
    serial_1 = _serial(cert_pem_1)

    _section("2. Re-enroll (renew) same device — no wait")
    key_pem_2, csr_pem_2 = generate_csr_and_key_pem(REGISTRATION_ID)
    cert_pem_2, chain_pem_2 = enroll_certificate_via_est(
        EST_SERVER_URL, BOOTSTRAP_TOKEN, csr_pem_2, verify_ssl=False
    )
    cn2, not_after_2 = get_cert_cn_and_expiry(cert_pem_2)
    _ok(f"Renewed cert for CN={cn2}, expires {not_after_2}")
    if not verify_certificate(cert_pem_2, chain_pem_2 or None):
        _err("Renewed cert failed verification")
        return False
    serial_2 = _serial(cert_pem_2)
    if serial_2 == serial_1:
        _err("Expected different serial after renew (got same)")
        return False
    _ok("Renewed cert has different serial and is valid")

    # Save latest cert/key for Azure
    (OUTPUT_DIR / "device_cert.pem").write_bytes(cert_pem_2)
    (OUTPUT_DIR / "device_key.pem").write_bytes(key_pem_2)
    (OUTPUT_DIR / "device_chain.pem").write_bytes(chain_pem_2 or b"")
    (OUTPUT_DIR / "device_key.pem").chmod(0o600)
    _info(f"Saved cert/key/chain to {OUTPUT_DIR}")

    _section("Summary")
    _ok("Renew workflow (quick) passed. Use --wait-renew to test after 5m expiry.")
    return True


def run_wait_and_renew_test() -> bool:
    """Enroll, wait 5m10s, then renew and verify new cert is valid."""
    _section("1. First enrollment (5-min short-lived cert)")
    OUTPUT_DIR.mkdir(exist_ok=True)
    key_pem, csr_pem = generate_csr_and_key_pem(REGISTRATION_ID)
    cert_pem_1, chain_pem = enroll_certificate_via_est(
        EST_SERVER_URL, BOOTSTRAP_TOKEN, csr_pem, verify_ssl=False
    )
    cn, not_after = get_cert_cn_and_expiry(cert_pem_1)
    _ok(f"Certificate issued for CN={cn}, expires {not_after}")
    if not verify_certificate(cert_pem_1, chain_pem or None):
        _err("First cert failed verification")
        return False
    _ok("First cert valid (will expire in ~5 minutes)")

    _section("2. Wait 5 minutes 10 seconds (cert will expire)")
    wait_sec = 5 * 60 + 10
    _info(f"Waiting {wait_sec}s...")
    time.sleep(wait_sec)

    # Verify first cert is now expired
    if verify_certificate(cert_pem_1, chain_pem or None):
        _err("First cert should be expired now")
        return False
    _ok("First cert is expired as expected")

    _section("3. Renew (re-enroll) after expiry")
    key_pem_2, csr_pem_2 = generate_csr_and_key_pem(REGISTRATION_ID)
    cert_pem_2, chain_pem_2 = enroll_certificate_via_est(
        EST_SERVER_URL, BOOTSTRAP_TOKEN, csr_pem_2, verify_ssl=False
    )
    cn2, not_after_2 = get_cert_cn_and_expiry(cert_pem_2)
    _ok(f"New cert for CN={cn2}, expires {not_after_2}")
    if not verify_certificate(cert_pem_2, chain_pem_2 or None):
        _err("Renewed cert failed verification")
        return False
    _ok("Renewed cert is valid — device can reconnect to Azure with this cert")

    (OUTPUT_DIR / "device_cert.pem").write_bytes(cert_pem_2)
    (OUTPUT_DIR / "device_key.pem").write_bytes(key_pem_2)
    (OUTPUT_DIR / "device_chain.pem").write_bytes(chain_pem_2 or b"")
    (OUTPUT_DIR / "device_key.pem").chmod(0o600)
    _info(f"Saved new cert/key to {OUTPUT_DIR}")

    _section("Summary")
    _ok("Renew-after-expiry test passed. Use these certs to connect to Azure and send data.")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Test 5-min cert and renew workflow")
    parser.add_argument(
        "--wait-renew",
        action="store_true",
        help="Wait 5m10s after first enroll then renew (tests after expiry)",
    )
    args = parser.parse_args()
    try:
        if args.wait_renew:
            ok = run_wait_and_renew_test()
        else:
            ok = run_quick_renew_test()
        return 0 if ok else 1
    except Exception as e:
        _err(str(e))
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
