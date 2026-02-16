#!/usr/bin/env python3
"""
EST Client for X.509 certificate enrollment via step-ca EST server.

This module provides functions to enroll certificates using the EST (Enrollment over Secure Transport) protocol.
Used for testing X.509 certificate enrollment before integrating with Azure IoT Hub.
"""

import requests
import urllib3
from pathlib import Path
from typing import Optional, Tuple

# Disable SSL warnings for local testing (use proper CA cert in production)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

try:
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.backends import default_backend
    _CRYPTO_AVAILABLE = True
except ImportError:
    _CRYPTO_AVAILABLE = False


def enroll_certificate_via_est(
    est_server_url: str,
    bootstrap_token: str,
    csr_pem: bytes,
    ca_cert_path: Optional[Path] = None,
    verify_ssl: bool = False
) -> Tuple[bytes, bytes]:
    """
    Enroll certificate via EST simpleenroll endpoint.
    
    Args:
        est_server_url: EST server URL (e.g., "https://localhost:8443/est")
        bootstrap_token: Bootstrap token for authentication
        csr_pem: Certificate signing request in PEM format
        ca_cert_path: Optional path to CA certificate for verification
        verify_ssl: Whether to verify SSL certificate (False for local testing)
        
    Returns:
        tuple: (certificate_pem, certificate_chain_pem)
        
    Raises:
        RuntimeError: If cryptography is not available
        requests.RequestException: If EST enrollment fails
    """
    if not _CRYPTO_AVAILABLE:
        raise RuntimeError("cryptography is required for EST enrollment")
    
    url = f"{est_server_url.rstrip('/')}/simpleenroll"
    
    headers = {
        "Content-Type": "application/pkcs10",
        "Authorization": f"Bearer {bootstrap_token}"
    }
    
    # Use CA cert for verification if provided, otherwise use verify_ssl flag
    verify = str(ca_cert_path) if ca_cert_path else verify_ssl
    
    try:
        response = requests.post(
            url,
            data=csr_pem,
            headers=headers,
            verify=verify,
            timeout=45
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        msg = str(e)
        if hasattr(e, "response") and e.response is not None and e.response.text:
            msg += f" | Server: {e.response.text.strip()}"
        raise RuntimeError(f"EST enrollment failed: {msg}") from e
    
    # EST returns DER format, convert to PEM
    cert_der = response.content
    cert = x509.load_der_x509_certificate(cert_der, default_backend())
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    
    # Get CA chain via cacerts endpoint
    try:
        chain_pem = get_ca_certs(est_server_url, bootstrap_token, ca_cert_path, verify_ssl)
    except Exception as e:
        # If chain fetch fails, return empty chain
        chain_pem = b""
    
    return cert_pem, chain_pem


def get_ca_certs(
    est_server_url: str,
    bootstrap_token: str,
    ca_cert_path: Optional[Path] = None,
    verify_ssl: bool = False
) -> bytes:
    """
    Get CA certificates chain from EST server via cacerts endpoint.
    
    Args:
        est_server_url: EST server URL
        bootstrap_token: Bootstrap token for authentication
        ca_cert_path: Optional path to CA certificate for verification
        verify_ssl: Whether to verify SSL certificate
        
    Returns:
        bytes: CA certificates chain in PEM format
    """
    url = f"{est_server_url.rstrip('/')}/cacerts"
    
    headers = {
        "Authorization": f"Bearer {bootstrap_token}"
    }
    
    verify = str(ca_cert_path) if ca_cert_path else verify_ssl
    
    try:
        response = requests.get(url, headers=headers, verify=verify, timeout=30)
        response.raise_for_status()
        
        # EST returns DER format, convert to PEM
        ca_certs_der = response.content
        # Parse and convert each certificate in the chain
        certs_pem = b""
        # Try to parse as single DER cert first (most common)
        try:
            cert = x509.load_der_x509_certificate(ca_certs_der, default_backend())
            certs_pem = cert.public_bytes(serialization.Encoding.PEM)
        except Exception:
            # If single cert parsing fails, try to parse as PKCS#7 bundle
            # Note: cryptography doesn't have built-in PKCS#7 support
            # For step-ca, cacerts typically returns a single cert or PEM bundle
            # Return raw content and let caller handle it
            certs_pem = ca_certs_der
        
        return certs_pem
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Failed to fetch CA certificates: {e}") from e


def verify_certificate(cert_pem: bytes, ca_cert_pem: Optional[bytes] = None) -> bool:
    """
    Verify that a certificate is valid and optionally verify against CA.
    
    Args:
        cert_pem: Certificate in PEM format
        ca_cert_pem: Optional CA certificate in PEM format for verification
        
    Returns:
        bool: True if certificate is valid
    """
    if not _CRYPTO_AVAILABLE:
        return False
    
    try:
        cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
        
        # Basic validation: check expiry (cert times are naive UTC from cryptography)
        from datetime import datetime, timezone
        now_utc_naive = datetime.now(timezone.utc).replace(tzinfo=None)
        if cert.not_valid_after < now_utc_naive or cert.not_valid_before > now_utc_naive:
            return False
        
        # If CA cert provided, verify chain
        if ca_cert_pem:
            ca_cert = x509.load_pem_x509_certificate(ca_cert_pem, default_backend())
            # Basic check: issuer matches CA subject
            if cert.issuer != ca_cert.subject:
                return False
        
        return True
    except Exception:
        return False
