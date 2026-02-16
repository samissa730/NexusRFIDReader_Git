#!/usr/bin/env python3
"""
Test Bootstrap Device Enrollment and Certificate Issuance via EST.

This script specifically tests:
1. Bootstrap device enrollment (initial enrollment with bootstrap token)
2. Certificate issuance verification (certificate details, issuer, validity)
3. Multiple device enrollment (bootstrap works for multiple devices)
4. Certificate chain validation

Usage:
    python test_bootstrap_enrollment.py
"""

import sys
from pathlib import Path
from datetime import datetime, timezone

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

try:
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.backends import default_backend
    _CRYPTO_AVAILABLE = True
except ImportError:
    _CRYPTO_AVAILABLE = False

# Configuration - Use EST proxy (port 9443) when running docker-compose with est-proxy
EST_SERVER_URL = "https://127.0.0.1:9443/est"
BOOTSTRAP_TOKEN = "changeme"
OUTPUT_DIR = Path(__file__).parent / "est_test_output"


def print_section(title: str):
    """Print a formatted section header."""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_success(message: str):
    """Print a success message."""
    print(f"✓ {message}")


def print_error(message: str):
    """Print an error message."""
    print(f"✗ {message}")


def print_info(message: str):
    """Print an info message."""
    print(f"  {message}")


def verify_certificate_issuance(cert_pem: bytes, expected_cn: str, ca_cert_pem: bytes = None) -> dict:
    """
    Verify certificate issuance details.
    
    Returns:
        dict: Verification results with details
    """
    if not _CRYPTO_AVAILABLE:
        return {"valid": False, "error": "cryptography not available"}
    
    results = {
        "valid": True,
        "errors": [],
        "warnings": [],
        "details": {}
    }
    
    try:
        cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
        
        # Extract certificate details
        cn = None
        for attr in cert.subject:
            if attr.oid == NameOID.COMMON_NAME:
                cn = attr.value
                break
        
        results["details"] = {
            "subject_cn": cn,
            "issuer": str(cert.issuer),
            "serial_number": str(cert.serial_number),
            "not_valid_before": cert.not_valid_before_utc,
            "not_valid_after": cert.not_valid_after_utc,
            "signature_algorithm": cert.signature_algorithm_oid._name if hasattr(cert.signature_algorithm_oid, '_name') else str(cert.signature_algorithm_oid),
        }
        
        # Verify CN matches expected
        if cn != expected_cn:
            results["valid"] = False
            results["errors"].append(f"CN mismatch: expected '{expected_cn}', got '{cn}'")
        
        # Verify certificate validity period
        now = datetime.now(timezone.utc)
        if cert.not_valid_after_utc < now:
            results["valid"] = False
            results["errors"].append(f"Certificate expired: {cert.not_valid_after_utc}")
        elif cert.not_valid_before_utc > now:
            results["valid"] = False
            results["errors"].append(f"Certificate not yet valid: {cert.not_valid_before_utc}")
        
        # Verify certificate chain (if CA cert provided)
        if ca_cert_pem:
            try:
                ca_cert = x509.load_pem_x509_certificate(ca_cert_pem, default_backend())
                
                # Verify issuer matches CA subject
                if cert.issuer != ca_cert.subject:
                    results["valid"] = False
                    results["errors"].append(f"Issuer mismatch: cert issuer '{cert.issuer}' != CA subject '{ca_cert.subject}'")
                else:
                    results["details"]["issuer_verified"] = True
                
                # Verify certificate signature (basic check - issuer is CA)
                results["details"]["ca_issuer"] = str(ca_cert.subject)
                
            except Exception as e:
                results["warnings"].append(f"Could not verify against CA: {e}")
        
        # Check certificate validity period (should be reasonable)
        validity_days = (cert.not_valid_after_utc - cert.not_valid_before_utc).days
        if validity_days < 1:
            results["valid"] = False
            results["errors"].append(f"Certificate validity period too short: {validity_days} days")
        elif validity_days > 3650:  # 10 years
            results["warnings"].append(f"Certificate validity period very long: {validity_days} days")
        
        results["details"]["validity_days"] = validity_days
        
    except Exception as e:
        results["valid"] = False
        results["errors"].append(f"Certificate parsing error: {e}")
    
    return results


