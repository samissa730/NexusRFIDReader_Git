#!/usr/bin/env python3
"""
Azure IoT Configuration Diagnostic Tool
Tests each credential and configuration step to identify issues
"""

import json
import sys
import socket
import time
from pathlib import Path

try:
    from azure.iot.device import (
        IoTHubDeviceClient,
        ProvisioningDeviceClient
    )
    from azure.iot.device.exceptions import (
        ConnectionDroppedError,
        ConnectionFailedError,
        CredentialError,
        ServiceError
    )
except ImportError:
    print("ERROR: Azure IoT SDK not installed")
    print(
        "Install with: sudo python3 -m pip install azure-iot-device "
        "--break-system-packages --ignore-installed"
    )
    sys.exit(1)

CONFIG_PATH = Path("/etc/azureiotpnp/provisioning_config.json")

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'

def print_success(msg):
    print(f"{Colors.GREEN}✓{Colors.END} {msg}")

def print_error(msg):
    print(f"{Colors.RED}✗{Colors.END} {msg}")

def print_warning(msg):
    print(f"{Colors.YELLOW}⚠{Colors.END} {msg}")

def print_info(msg):
    print(f"{Colors.BLUE}ℹ{Colors.END} {msg}")

def print_section(title):
    print(f"\n{Colors.BOLD}{'='*70}{Colors.END}")
    print(f"{Colors.BOLD}{title}{Colors.END}")
    print(f"{Colors.BOLD}{'='*70}{Colors.END}\n")

def test_config_file():
    """Test 1: Configuration file existence and format"""
    print_section("TEST 1: Configuration File")
    
    if not CONFIG_PATH.exists():
        print_error(f"Configuration file not found: {CONFIG_PATH}")
        print_info("Expected location: /etc/azureiotpnp/provisioning_config.json")
        print_info("Run device_setup.py first to create this file")
        return None
    
    print_success(f"Configuration file exists: {CONFIG_PATH}")
    
    # Check permissions
    import os
    stat_info = os.stat(CONFIG_PATH)
    perms = oct(stat_info.st_mode)[-3:]
    if perms == "600":
        print_success(f"File permissions correct: {perms}")
    else:
        print_warning(f"File permissions: {perms} (should be 600 for security)")
    
    # Validate JSON
    try:
        with open(CONFIG_PATH, 'r') as f:
            config = json.load(f)
        print_success("Configuration file has valid JSON format")
        return config
    except json.JSONDecodeError as e:
        print_error(f"Invalid JSON in configuration file: {e}")
        return None
    except Exception as e:
        print_error(f"Error reading configuration file: {e}")
        return None

def validate_required_fields(config):
    """Test 2: Validate required configuration fields"""
    print_section("TEST 2: Required Configuration Fields")
    
    required_fields = {
        "globalEndpoint": {
            "description": "DPS Global Endpoint",
            "expected_format": "global.azure-devices-provisioning.net",
            "azure_location": "Azure Portal → DPS → Overview → Global Endpoint"
        },
        "idScope": {
            "description": "DPS ID Scope",
            "expected_format": "0neXXXXXXXX (alphanumeric, typically 11 chars)",
            "azure_location": "Azure Portal → DPS → Overview → ID Scope"
        },
        "registrationId": {
            "description": "Device Registration ID",
            "expected_format": "Alphanumeric string (device serial number)",
            "azure_location": "Azure Portal → DPS → Manage enrollments → Individual enrollments"
        },
        "symmetricKey": {
            "description": "Device Symmetric Key",
            "expected_format": "Base64 encoded key (long string)",
            "azure_location": "Azure Portal → DPS → Manage enrollments → Individual enrollments → Primary Key"
        }
    }
    
    missing_fields = []
    invalid_fields = []
    
    for field, info in required_fields.items():
        if field not in config:
            print_error(f"Missing required field: {field}")
            print_info(f"  Description: {info['description']}")
            print_info(f"  Where to find: {info['azure_location']}")
            missing_fields.append(field)
        else:
            value = config[field]
            if not value or str(value).strip() == "":
                print_error(f"Empty value for field: {field}")
                invalid_fields.append(field)
            else:
                # Basic format validation
                if field == "globalEndpoint":
                    if "azure-devices-provisioning.net" not in str(value):
                        print_warning(f"globalEndpoint format may be incorrect: {value}")
                        print_info(f"  Expected format: {info['expected_format']}")
                elif field == "idScope":
                    if len(str(value)) < 10 or len(str(value)) > 15:
                        print_warning(f"idScope length unusual: {len(str(value))} chars")
                        print_info(f"  Expected format: {info['expected_format']}")
                elif field == "symmetricKey":
                    if len(str(value)) < 40:
                        print_warning(f"symmetricKey seems too short: {len(str(value))} chars")
                        print_info(f"  Expected format: {info['expected_format']}")
                
                print_success(f"{field}: Present and non-empty")
                # Show first/last few chars for verification (not full value)
                display_value = str(value)
                if len(display_value) > 20:
                    display_value = display_value[:10] + "..." + display_value[-10:]
                print_info(f"  Value preview: {display_value}")
    
    if missing_fields:
        print_error(f"\nMissing {len(missing_fields)} required field(s)")
        return False
    
    if invalid_fields:
        print_error(f"\nInvalid values in {len(invalid_fields)} field(s)")
        return False
    
    print_success("All required fields present and valid")
    return True

