#!/usr/bin/env python3
"""
Test DPS registration and IoT Hub connection using certificates from test_est_enrollment.

Uses device_cert.pem and device_key.pem from est_test_output/ (produced by test_est_enrollment.py).
Registration ID is taken from the certificate CN (e.g. test-device-001).

Requires:
  - Azure DPS with an X.509 enrollment for the device (registration_id = cert CN)
  - The CA that signed the device cert (e.g. Nexus IoT CA intermediate) registered in DPS
  - Config with idScope and globalEndpoint (see CONFIG paths below)

Config: id_scope and global_endpoint are read from (first found):
  - utils_Test/provisioning_config_x509.json  {"idScope": "...", "globalEndpoint": "..."}
  - utils_Test/provisioning_config.json       (if it has idScope/globalEndpoint and certPath/keyPath)
  - Environment: DPS_ID_SCOPE, DPS_GLOBAL_ENDPOINT

Usage:
  python test_x509_dps_iot_hub.py

Skip this test (e.g. in CI): set SKIP_X509_DPS_TEST=1
"""

import json
import os
import sys
import time
from pathlib import Path

# Same paths as test_est_enrollment output
_SCRIPT_DIR = Path(__file__).resolve().parent
EST_TEST_OUTPUT_DIR = _SCRIPT_DIR / "est_test_output"
EST_OUTPUT_CERT = EST_TEST_OUTPUT_DIR / "device_cert.pem"
EST_OUTPUT_KEY = EST_TEST_OUTPUT_DIR / "device_key.pem"

CONFIG_PATHS = [
    _SCRIPT_DIR / "provisioning_config_x509.json",
    _SCRIPT_DIR / "provisioning_config.json",
    Path("/etc/azureiotpnp/provisioning_config.json"),
]


def _print_section(title: str):
    print("\n" + "=" * 64)
    print(f"  {title}")
    print("=" * 64)


def _print_ok(msg: str):
    print(f"  [OK] {msg}")


def _print_fail(msg: str):
    print(f"  [FAIL] {msg}")


def _print_info(msg: str):
    print(f"  {msg}")


def _load_dps_config():
    """Load id_scope and global_endpoint from config file or env."""
    for path in CONFIG_PATHS:
        if path.is_file():
            try:
                data = json.loads(path.read_text())
                id_scope = data.get("idScope") or os.environ.get("DPS_ID_SCOPE")
                global_endpoint = data.get("globalEndpoint") or os.environ.get("DPS_GLOBAL_ENDPOINT")
                if id_scope and global_endpoint:
                    return {"idScope": id_scope, "globalEndpoint": global_endpoint, "_path": str(path)}
            except Exception:
                continue
    id_scope = os.environ.get("DPS_ID_SCOPE")
    global_endpoint = os.environ.get("DPS_GLOBAL_ENDPOINT")
    if id_scope and global_endpoint:
        return {"idScope": id_scope, "globalEndpoint": global_endpoint, "_path": "environment"}
    return None


def _get_registration_id_from_cert():
    """Read certificate CN from est_test_output device_cert.pem (registration_id)."""
    if not EST_OUTPUT_CERT.is_file():
        return None
    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.backends import default_backend
        cert = x509.load_pem_x509_certificate(EST_OUTPUT_CERT.read_bytes(), default_backend())
        for attr in cert.subject:
            if attr.oid == NameOID.COMMON_NAME:
                return attr.value
    except Exception:
        pass
    return None


