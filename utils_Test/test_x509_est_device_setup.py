"""
Tests for X.509 + EST device-side setup (Phase 4).

Covers:
- X.509 provisioning config structure (certPath, keyPath, registrationId, idScope; no symmetricKey).
- CSR generation for EST enrollment (registration_id as CN).
- Certificate loading and basic validation (subject CN, expiry).
- EST/bootstrap config parsing (est_server_url, est_bootstrap_token).

Does not require a live EST server or DPS. Uses unittest; cryptography is optional (tests skip if missing).
"""

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.backends import default_backend
    _CRYPTO_AVAILABLE = True
except ImportError:
    _CRYPTO_AVAILABLE = False


# --- Helpers used by device-side X.509/EST flow (tested here) ---

def build_x509_provisioning_config(
    registration_id: str,
    id_scope: str,
    cert_path: str,
    key_path: str,
    chain_path: str | None = None,
    global_endpoint: str = "global.azure-devices-provisioning.net",
    tags: dict | None = None,
    device_update: dict | None = None,
) -> dict:
    """Build provisioning config for X.509 (no symmetric key). Used by device_setup after EST enrollment."""
    config = {
        "globalEndpoint": global_endpoint,
        "idScope": id_scope,
        "registrationId": registration_id,
        "certPath": cert_path,
        "keyPath": key_path,
        "tags": tags or {},
        "deviceUpdate": device_update or {},
    }
    if chain_path is not None:
        config["chainPath"] = chain_path
    return config


def validate_x509_provisioning_config(config: dict) -> tuple[bool, str]:
    """
    Validate that config has required X.509 fields and no symmetric key for X.509-only mode.
    Returns (ok, message).
    """
    required = ("registrationId", "idScope", "certPath", "keyPath")
    for key in required:
        if not config.get(key):
            return False, f"Missing or empty required field: {key}"
    if config.get("symmetricKey"):
        return False, "X.509 config must not contain symmetricKey"
    return True, "OK"


def generate_csr_and_key_pem(registration_id: str, key_size: int = 2048) -> tuple[bytes, bytes]:
    """
    Generate a private key and CSR with CN = registration_id (for EST simpleenroll).
    Returns (private_key_pem, csr_pem). Requires cryptography.
    """
    if not _CRYPTO_AVAILABLE:
        raise RuntimeError("cryptography is required for CSR generation")
    key = rsa.generate_private_key(public_exponent=65537, key_size=key_size, backend=default_backend())
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


def get_cert_cn_and_expiry(cert_pem: bytes) -> tuple[str | None, datetime | None]:
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


def parse_est_env_config(env: dict) -> dict:
    """Extract EST-related keys from env.json-like config."""
    return {
        "est_server_url": (env.get("est_server_url") or "").strip() or None,
        "est_bootstrap_token": (env.get("est_bootstrap_token") or "").strip() or None,
    }


# Output directory from test_est_enrollment.py (device_cert.pem, device_key.pem, etc.)
EST_TEST_OUTPUT_DIR = Path(__file__).resolve().parent / "est_test_output"
EST_OUTPUT_CERT = EST_TEST_OUTPUT_DIR / "device_cert.pem"
EST_OUTPUT_KEY = EST_TEST_OUTPUT_DIR / "device_key.pem"
EST_OUTPUT_CHAIN = EST_TEST_OUTPUT_DIR / "device_chain.pem"
EST_OUTPUT_CA = EST_TEST_OUTPUT_DIR / "ca_cert.pem"


def _est_enrollment_output_available() -> bool:
    """True if test_est_enrollment.py has been run and produced device cert + key."""
    return EST_OUTPUT_CERT.is_file() and EST_OUTPUT_KEY.is_file()


# --- Unittest classes ---


