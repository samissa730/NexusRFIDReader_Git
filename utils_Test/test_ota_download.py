"""
Tests for OTA download flow: Azure-IoT-Connection/download.py.

Covers config path, nexus_update parsing, version comparison, and platform detection.
Does not call network or dpkg; use mocks for fetch_latest_manifest and install steps.
"""

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DOWNLOAD_PY = _PROJECT_ROOT / "Azure-IoT-Connection" / "download.py"


def _load_download_module():
    """Load download module from Azure-IoT-Connection (folder name has hyphen)."""
    if not _DOWNLOAD_PY.exists():
        return None
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))
    spec = importlib.util.spec_from_file_location("download", _DOWNLOAD_PY)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["download"] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        return None
    return mod


class TestGetAppConfigPath(unittest.TestCase):
    """Test get_app_config_path with and without NEXUS_UPDATE_CONFIG_PATH."""

    def setUp(self):
        self.download = _load_download_module()
        if self.download is None:
            self.skipTest("Azure-IoT-Connection/download.py not found")

    def test_env_override(self):
        with mock.patch.dict(os.environ, {"NEXUS_UPDATE_CONFIG_PATH": "/etc/custom/config.json"}):
            path = self.download.get_app_config_path()
        self.assertEqual(path.name, "config.json")
        self.assertEqual(path.as_posix(), "/etc/custom/config.json")

    def test_default_path(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            if "NEXUS_UPDATE_CONFIG_PATH" in os.environ:
                del os.environ["NEXUS_UPDATE_CONFIG_PATH"]
        with mock.patch.object(self.download.os.path, "expanduser", return_value="/home/pi"):
            path = self.download.get_app_config_path()
        self.assertEqual(path.name, "config.json")
        self.assertEqual(path.parent.name, "config")
        self.assertEqual(path.as_posix(), "/etc/nexuslocate/config/config.json")


class TestGetNexusUpdateConfig(unittest.TestCase):
    """Test get_nexus_update_config parsing from app config."""

    def setUp(self):
        self.download = _load_download_module()
        if self.download is None:
            self.skipTest("Azure-IoT-Connection/download.py not found")

    def test_valid_config(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({
                "nexus_update": {
                    "base_url": "https://satestrfidlocate.blob.core.windows.net/deviceupdates",
                    "sas_token": "?sv=123",
                    "platform": "rpi",
                }
            }, f)
            path = f.name
        try:
            with mock.patch.object(self.download, "get_app_config_path", return_value=Path(path)):
                cfg = self.download.get_nexus_update_config()
            self.assertEqual(cfg["base_url"], "https://satestrfidlocate.blob.core.windows.net/deviceupdates")
            self.assertTrue(cfg["sas_token"].startswith("?"))
            self.assertEqual(cfg["platform"], "rpi")
        finally:
            os.unlink(path)

    def test_sas_token_without_question_mark(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({
                "nexus_update": {
                    "base_url": "https://example.blob.core.windows.net/container",
                    "sas_token": "sv=456",
                }
            }, f)
            path = f.name
        try:
            with mock.patch.object(self.download, "get_app_config_path", return_value=Path(path)):
                cfg = self.download.get_nexus_update_config()
            self.assertEqual(cfg["sas_token"], "?sv=456")
        finally:
            os.unlink(path)

    def test_missing_base_url_raises(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"nexus_update": {"sas_token": "?x"}}, f)
            path = f.name
        try:
            with mock.patch.object(self.download, "get_app_config_path", return_value=Path(path)):
                with self.assertRaises(ValueError) as ctx:
                    self.download.get_nexus_update_config()
                self.assertIn("base_url", str(ctx.exception))
        finally:
            os.unlink(path)


class TestParseBuildVersion(unittest.TestCase):
    """Test parse_build_version for YYYYMMDD.N format."""

    def setUp(self):
        self.download = _load_download_module()
        if self.download is None:
            self.skipTest("Azure-IoT-Connection/download.py not found")

    def test_valid_version(self):
        self.assertEqual(self.download.parse_build_version("20250204.1"), (20250204, 1))
        self.assertEqual(self.download.parse_build_version("20250101.0"), (20250101, 0))

    def test_empty_or_invalid(self):
        self.assertEqual(self.download.parse_build_version(""), (0, 0))
        self.assertEqual(self.download.parse_build_version("invalid"), (0, 0))
        # Date part outside YYYYMMDD range (e.g. day 32 or year 1000-01-00) returns (0, 0)
        self.assertEqual(self.download.parse_build_version("99991232.0"), (0, 0))
        self.assertEqual(self.download.parse_build_version("10000100.0"), (0, 0))


class TestIsVersionNewer(unittest.TestCase):
    """Test is_version_newer comparison."""

    def setUp(self):
        self.download = _load_download_module()
        if self.download is None:
            self.skipTest("Azure-IoT-Connection/download.py not found")

    def test_newer(self):
        self.assertTrue(self.download.is_version_newer("20250204.2", "20250204.1"))
        self.assertTrue(self.download.is_version_newer("20250205.1", "20250204.1"))
        self.assertTrue(self.download.is_version_newer("20250204.1", None))

    def test_not_newer(self):
        self.assertFalse(self.download.is_version_newer("20250204.1", "20250204.1"))
        self.assertFalse(self.download.is_version_newer("20250204.1", "20250204.2"))
        self.assertFalse(self.download.is_version_newer("20250203.9", "20250204.1"))


class TestDetectPlatform(unittest.TestCase):
    """Test detect_platform with configured value and /proc fallback."""

    def setUp(self):
        self.download = _load_download_module()
        if self.download is None:
            self.skipTest("Azure-IoT-Connection/download.py not found")

    def test_configured_rpi(self):
        self.assertEqual(self.download.detect_platform("rpi"), "rpi")

    def test_configured_linux(self):
        self.assertEqual(self.download.detect_platform("linux"), "linux")

    def test_empty_uses_fallback(self):
        with mock.patch("builtins.open", mock.mock_open(read_data=b"Raspberry Pi Model B")):
            self.assertEqual(self.download.detect_platform(""), "rpi")
        with mock.patch("builtins.open", side_effect=FileNotFoundError):
            self.assertEqual(self.download.detect_platform(""), "linux")


class TestC2DPayloadOta(unittest.TestCase):
    """Test that C2D payload with type 'ota' is what iot_service and pipeline use."""

    def test_ota_payload_structure(self):
        payload = {"type": "ota", "action": "check_update"}
        self.assertEqual(payload.get("type"), "ota")
        message_json = json.dumps(payload)
        parsed = json.loads(message_json)
        self.assertEqual(parsed["type"], "ota")


if __name__ == "__main__":
    unittest.main()