def test_bootstrap_device_enrollment(registration_id: str, device_num: int = 1) -> bool:
    """
    Test bootstrap enrollment for a single device.
    
    Args:
        registration_id: Device registration ID (will be CN in certificate)
        device_num: Device number for output organization
        
    Returns:
        bool: True if enrollment successful
    """
    print_section(f"Bootstrap Device Enrollment Test #{device_num}: {registration_id}")
    
    try:
        # Step 1: Generate CSR
        print_info(f"Generating CSR for device: {registration_id}")
        key_pem, csr_pem = generate_csr_and_key_pem(registration_id)
        print_success("CSR generated")
        
        # Step 2: Bootstrap enrollment via EST (using bootstrap token)
        print_info("Performing bootstrap enrollment with bootstrap token...")
        print_info(f"  EST Server: {EST_SERVER_URL}")
        print_info(f"  Bootstrap Token: {BOOTSTRAP_TOKEN[:10]}..." if len(BOOTSTRAP_TOKEN) > 10 else f"  Bootstrap Token: {BOOTSTRAP_TOKEN}")
        
        cert_pem, chain_pem = enroll_certificate_via_est(
            EST_SERVER_URL,
            BOOTSTRAP_TOKEN,  # Bootstrap token for initial enrollment
            csr_pem,
            verify_ssl=False
        )
        print_success("Certificate issued via bootstrap enrollment")
        
        # Step 3: Get CA certificates
        print_info("Fetching CA certificate chain...")
        ca_certs_pem = get_ca_certs(EST_SERVER_URL, BOOTSTRAP_TOKEN, verify_ssl=False)
        print_success("CA certificates retrieved")
        
        # Step 4: Verify certificate issuance
        print_info("Verifying certificate issuance...")
        issuance_results = verify_certificate_issuance(cert_pem, registration_id, ca_certs_pem)
        
        if issuance_results["valid"]:
            print_success("Certificate issuance verified")
            
            # Print certificate details
            details = issuance_results["details"]
            print_info(f"  Subject CN: {details.get('subject_cn')}")
            print_info(f"  Issuer: {details.get('issuer')}")
            print_info(f"  Serial Number: {details.get('serial_number')}")
            print_info(f"  Valid From: {details.get('not_valid_before')}")
            print_info(f"  Valid Until: {details.get('not_valid_after')}")
            print_info(f"  Validity Period: {details.get('validity_days')} days")
            
            if details.get("issuer_verified"):
                print_success("  Issuer verified against CA")
        else:
            print_error("Certificate issuance verification failed")
            for error in issuance_results["errors"]:
                print_error(f"  {error}")
            return False
        
        if issuance_results["warnings"]:
            for warning in issuance_results["warnings"]:
                print_info(f"  ⚠ Warning: {warning}")
        
        # Step 5: Verify certificate chain
        print_info("Verifying certificate chain...")
        chain_valid = verify_certificate(cert_pem, ca_certs_pem)
        if chain_valid:
            print_success("Certificate chain verified")
        else:
            print_error("Certificate chain verification failed")
            return False
        
        # Step 6: Save certificates
        device_dir = OUTPUT_DIR / f"device_{device_num}_{registration_id}"
        device_dir.mkdir(parents=True, exist_ok=True)
        
        (device_dir / "device_cert.pem").write_bytes(cert_pem)
        (device_dir / "device_key.pem").write_bytes(key_pem)
        (device_dir / "device_chain.pem").write_bytes(chain_pem)
        (device_dir / "ca_cert.pem").write_bytes(ca_certs_pem)
        (device_dir / "device.csr").write_bytes(csr_pem)
        
        (device_dir / "device_key.pem").chmod(0o600)
        print_success(f"Certificates saved to: {device_dir}")
        
        return True
        
    except Exception as e:
        print_error(f"Bootstrap enrollment failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_multiple_devices():
    """Test bootstrap enrollment for multiple devices."""
    print_section("Multiple Device Bootstrap Enrollment Test")
    
    devices = [
        "test-device-001",
        "test-device-002",
        "test-device-003"
    ]
    
    results = []
    for i, device_id in enumerate(devices, 1):
        success = test_bootstrap_device_enrollment(device_id, i)
        results.append((device_id, success))
    
    # Summary
    print_section("Multiple Device Test Summary")
    successful = sum(1 for _, success in results if success)
    total = len(results)
    
    print_info(f"Successfully enrolled: {successful}/{total} devices")
    for device_id, success in results:
        status = "✓" if success else "✗"
        print_info(f"  {status} {device_id}")
    
    return successful == total


def main():
    """Run bootstrap enrollment tests."""
    print_section("Bootstrap Device Enrollment & Certificate Issuance Test")
    
    if not _CRYPTO_AVAILABLE:
        print_error("cryptography library not available. Install with: pip install cryptography")
        return False
    
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    # Test 1: Single device bootstrap enrollment
    print("\n")
    success1 = test_bootstrap_device_enrollment("test-device-001", 1)
    
    if not success1:
        print_error("Single device test failed. Stopping.")
        return False
    
    # Test 2: Multiple devices bootstrap enrollment
    print("\n")
    success2 = test_multiple_devices()
    
    # Final summary
    print_section("Test Summary")
    if success1 and success2:
        print_success("All bootstrap enrollment tests passed!")
        print_info("\nTest Results:")
        print_info("  ✓ Bootstrap device enrollment works")
        print_info("  ✓ Certificate issuance verified")
        print_info("  ✓ Multiple device enrollment works")
        print_info("\nCertificates saved in: " + str(OUTPUT_DIR))
        return True
    else:
        print_error("Some tests failed")
        return False


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