class TestX509ProvisioningConfigStructure(unittest.TestCase):
    """Test X.509 provisioning config shape and validation."""

    def test_build_config_has_required_fields(self):
        config = build_x509_provisioning_config(
            registration_id="device-001",
            id_scope="0ne12345678",
            cert_path="/etc/nexuslocate/pki/device.crt",
            key_path="/etc/nexuslocate/pki/device.key",
            tags={"nexusLocate": {"siteName": "Lazer", "truckNumber": "001"}},
            device_update={"blobBasePath": "builds", "currentVersion": "20250826.1"},
        )
        self.assertEqual(config["registrationId"], "device-001")
        self.assertEqual(config["idScope"], "0ne12345678")
        self.assertEqual(config["certPath"], "/etc/nexuslocate/pki/device.crt")
        self.assertEqual(config["keyPath"], "/etc/nexuslocate/pki/device.key")
        self.assertNotIn("symmetricKey", config)
        self.assertIn("tags", config)
        self.assertIn("deviceUpdate", config)

    def test_build_config_optional_chain_path(self):
        config = build_x509_provisioning_config(
            registration_id="d1",
            id_scope="0ne1",
            cert_path="/etc/cert.pem",
            key_path="/etc/key.pem",
            chain_path="/etc/chain.pem",
        )
        self.assertEqual(config.get("chainPath"), "/etc/chain.pem")

    def test_validate_x509_config_accepts_valid(self):
        config = {
            "registrationId": "d1",
            "idScope": "0ne1",
            "certPath": "/etc/cert.pem",
            "keyPath": "/etc/key.pem",
        }
        ok, msg = validate_x509_provisioning_config(config)
        self.assertTrue(ok, msg)
        self.assertEqual(msg, "OK")

    def test_validate_x509_config_rejects_missing_field(self):
        config = {
            "registrationId": "d1",
            "idScope": "0ne1",
            "certPath": "/etc/cert.pem",
            # keyPath missing
        }
        ok, msg = validate_x509_provisioning_config(config)
        self.assertFalse(ok)
        self.assertIn("keyPath", msg)

    def test_validate_x509_config_rejects_symmetric_key(self):
        config = {
            "registrationId": "d1",
            "idScope": "0ne1",
            "certPath": "/etc/cert.pem",
            "keyPath": "/etc/key.pem",
            "symmetricKey": "base64key==",
        }
        ok, msg = validate_x509_provisioning_config(config)
        self.assertFalse(ok)
        self.assertIn("symmetricKey", msg)

    def test_config_roundtrip_json(self):
        config = build_x509_provisioning_config(
            registration_id="pi-serial-123",
            id_scope="0ne12345678",
            cert_path="/etc/nexuslocate/pki/device.crt",
            key_path="/etc/nexuslocate/pki/device.key",
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config, f, indent=2)
            path = f.name
        try:
            with open(path) as f2:
                loaded = json.load(f2)
            ok, _ = validate_x509_provisioning_config(loaded)
            self.assertTrue(ok)
            self.assertEqual(loaded["registrationId"], config["registrationId"])
        finally:
            Path(path).unlink(missing_ok=True)


@unittest.skipIf(not _CRYPTO_AVAILABLE, "cryptography not installed")
class TestCsrGenerationForEst(unittest.TestCase):
    """Test CSR generation for EST enrollment (registration_id as CN)."""

    def test_csr_and_key_generated(self):
        key_pem, csr_pem = generate_csr_and_key_pem("device-001")
        self.assertIn(b"-----BEGIN PRIVATE KEY-----", key_pem)
        self.assertIn(b"-----BEGIN CERTIFICATE REQUEST-----", csr_pem)

    def test_csr_contains_registration_id_as_cn(self):
        reg_id = "my-device-serial-12345"
        _, csr_pem = generate_csr_and_key_pem(reg_id)
        csr = x509.load_pem_x509_csr(csr_pem, default_backend())
        cn = None
        for attr in csr.subject:
            if attr.oid == NameOID.COMMON_NAME:
                cn = attr.value
                break
        self.assertEqual(cn, reg_id)

    def test_different_reg_ids_produce_different_keys(self):
        _, csr1 = generate_csr_and_key_pem("device-a")
        _, csr2 = generate_csr_and_key_pem("device-b")
        self.assertNotEqual(csr1, csr2)