def test_network_connectivity():
    """Test 3: Network connectivity to Azure DPS"""
    print_section("TEST 3: Network Connectivity")
    
    test_hosts = [
        ("global.azure-devices-provisioning.net", 443, "Azure DPS"),
        ("iothub-dev-spotlight-rfid.azure-devices.net", 443, "Azure IoT Hub")
    ]
    
    all_ok = True
    for host, port, description in test_hosts:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((host, port))
            sock.close()
            
            if result == 0:
                print_success(f"{description} ({host}:{port}) - Reachable")
            else:
                print_error(f"{description} ({host}:{port}) - Not reachable (error code: {result})")
                all_ok = False
        except socket.gaierror as e:
            print_error(f"{description} ({host}) - DNS resolution failed: {e}")
            all_ok = False
        except Exception as e:
            print_error(f"{description} ({host}) - Connection test failed: {e}")
            all_ok = False
    
    return all_ok

def test_dps_provisioning(config):
    """Test 4: DPS Device Provisioning"""
    print_section("TEST 4: Device Provisioning Service (DPS) Connection")
    
    try:
        global_endpoint = config.get("globalEndpoint")
        id_scope = config.get("idScope")
        registration_id = config.get("registrationId")
        symmetric_key = config.get("symmetricKey")
        
        print_info(f"Testing DPS connection...")
        print_info(f"  Endpoint: {global_endpoint}")
        print_info(f"  ID Scope: {id_scope}")
        print_info(f"  Registration ID: {registration_id}")
        
        # Create provisioning client
        prov_client = ProvisioningDeviceClient.create_from_symmetric_key(
            provisioning_host=global_endpoint,
            registration_id=registration_id,
            id_scope=id_scope,
            symmetric_key=symmetric_key
        )
        
        print_info("Attempting device registration with DPS...")
        result = prov_client.register()
        
        if result.status == "assigned":
            assigned_hub = result.registration_state.assigned_hub
            device_id = result.registration_state.device_id
            print_success("Device successfully provisioned!")
            print_info(f"  Assigned IoT Hub: {assigned_hub}")
            print_info(f"  Device ID: {device_id}")
            
            # Verify device ID matches registration ID (usually they match)
            if device_id != registration_id:
                print_warning(f"Device ID ({device_id}) differs from Registration ID ({registration_id})")
                print_info("  This is normal if using custom allocation policy")
            
            return {
                "success": True,
                "assigned_hub": assigned_hub,
                "device_id": device_id
            }
        else:
            print_error(f"Provisioning failed with status: {result.status}")
            
            if result.status == "unassigned":
                print_error("Device registration exists but was not assigned to an IoT Hub")
                print_info("  Check Azure Portal → DPS → Manage enrollments")
                print_info("  Ensure device enrollment is active and linked to an IoT Hub")
            elif result.status == "failed":
                print_error("Provisioning request failed")
                print_info("  Possible causes:")
                print_info("    - Invalid symmetric key")
                print_info("    - Device not registered in DPS")
                print_info("    - DPS enrollment disabled or expired")
            elif result.status == "assigning":
                print_warning("Provisioning still in progress (assigning)")
                print_info("  This may indicate a slow network or DPS processing delay")
            
            return {"success": False, "status": result.status}
            
    except CredentialError as e:
        print_error(f"Credential error during provisioning: {e}")
        print_info("  Check your symmetric key in Azure Portal")
        print_info("  Azure Portal → DPS → Manage enrollments → [Your device] → Primary Key")
        return {"success": False, "error": "credential_error"}
    except ConnectionFailedError as e:
        print_error(f"Connection failed: {e}")
        print_info("  Check network connectivity and firewall settings")
        return {"success": False, "error": "connection_failed"}
    except Exception as e:
        print_error(f"Unexpected error during provisioning: {e}")
        import traceback
        print_info("  Full error details:")
        traceback.print_exc()
        return {"success": False, "error": str(e)}

