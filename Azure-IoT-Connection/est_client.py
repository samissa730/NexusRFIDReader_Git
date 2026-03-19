#!/usr/bin/env python3
"""
EST client for X.509 certificate enrollment (e.g. step-ca EST server).

Provides CSR generation, EST simpleenroll/cacerts, and cert verification.
Used by device_setup for X.509 provisioning and by tests in utils_Test.
"""

from pathlib import Path
from typing import Optional, Tuple

try:
    import requests
    import urllib3
    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False

if _REQUESTS_AVAILABLE:
    try:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    except Exception:
        pass

try:
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.backends import default_backend
    _CRYPTO_AVAILABLE = True
except ImportError:
    _CRYPTO_AVAILABLE = False


def generate_csr_and_key_pem(registration_id: str, key_size: int = 2048) -> Tuple[bytes, bytes]:
    """
    Generate a private key and CSR with CN = registration_id (for EST simpleenroll).
    Returns (private_key_pem, csr_pem). Requires cryptography.
    """
    if not _CRYPTO_AVAILABLE:
        raise RuntimeError("cryptography is required for CSR generation")
    key = rsa.generate_private_key(
        public_exponent=65537, key_size=key_size, backend=default_backend()
    )
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, registration_id)])
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(name)
        .sign(key, hashes.SHA256(), default_backend())
    )
    key_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    csr_pem = csr.public_bytes(serialization.Encoding.PEM)
    return key_pem, csr_pem


def get_cert_cn_and_expiry(cert_pem: bytes):
    """Parse PEM certificate and return (common_name, not_valid_after)."""
    if not _CRYPTO_AVAILABLE:
        return None, None
    cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
    cn = None
    for attr in cert.subject:
        if attr.oid == NameOID.COMMON_NAME:
            cn = attr.value
            break
    return cn, cert.not_valid_after


def enroll_certificate_via_est(
    est_server_url: str,
    bootstrap_token: str,
    csr_pem: bytes,
    ca_cert_path: Optional[Path] = None,
    verify_ssl: bool = False,
) -> Tuple[bytes, bytes]:
    """
    Enroll certificate via EST simpleenroll endpoint.

    Returns:
        (certificate_pem, certificate_chain_pem)
    """
    if not _REQUESTS_AVAILABLE:
        raise RuntimeError("requests is required for EST enrollment")
    if not _CRYPTO_AVAILABLE:
        raise RuntimeError("cryptography is required for EST enrollment")

    url = f"{est_server_url.rstrip('/')}/simpleenroll"
    headers = {
        "Content-Type": "application/pkcs10",
        "Authorization": f"Bearer {bootstrap_token}",
    }
    verify = str(ca_cert_path) if ca_cert_path else verify_ssl

    try:
        response = requests.post(
            url, data=csr_pem, headers=headers, verify=verify, timeout=45
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        msg = str(e)
        if hasattr(e, "response") and e.response is not None and getattr(e.response, "text", None):
            msg += f" | Server: {e.response.text.strip()}"
        raise RuntimeError(f"EST enrollment failed: {msg}") from e

    cert_der = response.content
    cert = x509.load_der_x509_certificate(cert_der, default_backend())
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)

    try:
        chain_pem = get_ca_certs(est_server_url, bootstrap_token, ca_cert_path, verify_ssl)
    except Exception:
        chain_pem = b""

    return cert_pem, chain_pem


def get_ca_certs(
    est_server_url: str,
    bootstrap_token: str,
    ca_cert_path: Optional[Path] = None,
    verify_ssl: bool = False,
) -> bytes:
    """Get CA certificates from EST cacerts endpoint. Returns PEM bytes."""
    if not _REQUESTS_AVAILABLE or not _CRYPTO_AVAILABLE:
        raise RuntimeError("requests and cryptography required")

    url = f"{est_server_url.rstrip('/')}/cacerts"
    headers = {"Authorization": f"Bearer {bootstrap_token}"}
    verify = str(ca_cert_path) if ca_cert_path else verify_ssl

    response = requests.get(url, headers=headers, verify=verify, timeout=30)
    response.raise_for_status()
    ca_certs_der = response.content
    try:
        cert = x509.load_der_x509_certificate(ca_certs_der, default_backend())
        return cert.public_bytes(serialization.Encoding.PEM)
    except Exception:
        return ca_certs_der


def verify_certificate(cert_pem: bytes, ca_cert_pem: Optional[bytes] = None) -> bool:
    """Verify certificate validity and optionally chain to CA."""
    if not _CRYPTO_AVAILABLE:
        return False
    try:
        from datetime import datetime, timezone
        cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        if cert.not_valid_after < now_utc or cert.not_valid_before > now_utc:
            return False
        if ca_cert_pem:
            ca_cert = x509.load_pem_x509_certificate(ca_cert_pem, default_backend())
            if cert.issuer != ca_cert.subject:
                return False
        return True
    except Exception:
        return False


def enroll_device(
    registration_id: str,
    est_server_url: str,
    bootstrap_token: str,
    cert_path: Path,
    key_path: Path,
    chain_path: Optional[Path] = None,
    ca_cert_path: Optional[Path] = None,
    verify_ssl: bool = False,
) -> bool:
    """
    One-shot: generate CSR, enroll via EST, verify, and save cert/key (and optional chain).
    Returns True on success.
    """
    key_pem, csr_pem = generate_csr_and_key_pem(registration_id)
    cert_pem, chain_pem = enroll_certificate_via_est(
        est_server_url, bootstrap_token, csr_pem, ca_cert_path, verify_ssl
    )
    if not verify_certificate(cert_pem, chain_pem or None):
        return False
    cert_path.parent.mkdir(parents=True, exist_ok=True)
    cert_path.write_bytes(cert_pem)
    key_path.write_bytes(key_pem)
    key_path.chmod(0o600)
    if chain_path is not None and chain_pem:
        chain_path.write_bytes(chain_pem)
    return True
