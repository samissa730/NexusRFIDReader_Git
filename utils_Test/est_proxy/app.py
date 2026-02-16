#!/usr/bin/env python3
"""
EST (RFC 7030) proxy that uses step-ca as the backend CA.
Exposes /est/simpleenroll and /est/cacerts; forwards signing to step-ca via step CLI.
"""
import os
import subprocess
import tempfile
from pathlib import Path

from flask import Flask, request, Response

try:
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.backends import default_backend
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False

app = Flask(__name__)

# From environment
BOOTSTRAP_TOKEN = os.environ.get("EST_BOOTSTRAP_TOKEN", "changeme")
STEP_CA_URL = os.environ.get("STEP_CA_URL", "https://step-ca:8443")
STEP_PASSWORD_FILE = os.environ.get("STEP_CA_PASSWORD_FILE", "/home/step/secrets/password")
STEP_ROOT_CERT = os.environ.get("STEP_CA_ROOT_CERT", "/home/step/certs/root_ca.crt")
STEP_PROVISIONER = os.environ.get("STEP_CA_PROVISIONER", "admin")


def _get_cn_from_csr(csr_der: bytes) -> str:
    """Extract Common Name from CSR (DER or PEM)."""
    if not CRYPTO_AVAILABLE:
        raise RuntimeError("cryptography required")
    try:
        cert = x509.load_der_x509_csr(csr_der, default_backend())
    except Exception:
        cert = x509.load_pem_x509_csr(csr_der, default_backend())
    for attr in cert.subject:
        if attr.oid == NameOID.COMMON_NAME:
            return attr.value
    raise ValueError("No CN in CSR")


def _csr_to_pem(csr_bytes: bytes) -> bytes:
    """Normalize CSR to PEM."""
    if not CRYPTO_AVAILABLE:
        return csr_bytes
    if b"-----BEGIN" in csr_bytes:
        return csr_bytes
    csr = x509.load_der_x509_csr(csr_bytes, default_backend())
    return csr.public_bytes(serialization.Encoding.PEM)


@app.route("/est/simpleenroll", methods=["POST"])
def simpleenroll():
    """EST simpleenroll: accept CSR, get token from step-ca, sign, return cert (DER)."""
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        return Response("Unauthorized", status=401)
    token = auth[7:].strip()
    if token != BOOTSTRAP_TOKEN:
        return Response("Forbidden", status=403)

    if not request.data:
        return Response("Missing CSR body", status=400)

    csr_bytes = request.data
    try:
        cn = _get_cn_from_csr(csr_bytes)
    except Exception as e:
        return Response(f"Invalid CSR: {e}", status=400)

    csr_pem = _csr_to_pem(csr_bytes)
    root = STEP_ROOT_CERT
    if not Path(root).exists():
        root = "/home/step/certs/root_ca.crt"
    ca_url = STEP_CA_URL
    pw_file = STEP_PASSWORD_FILE

    with tempfile.TemporaryDirectory() as tmp:
        csr_path = Path(tmp) / "req.pem"
        crt_path = Path(tmp) / "cert.pem"
        csr_path.write_bytes(csr_pem)

        # Get one-time token from step-ca
        try:
            result = subprocess.run(
                [
                    "step", "ca", "token", cn,
                    "--password-file", pw_file,
                    "--ca-url", ca_url,
                    "--root", root,
                    "--provisioner", STEP_PROVISIONER,
                    "--insecure",
                ],
                capture_output=True,
                text=True,
                timeout=30,
                cwd="/home/step",
            )
            if result.returncode != 0:
                app.logger.warning("step ca token stderr: %s", result.stderr)
                return Response(f"Token failed: {result.stderr}", status=502)
            ott = result.stdout.strip()
        except Exception as e:
            app.logger.exception("step ca token")
            return Response(str(e), status=502)

        # Sign CSR with step-ca
        try:
            result = subprocess.run(
                [
                    "step", "ca", "sign", str(csr_path), str(crt_path),
                    "--token", ott,
                    "--ca-url", ca_url,
                    "--root", root,
                    "--insecure",
                ],
                capture_output=True,
                text=True,
                timeout=30,
                cwd="/home/step",
            )
            if result.returncode != 0:
                app.logger.warning("step ca sign stderr: %s", result.stderr)
                return Response(f"Sign failed: {result.stderr}", status=502)
        except Exception as e:
            app.logger.exception("step ca sign")
            return Response(str(e), status=502)

        cert_pem = crt_path.read_bytes()
        cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
        cert_der = cert.public_bytes(serialization.Encoding.DER)

    return Response(cert_der, mimetype="application/pkcs7-mime; smime-type=certs-only")


def _load_first_pem_cert(pem_bytes: bytes):
    """Load first certificate from PEM (single or chain)."""
    cert = x509.load_pem_x509_certificate(pem_bytes, default_backend())
    return cert


@app.route("/est/cacerts", methods=["GET"])
def cacerts():
    """EST cacerts: return CA chain (intermediate) as DER."""
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        return Response("Unauthorized", status=401)
    if auth[7:].strip() != BOOTSTRAP_TOKEN:
        return Response("Forbidden", status=403)

    intermediate = Path("/home/step/certs/intermediate_ca.crt")
    if not intermediate.exists():
        return Response("CA certs not found", status=500)
    pem = intermediate.read_bytes()
    cert = _load_first_pem_cert(pem)
    cert_der = cert.public_bytes(serialization.Encoding.DER)
    return Response(
        cert_der,
        mimetype="application/pkcs7-mime; smime-type=certs-only",
    )


@app.route("/health", methods=["GET"])
def health():
    return Response('{"status":"ok"}', mimetype="application/json")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9443, debug=os.environ.get("FLASK_DEBUG", "0") == "1")