def test_iot_hub_connection(config, provisioning_result):
    """Test 5: IoT Hub Connection"""
    print_section("TEST 5: IoT Hub Connection")
    
    if not provisioning_result.get("success"):
        print_error("Cannot test IoT Hub connection - DPS provisioning failed")
        return False
    
    try:
        assigned_hub = provisioning_result["assigned_hub"]
        device_id = provisioning_result["device_id"]
        symmetric_key = config.get("symmetricKey")
        
        print_info(f"Connecting to IoT Hub: {assigned_hub}")
        print_info(f"  Device ID: {device_id}")
        
        # Create IoT Hub client
        client = IoTHubDeviceClient.create_from_symmetric_key(
            symmetric_key=symmetric_key,
            hostname=assigned_hub,
            device_id=device_id
        )
        
        # Test connection without callbacks to avoid handler errors
        print_info("Attempting connection...")
        client.connect()
        print_success("Successfully connected to IoT Hub!")
        
        # Test sending a message
        test_message = json.dumps({
            "event": "diagnostic_test",
            "timestamp": int(time.time()),
            "test": True
        })
        
        print_info("Testing message send...")
        client.send_message(test_message)
        print_success("Successfully sent test message to IoT Hub!")
        
        # Disconnect
        client.disconnect()
        print_success("Disconnected from IoT Hub")
        
        return True
        
    except CredentialError as e:
        print_error(f"Credential error: {e}")
        print_info("  The symmetric key may be incorrect")
        print_info("  Verify in Azure Portal → DPS → Manage enrollments → [Your device]")
        return False
    except ConnectionFailedError as e:
        print_error(f"Connection failed: {e}")
        print_info("  Possible causes:")
        print_info("    - IoT Hub may be disabled or deleted")
        print_info("    - Device may not have proper permissions")
        print_info("    - Network/firewall blocking connection")
        return False
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False

def provide_azure_portal_instructions():
    """Provide detailed instructions for finding credentials in Azure Portal"""
    print_section("HOW TO FIND CREDENTIALS IN AZURE PORTAL")
    
    instructions = [
        {
            "field": "ID Scope",
            "steps": [
                "1. Go to Azure Portal (portal.azure.com)",
                "2. Navigate to your Device Provisioning Service (DPS)",
                "3. Click on 'Overview' in the left menu",
                "4. Find 'ID Scope' field - copy this value",
                "5. Format: Usually starts with '0ne' followed by alphanumeric characters"
            ]
        },
        {
            "field": "Group Key / Symmetric Key",
            "steps": [
                "1. In your DPS, click 'Manage enrollments' in the left menu",
                "2. Click on 'Individual enrollments' tab",
                "3. Find your device registration (by Registration ID)",
                "4. Click on the device to open details",
                "5. Under 'Authentication', find 'Primary Key' or 'Symmetric Key'",
                "6. Click the eye icon to reveal and copy the key",
                "7. Note: This is a long base64-encoded string"
            ]
        },
        {
            "field": "Registration ID",
            "steps": [
                "1. In DPS → Manage enrollments → Individual enrollments",
                "2. Find your device in the list",
                "3. The 'Registration ID' column shows your device ID",
                "4. This should match your device serial number (e.g., 10000000fbd711b4)"
            ]
        },
        {
            "field": "Global Endpoint",
            "steps": [
                "1. In DPS → Overview",
                "2. Find 'Service Endpoint' or 'Global Endpoint'",
                "3. Usually: global.azure-devices-provisioning.net",
                "4. This is the same for all DPS instances"
            ]
        },
        {
            "field": "Verify Device Registration",
            "steps": [
                "1. DPS → Manage enrollments → Individual enrollments",
                "2. Check that your device shows 'Enabled' status",
                "3. Verify 'Allocation policy' is set correctly",
                "4. If using 'Static allocation', ensure IoT Hub is specified",
                "5. Check 'Reprovision policy' if device was previously registered"
            ]
        }
    ]
    
    for item in instructions:
        print(f"\n{Colors.BOLD}{item['field']}:{Colors.END}")
        for step in item['steps']:
            print(f"  {step}")

def main():
    print_section("Azure IoT Configuration Diagnostic Tool")
    print_info("This tool will test each credential and configuration step")
    print_info("Run with: sudo python3 utils_Test/diagnose_iot_config.py\n")
    
    # Test 1: Configuration file
    config = test_config_file()
    if not config:
        print_error("\nCannot continue - configuration file is missing or invalid")
        provide_azure_portal_instructions()
        sys.exit(1)
    
    # Test 2: Required fields
    if not validate_required_fields(config):
        print_error("\nCannot continue - required fields are missing or invalid")
        provide_azure_portal_instructions()
        sys.exit(1)
    
    # Test 3: Network connectivity
    if not test_network_connectivity():
        print_warning("\nNetwork connectivity issues detected")
        print_info("  Check firewall settings and internet connection")
        print_info("  Some tests may still work if connectivity improves")
    
    # Test 4: DPS Provisioning
    provisioning_result = test_dps_provisioning(config)
    
    # Test 5: IoT Hub Connection (only if provisioning succeeded)
    if provisioning_result.get("success"):
        test_iot_hub_connection(config, provisioning_result)
    else:
        print_error("\nSkipping IoT Hub connection test - DPS provisioning failed")
        provide_azure_portal_instructions()
    
    # Summary
    print_section("DIAGNOSTIC SUMMARY")
    
    if provisioning_result.get("success"):
        print_success("Configuration appears to be correct!")
        print_info("If you're still seeing connection errors, they may be:")
        print_info("  - Temporary network issues")
        print_info("  - Azure IoT Hub throttling/limits")
        print_info("  - SDK background thread handling (non-critical)")
    else:
        print_error("Configuration issues detected")
        print_info("Review the errors above and verify credentials in Azure Portal")
        provide_azure_portal_instructions()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nDiagnostic interrupted by user")
        sys.exit(0)
    except Exception as e:
        print_error(f"\nFatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)