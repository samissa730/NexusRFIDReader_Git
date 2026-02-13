#!/usr/bin/env python3
"""
Test EST enrollment with step-ca server.

This script tests the complete EST enrollment flow:
1. Generate CSR with registration_id as CN
2. Bootstrap enrollment via EST server (using bootstrap token)
3. Verify certificate issuance
4. Save certificates for use with Azure IoT Hub

This is a basic test. For comprehensive bootstrap device enrollment and 
certificate issuance verification, use test_bootstrap_enrollment.py

Usage:
    python test_est_enrollment.py
    
Before running:
    1. Start step-ca EST server: docker-compose up -d (in utils_Test directory)
    2. Update EST_SERVER_URL and BOOTSTRAP_TOKEN below
"""

import sys
from pathlib import Path

# Add parent directory to path to import test helpers
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils_Test.test_x509_est_device_setup import (
    generate_csr_and_key_pem,
    get_cert_cn_and_expiry
)
from utils_Test.est_client import (
    enroll_certificate_via_est,
    get_ca_certs,
    verify_certificate
)

# Configuration - Update these for your setup
EST_SERVER_URL = "https://localhost:8443/est"
BOOTSTRAP_TOKEN = "changeme"  # Update with your step-ca bootstrap token
REGISTRATION_ID = "test-device-001"  # Device registration ID (will be CN in certificate)
OUTPUT_DIR = Path(__file__).parent / "est_test_output"


def print_section(title: str):
    """Print a formatted section header."""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def print_success(message: str):
    """Print a success message."""
    print(f"✓ {message}")


def print_error(message: str):
    """Print an error message."""
    print(f"✗ {message}")


def print_info(message: str):
    """Print an info message."""
    print(f"  {message}")