def _run_x509_dps_and_iot_hub():
    if os.environ.get("SKIP_X509_DPS_TEST"):
        _print_section("X.509 DPS / IoT Hub test (skipped)")
        _print_info("SKIP_X509_DPS_TEST is set. Exiting.")
        return True

    if not EST_OUTPUT_CERT.is_file() or not EST_OUTPUT_KEY.is_file():
        _print_section("X.509 DPS / IoT Hub test (skipped)")
        _print_fail("EST enrollment output not found.")
        _print_info("Run test_est_enrollment.py first to generate device_cert.pem and device_key.pem in est_test_output/")
        return False

    config = _load_dps_config()
    if not config:
        _print_section("X.509 DPS / IoT Hub test (skipped)")
        _print_fail("No DPS config found.")
        _print_info("Create provisioning_config_x509.json with idScope and globalEndpoint, or set DPS_ID_SCOPE and DPS_GLOBAL_ENDPOINT.")
        return False

    try:
        from azure.iot.device import IoTHubDeviceClient, ProvisioningDeviceClient, X509
    except ImportError:
        _print_section("X.509 DPS / IoT Hub test (skipped)")
        _print_fail("Azure IoT SDK not installed.")
        _print_info("Install with: pip install azure-iot-device")
        return False

    registration_id = _get_registration_id_from_cert()
    if not registration_id:
        _print_fail("Could not read registration_id (CN) from device certificate.")
        return False

    id_scope = config["idScope"]
    global_endpoint = config["globalEndpoint"]

    _print_section("1. Using certificates from test_est_enrollment")
    _print_info(f"  Device certificate: {EST_OUTPUT_CERT}")
    _print_info(f"  Device private key:  {EST_OUTPUT_KEY}")
    _print_info(f"  Registration ID (from cert CN): {registration_id}")
    _print_info(f"  DPS config source: {config.get('_path', 'unknown')}")
    _print_ok("Certificates and config loaded.")

    _print_section("2. DPS registration (X.509)")
    _print_info(f"  Global endpoint: {global_endpoint}")
    _print_info(f"  ID Scope: {id_scope}")
    try:
        x509 = X509(cert_file=str(EST_OUTPUT_CERT), key_file=str(EST_OUTPUT_KEY))
        prov_client = ProvisioningDeviceClient.create_from_x509_certificate(
            provisioning_host=global_endpoint,
            registration_id=registration_id,
            id_scope=id_scope,
            x509=x509,
        )
        _print_info("  Registering with DPS...")
        result = prov_client.register()
        if result.status != "assigned":
            _print_fail(f"DPS registration status: {result.status}")
            _print_info("  Ensure DPS has an X.509 enrollment for this registration_id and the CA that signed the device cert.")
            return False
        assigned_hub = result.registration_state.assigned_hub
        device_id = result.registration_state.device_id
        _print_ok(f"Provisioned. IoT Hub: {assigned_hub}, Device ID: {device_id}")
    except Exception as e:
        _print_fail(f"DPS registration failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    _print_section("3. IoT Hub connection (X.509)")
    try:
        client = IoTHubDeviceClient.create_from_x509_certificate(
            hostname=assigned_hub,
            device_id=device_id,
            x509=x509,
        )
        _print_info("  Connecting...")
        client.connect()
        _print_ok("Connected to IoT Hub.")
    except Exception as e:
        _print_fail(f"IoT Hub connection failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    _print_section("4. Sending scan data every 5 seconds (Ctrl+C to stop)")
    _print_info("  Press Ctrl+C to stop and disconnect.")
    send_interval_sec = 5
    count = 0
    try:
        while True:
            count += 1
            ts = int(time.time())
            # Scan data format (same shape as test_iot_service / production scan records)
            test_tag = f"E20034120B1B0170{ts % 100000000:08d}"
            scan_message = {
                "type": "scan_batch",
                "scans": [
                    {
                        "siteId": "019a9e1e-81ff-75ab-99fc-4115bb92fec6",
                        "tagName": test_tag,
                        "latitude": 37.7749 + (hash(test_tag) % 100) * 0.0001,
                        "longitude": -122.4194 + (hash(test_tag) % 100) * 0.0001,
                        "speed": 15.0,
                        "deviceId": device_id,
                        "registrationId": registration_id,
                        "antenna": "1",
                        "barrier": 270.0,
                        "comment": None,
                        "sequence": count,
                        "timestamp": ts,
                        "source": "test_x509_dps_iot_hub",
                    }
                ],
            }
            client.send_message(json.dumps(scan_message))
            _print_ok(f"Scan #{count} (tag {test_tag[:20]}...) sent at {time.strftime('%H:%M:%S')}. Next in {send_interval_sec}s...")
            time.sleep(send_interval_sec)
    except KeyboardInterrupt:
        print("\n")
        _print_info("User stopped. Disconnecting...")
    except Exception as e:
        _print_fail(f"Send message failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        try:
            client.disconnect()
            _print_ok("Disconnected from IoT Hub.")
        except Exception:
            pass

    _print_section("VERIFICATION SUMMARY")
    _print_ok("DPS registration (X.509) using EST enrollment certificates: PASSED")
    _print_ok("IoT Hub connection (X.509): PASSED")
    _print_ok(f"Sending scan data to IoT Hub: {count} scan(s) sent. Stopped by user.")
    print("=" * 64 + "\n")
    return True


if __name__ == "__main__":
    success = _run_x509_dps_and_iot_hub()
    sys.exit(0 if success else 1)
