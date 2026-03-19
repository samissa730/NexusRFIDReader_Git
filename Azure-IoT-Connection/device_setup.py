#!/usr/bin/env python3
"""
Device Setup Script for Nexus Locate IoT (X.509 only).
Enrolls device certificate via EST and writes provisioning config (certPath, keyPath).
"""

import json
import subprocess
import sys
from pathlib import Path
import os

# Ensure Azure-IoT-Connection directory is on path for est_client import
_script_dir = Path(__file__).resolve().parent
if str(_script_dir) not in sys.path:
    sys.path.insert(0, str(_script_dir))

CONFIG_PATH = Path("/etc/azureiotpnp/provisioning_config.json")
# X.509 cert/key stored next to config
DEFAULT_CERT_PATH = CONFIG_PATH.parent / "device_cert.pem"
DEFAULT_KEY_PATH = CONFIG_PATH.parent / "device_key.pem"


def load_env_json():
    """Load env.json from known paths (read-only, no prompts). Returns dict or {}."""
    script_dir = Path(__file__).parent
    candidates = [script_dir / "env.json", Path.cwd() / "env.json"]
    if os.getenv("NEXUS_PROJECT_DIR"):
        candidates.insert(0, Path(os.getenv("NEXUS_PROJECT_DIR")) / "env.json")
    for path in candidates:
        if path.exists():
            try:
                return json.loads(path.read_text()) or {}
            except Exception:
                pass
    return {}


def get_device_serial():
    """Get device serial number"""
    try:
        result = subprocess.run(['cat', '/proc/cpuinfo'], capture_output=True, text=True)
        for line in result.stdout.split('\n'):
            if line.startswith('Serial'):
                serial = line.split(':')[1].strip().lstrip('0')
                return serial if serial else "unknown"
    except:
        pass
    return "unknown"

def get_user_input():
    """Get configuration inputs for X.509 (EST enrollment)."""
    print("=" * 60)
    print("Nexus Locate IoT Device Setup (X.509 / EST)")
    print("=" * 60)

    serial = get_device_serial()
    print(f"\nDevice Serial Number: {serial}")

    env_config = load_env_json()

    id_scope = env_config.get('idScope') or input("Enter ID Scope: ").strip()
    if not id_scope:
        print("ID Scope is required.")
        return None

    est_server_url = (env_config.get('est_server_url') or "").strip() or input(
        "Enter EST Server URL (e.g. https://your-est:9443/est): "
    ).strip()
    est_bootstrap_token = (env_config.get('est_bootstrap_token') or "").strip() or input(
        "Enter EST Bootstrap Token: "
    ).strip()
    if not est_server_url or not est_bootstrap_token:
        print("EST server URL and bootstrap token are required for X.509 enrollment.")
        return None

    device_id = env_config.get('registrationId') or serial
    site_name = env_config.get('siteName') or "Lazer"
    truck_number = env_config.get('truckNumber') or serial

    return {
        'device_id': device_id,
        'id_scope': id_scope,
        'global_endpoint': env_config.get('globalEndpoint') or "global.azure-devices-provisioning.net",
        'est_server_url': est_server_url,
        'est_bootstrap_token': est_bootstrap_token,
        'site_name': site_name,
        'truck_number': truck_number,
        'serial': serial,
        'storage_account': env_config.get('storageAccount') or "",
        'container_name': env_config.get('containerName') or "",
        'sas_token': env_config.get('sas_token') or "",
    }


def save_configuration(inputs):
    """Enroll via EST, save cert/key, and write X.509 provisioning config (no symmetric key)."""
    try:
        from est_client import enroll_device
    except ImportError:
        print("Error: est_client module not found. Install cryptography and requests.")
        return False

    cert_path = Path(inputs.get('cert_path') or str(DEFAULT_CERT_PATH))
    key_path = Path(inputs.get('key_path') or str(DEFAULT_KEY_PATH))

    print("\nEnrolling device certificate via EST...")
    ok = enroll_device(
        registration_id=inputs['device_id'],
        est_server_url=inputs['est_server_url'],
        bootstrap_token=inputs['est_bootstrap_token'],
        cert_path=cert_path,
        key_path=key_path,
        chain_path=None,
        verify_ssl=False,
    )
    if not ok:
        print("EST enrollment failed. Check EST server URL and bootstrap token.")
        return False
    print("Certificate enrolled and saved.")

    config = {
        "globalEndpoint": inputs.get('global_endpoint') or "global.azure-devices-provisioning.net",
        "idScope": inputs['id_scope'],
        "registrationId": inputs['device_id'],
        "certPath": str(cert_path.resolve()),
        "keyPath": str(key_path.resolve()),
        "estServerUrl": inputs.get('est_server_url') or "",
        "estBootstrapToken": inputs.get('est_bootstrap_token') or "",
        "tags": {
            "nexusLocate": {
                "siteName": inputs['site_name'],
                "truckNumber": inputs['truck_number'],
                "deviceSerial": inputs['serial']
            }
        },
        "deviceUpdate": {
            "blobBasePath": "builds",
            "currentVersion": "20250826.1",
            "storageAccount": inputs.get('storage_account') or "",
            "containerName": inputs.get('container_name') or "",
            "sasToken": inputs.get('sas_token') or ""
        }
    }

    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(config, indent=2))
        subprocess.run(['chmod', '600', str(CONFIG_PATH)], check=False)
        return True
    except Exception as e:
        print(f"Error saving configuration: {e}")
        return False


def main():
    if CONFIG_PATH.exists():
        print("Device is already configured!")
        response = input("Do you want to reconfigure? (yes/no): ").strip().lower()
        if response not in ['yes', 'y']:
            print("Setup cancelled.")
            return

    inputs = get_user_input()
    if not inputs:
        print("Setup failed due to missing inputs.")
        return

    print("\n" + "=" * 60)
    print("Configuration Summary (X.509)")
    print("=" * 60)
    print(f"Device ID: {inputs['device_id']}")
    print(f"ID Scope: {inputs['id_scope']}")
    print(f"Site Name: {inputs['site_name']}")
    print(f"Truck Number: {inputs['truck_number']}")
    print(f"Device Serial: {inputs['serial']}")
    print("=" * 60)

    print("\nSaving configuration...")
    if save_configuration(inputs):
        print(f"\n✓ Configuration saved to {CONFIG_PATH}")
        print("✓ Device setup completed successfully!")
        print("\nNext steps:")
        print("1. In Azure DPS, create an X.509 enrollment for this device (registration_id = device ID) and register the CA that signed the device cert.")
        print("2. Install and start the IoT service")
        print("3. The device will connect to Azure IoT Hub using X.509")
    else:
        print("\n✗ Failed to save configuration")

if __name__ == "__main__":
    main()