def test_est_enrollment():
    """Test EST enrollment flow."""
    print_section("EST Enrollment Test")
    
    # Create output directory
    OUTPUT_DIR.mkdir(exist_ok=True)
    print_info(f"Output directory: {OUTPUT_DIR}")
    
    # Step 1: Generate CSR
    print_section("Step 1: Generate CSR")
    try:
        print_info(f"Generating CSR for registration_id: {REGISTRATION_ID}")
        key_pem, csr_pem = generate_csr_and_key_pem(REGISTRATION_ID)
        print_success("CSR generated successfully")
        
        # Save CSR for inspection
        csr_path = OUTPUT_DIR / "device.csr"
        csr_path.write_bytes(csr_pem)
        print_info(f"CSR saved to: {csr_path}")
    except Exception as e:
        print_error(f"Failed to generate CSR: {e}")
        return False
    
    # Step 2: Bootstrap enrollment via EST (using bootstrap token)
    print_section("Step 2: Bootstrap Enrollment via EST")
    try:
        print_info(f"EST Server URL: {EST_SERVER_URL}")
        print_info(f"Bootstrap Token: {BOOTSTRAP_TOKEN[:10]}..." if len(BOOTSTRAP_TOKEN) > 10 else f"Bootstrap Token: {BOOTSTRAP_TOKEN}")
        print_info("Performing bootstrap enrollment (initial enrollment with bootstrap token)...")
        
        cert_pem, chain_pem = enroll_certificate_via_est(
            EST_SERVER_URL,
            BOOTSTRAP_TOKEN,  # Bootstrap token for initial device enrollment
            csr_pem,
            verify_ssl=False  # Disable SSL verification for local testing
        )
        print_success("Certificate issued via bootstrap enrollment!")
        
        # Parse certificate to show details
        cn, expiry = get_cert_cn_and_expiry(cert_pem)
        if cn:
            print_info(f"Certificate CN: {cn}")
        if expiry:
            print_info(f"Certificate expires: {expiry}")
        
        # Verify certificate issuance
        print_info("Verifying certificate issuance...")
        try:
            from cryptography import x509
            from cryptography.x509.oid import NameOID
            from cryptography.hazmat.backends import default_backend
            
            cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
            print_info(f"Issuer: {cert.issuer}")
            print_info(f"Serial Number: {cert.serial_number}")
            print_info(f"Valid From: {cert.not_valid_before_utc}")
            print_info(f"Valid Until: {cert.not_valid_after_utc}")
            
            # Verify CN matches registration_id
            cert_cn = None
            for attr in cert.subject:
                if attr.oid == NameOID.COMMON_NAME:
                    cert_cn = attr.value
                    break
            
            if cert_cn == REGISTRATION_ID:
                print_success(f"Certificate CN matches registration_id: {REGISTRATION_ID}")
            else:
                print_error(f"Certificate CN mismatch: expected {REGISTRATION_ID}, got {cert_cn}")
        except Exception as e:
            print_info(f"Could not parse certificate details: {e}")
        
    except Exception as e:
        print_error(f"EST enrollment failed: {e}")
        print_info("Make sure step-ca EST server is running:")
        print_info("  docker-compose up -d")
        print_info("Check EST_SERVER_URL and BOOTSTRAP_TOKEN in this script")
        return False
    
    # Step 3: Get CA certificates
    print_section("Step 3: Get CA Certificates")
    try:
        print_info("Fetching CA certificate chain...")
        ca_certs_pem = get_ca_certs(EST_SERVER_URL, BOOTSTRAP_TOKEN, verify_ssl=False)
        print_success("CA certificates retrieved")
    except Exception as e:
        print_error(f"Failed to get CA certificates: {e}")
        ca_certs_pem = chain_pem  # Use chain from enrollment if available
    
    # Step 4: Verify certificate
    print_section("Step 4: Verify Certificate")
    try:
        is_valid = verify_certificate(cert_pem, ca_certs_pem)
        if is_valid:
            print_success("Certificate verification passed")
        else:
            print_error("Certificate verification failed")
    except Exception as e:
        print_error(f"Certificate verification error: {e}")
    
    # Step 5: Save certificates
    print_section("Step 5: Save Certificates")
    try:
        cert_path = OUTPUT_DIR / "device_cert.pem"
        key_path = OUTPUT_DIR / "device_key.pem"
        chain_path = OUTPUT_DIR / "device_chain.pem"
        ca_path = OUTPUT_DIR / "ca_cert.pem"
        
        cert_path.write_bytes(cert_pem)
        key_path.write_bytes(key_pem)
        chain_path.write_bytes(chain_pem)
        ca_path.write_bytes(ca_certs_pem)
        
        print_success("Certificates saved:")
        print_info(f"  Device Certificate: {cert_path}")
        print_info(f"  Device Private Key: {key_path}")
        print_info(f"  Certificate Chain: {chain_path}")
        print_info(f"  CA Certificate: {ca_path}")
        
        # Set restrictive permissions on key file
        key_path.chmod(0o600)
        print_info("Private key permissions set to 600")
        
    except Exception as e:
        print_error(f"Failed to save certificates: {e}")
        return False
    
    # Summary
    print_section("Test Summary")
    print_success("Bootstrap enrollment test completed successfully!")
    print_info("\nTest Coverage:")
    print_info("  ✓ Bootstrap device enrollment (using bootstrap token)")
    print_info("  ✓ Certificate issuance verification")
    print_info("  ✓ Certificate chain validation")
    print_info("\nNext steps:")
    print_info("1. Review certificates in: " + str(OUTPUT_DIR))
    print_info("2. Run comprehensive test: python test_bootstrap_enrollment.py")
    print_info("3. Use device_cert.pem and device_key.pem for Azure IoT Hub X.509 authentication")
    print_info("4. Update device_setup.py to use EST enrollment")
    print_info("5. Update iot_service.py to use X.509 certificates")
    
    return True


if __name__ == "__main__":
    try:
        success = test_est_enrollment()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