@unittest.skipIf(not _CRYPTO_AVAILABLE, "cryptography not installed")
class TestCertificateParsing(unittest.TestCase):
    """Test parsing device certificate (CN and expiry)."""

    def test_get_cert_cn_and_expiry(self):
        # Create a self-signed cert for testing (in real flow EST returns CA-signed cert)
        key = rsa.generate_private_key(
            public_exponent=65537, key_size=2048, backend=default_backend()
        )
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test-device-99")])
        cert = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now(timezone.utc) - timedelta(hours=1))
            .not_valid_after(datetime.now(timezone.utc) + timedelta(days=90))
            .sign(key, hashes.SHA256(), default_backend())
        )
        cert_pem = cert.public_bytes(serialization.Encoding.PEM)
        cn, not_after = get_cert_cn_and_expiry(cert_pem)
        self.assertEqual(cn, "test-device-99")
        self.assertIsNotNone(not_after)


class TestEstEnvConfig(unittest.TestCase):
    """Test EST/bootstrap config parsing from env-like dict."""

    def test_parse_est_env_full(self):
        env = {
            "est_server_url": "https://est.example.com:8443/est",
            "est_bootstrap_token": "secret-token",
            "idScope": "0ne1",
        }
        out = parse_est_env_config(env)
        self.assertEqual(out["est_server_url"], "https://est.example.com:8443/est")
        self.assertEqual(out["est_bootstrap_token"], "secret-token")

    def test_parse_est_env_empty_or_missing(self):
        self.assertEqual(parse_est_env_config({}), {"est_server_url": None, "est_bootstrap_token": None})
        self.assertEqual(
            parse_est_env_config({"est_server_url": "  ", "est_bootstrap_token": ""}),
            {"est_server_url": None, "est_bootstrap_token": None},
        )


@unittest.skipIf(not _est_enrollment_output_available(), "Run test_est_enrollment.py first to generate device cert and key in est_test_output/")
@unittest.skipIf(not _CRYPTO_AVAILABLE, "cryptography not installed")
class TestX509UsingEstEnrollmentOutput(unittest.TestCase):
    """Use certificates produced by test_est_enrollment.py (est_test_output/)."""

    def test_device_cert_cn_and_expiry_from_est_output(self):
        cert_pem = EST_OUTPUT_CERT.read_bytes()
        cn, not_after = get_cert_cn_and_expiry(cert_pem)
        self.assertIsNotNone(cn, "Device cert should have a CN")
        self.assertIsNotNone(not_after, "Device cert should have not_valid_after")
        # test_est_enrollment uses REGISTRATION_ID = test-device-001
        self.assertEqual(cn, "test-device-001", "CN should match registration_id from test_est_enrollment")

    def test_device_cert_not_expired(self):
        cert_pem = EST_OUTPUT_CERT.read_bytes()
        _, not_after = get_cert_cn_and_expiry(cert_pem)
        now_utc_naive = datetime.now(timezone.utc).replace(tzinfo=None)
        self.assertLess(now_utc_naive, not_after, "Device cert from EST enrollment should not be expired")

    def test_x509_provisioning_config_with_est_output_paths(self):
        config = build_x509_provisioning_config(
            registration_id="test-device-001",
            id_scope="0ne00000000",
            cert_path=str(EST_OUTPUT_CERT),
            key_path=str(EST_OUTPUT_KEY),
            chain_path=str(EST_OUTPUT_CHAIN) if EST_OUTPUT_CHAIN.is_file() else None,
        )
        ok, msg = validate_x509_provisioning_config(config)
        self.assertTrue(ok, msg)
        self.assertEqual(config["certPath"], str(EST_OUTPUT_CERT))
        self.assertEqual(config["keyPath"], str(EST_OUTPUT_KEY))

    def test_config_roundtrip_json_with_est_output_paths(self):
        config = build_x509_provisioning_config(
            registration_id="test-device-001",
            id_scope="0ne00000000",
            cert_path=str(EST_OUTPUT_CERT),
            key_path=str(EST_OUTPUT_KEY),
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config, f, indent=2)
            path = f.name
        try:
            with open(path) as f2:
                loaded = json.load(f2)
            ok, _ = validate_x509_provisioning_config(loaded)
            self.assertTrue(ok)
            self.assertEqual(Path(loaded["certPath"]).resolve(), EST_OUTPUT_CERT.resolve())
            self.assertEqual(Path(loaded["keyPath"]).resolve(), EST_OUTPUT_KEY.resolve())
        finally:
            Path(path).unlink(missing_ok=True)


# Human-readable names for each test class (for client-facing summary)
_TEST_SUITE_DESCRIPTIONS = {
    "TestX509ProvisioningConfigStructure": "X.509 provisioning config structure and validation",
    "TestCsrGenerationForEst": "CSR generation for EST enrollment (registration_id as CN)",
    "TestCertificateParsing": "Certificate parsing (CN and expiry)",
    "TestEstEnvConfig": "EST/bootstrap config parsing",
    "TestX509UsingEstEnrollmentOutput": "Certificates from EST enrollment (est_test_output/)",
}


def _test_class_from_id(test_id: str) -> str | None:
    """Extract test class name from unittest test id (e.g. __main__.TestX509...test_foo -> TestX509...)."""
    if "." in test_id:
        parts = test_id.split(".")
        for p in parts:
            if p.startswith("Test") and p in _TEST_SUITE_DESCRIPTIONS:
                return p
    return None


if __name__ == "__main__":
    import sys

    print("\n" + "=" * 64)
    print("  X.509 / EST DEVICE SETUP VERIFICATION")
    print("=" * 64)
    print("  This run verifies:")
    for _desc in _TEST_SUITE_DESCRIPTIONS.values():
        print(f"    - {_desc}")
    if not _est_enrollment_output_available():
        print("    - [Partially skipped] EST enrollment output tests (run test_est_enrollment.py first)")
    print("=" * 64 + "\n")

    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
    result = runner.run(suite)

    # Client-facing summary: which classes failed, and which were skipped
    failed_by_class = {}
    for test, _ in list(result.failures) + list(result.errors):
        cls = _test_class_from_id(test.id())
        if cls:
            failed_by_class[cls] = failed_by_class.get(cls, 0) + 1

    def _skipped_reason(class_name: str) -> str | None:
        if class_name == "TestX509UsingEstEnrollmentOutput" and not _est_enrollment_output_available():
            return "Run test_est_enrollment.py first to generate est_test_output/"
        if class_name in ("TestCsrGenerationForEst", "TestCertificateParsing", "TestX509UsingEstEnrollmentOutput"):
            if not _CRYPTO_AVAILABLE:
                return "cryptography not installed"
        return None

    print("\n" + "=" * 64)
    print("  VERIFICATION SUMMARY")
    print("=" * 64)
    for class_name, desc in _TEST_SUITE_DESCRIPTIONS.items():
        if class_name in failed_by_class:
            print(f"  [FAILED] {desc} ({failed_by_class[class_name]} test(s) failed)")
        elif _skipped_reason(class_name):
            print(f"  [SKIPPED] {desc} ({_skipped_reason(class_name)})")
        else:
            print(f"  [PASSED] {desc}")
    print("=" * 64)
    if result.wasSuccessful():
        print("  OVERALL: All checks PASSED. X.509/EST device setup is working as expected.")
    else:
        print(f"  OVERALL: {len(result.failures) + len(result.errors)} check(s) FAILED. See details above.")
    print("=" * 64 + "\n")

    sys.exit(0 if result.wasSuccessful() else 1)
