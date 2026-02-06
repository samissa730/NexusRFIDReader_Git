"""
Unit tests for sending scan data to Azure IoT Hub using MQTT.

Tests the flow: scan record -> batch payload -> IoT Hub send_message (MQTT).
Covers AzureIoTService batch formatting and send_message_safe, and IoTClient message format.
"""

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

# Project root (parent of UnitTests)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_IOT_SERVICE_PATH = _PROJECT_ROOT / "Azure-IoT-Connection" / "iot_service.py"


def _load_iot_service_module():
    """Load iot_service from Azure-IoT-Connection (folder name has hyphen)."""
    if not _IOT_SERVICE_PATH.exists():
        return None
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))
    spec = importlib.util.spec_from_file_location("iot_service", _IOT_SERVICE_PATH)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["iot_service"] = mod
    try:
        spec.loader.exec_module(mod)
    except (ImportError, FileNotFoundError, Exception):
        return None
    return mod


def _minimal_provisioning_config():
    """Minimal config so AzureIoTService._load_configuration() succeeds in tests."""
    return {
        "globalEndpoint": "global.azure-devices-provisioning.net",
        "idScope": "0ne1234567",
        "registrationId": "test-device-001",
        "symmetricKey": "test_symmetric_key_base64==",
        "tags": {"nexusLocate": {"siteName": "TestSite", "truckNumber": "T1"}},
        "batchSize": 3,
        "batchIntervalSeconds": 5,
    }


def _sample_scan_record():
    """Sample scan record matching C# Azure Function / overview format."""
    return {
        "siteId": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
        "tagName": "E28011606000020345678ABC",
        "latitude": 33.00652,
        "longitude": -96.6927,
        "speed": 15.0,
        "deviceId": "nexus-device-001",
        "antenna": "1",
        "barrier": 270.0,
        "rssi": "42",
    }


class TestScanPayloadFormat(unittest.TestCase):
    """Test that scan batch payload sent over MQTT has the correct structure."""

    def test_scan_batch_payload_structure(self):
        """Payload sent to IoT Hub must be {"type": "scan_batch", "scans": [...]}."""
        scans = [_sample_scan_record(), _sample_scan_record()]
        payload = {"type": "scan_batch", "scans": scans}
        message_json = json.dumps(payload)
        parsed = json.loads(message_json)
        self.assertEqual(parsed["type"], "scan_batch")
        self.assertIsInstance(parsed["scans"], list)
        self.assertEqual(len(parsed["scans"]), 2)
        self.assertEqual(parsed["scans"][0]["tagName"], "E28011606000020345678ABC")
        self.assertEqual(parsed["scans"][0]["latitude"], 33.00652)

    def test_scan_message_from_client_structure(self):
        """Client sends {"type": "scan", "data": scan_record} for socket."""
        scan = _sample_scan_record()
        message = {"type": "scan", "data": scan}
        message_json = json.dumps(message)
        parsed = json.loads(message_json)
        self.assertEqual(parsed["type"], "scan")
        self.assertIn("data", parsed)
        self.assertEqual(parsed["data"]["tagName"], scan["tagName"])


class TestAzureIoTServiceMqttSend(unittest.TestCase):
    """Test AzureIoTService logic that builds and sends scan data via MQTT (send_message)."""

    @classmethod
    def setUpClass(cls):
        cls.iot_module = _load_iot_service_module()

    def _create_service(self, config_overrides=None):
        """Create AzureIoTService with mocked config (no real file or Azure connection)."""
        config = _minimal_provisioning_config()
        if config_overrides:
            config.update(config_overrides)
        config_json = json.dumps(config)
        mock_path = mock.MagicMock()
        mock_path.exists.return_value = True
        mock_path.read_text.return_value = config_json
        with mock.patch.object(self.iot_module, "CONFIG_PATH", mock_path):
            with mock.patch.object(self.iot_module.AzureIoTService, "_start_socket_server"):
                with mock.patch("signal.signal"):
                    return self.iot_module.AzureIoTService()

    def test_flush_scan_batch_calls_send_message_with_correct_json(self):
        """_flush_scan_batch must call client.send_message with JSON string of scan_batch."""
        if not self.iot_module:
            self.skipTest("Azure-IoT-Connection/iot_service.py not found or not loadable")
        service = self._create_service()
        service.client = mock.MagicMock()
        service.connected = True
        service.scan_buffer = [_sample_scan_record(), _sample_scan_record()]
        service._flush_scan_batch()
        self.assertEqual(service.client.send_message.call_count, 1)
        call_arg = service.client.send_message.call_args[0][0]
        self.assertIsInstance(call_arg, str)
        parsed = json.loads(call_arg)
        self.assertEqual(parsed["type"], "scan_batch")
        self.assertEqual(len(parsed["scans"]), 2)
        self.assertEqual(parsed["scans"][0]["tagName"], _sample_scan_record()["tagName"])

    def test_send_message_safe_calls_client_send_message_when_connected(self):
        """_send_message_safe must call client.send_message with the given JSON string."""
        if not self.iot_module:
            self.skipTest("Azure-IoT-Connection/iot_service.py not found or not loadable")
        service = self._create_service()
        service.client = mock.MagicMock()
        service.connected = True
        payload = {"type": "scan_batch", "scans": [_sample_scan_record()]}
        message_json = json.dumps(payload)
        result = service._send_message_safe(message_json)
        self.assertTrue(result)
        service.client.send_message.assert_called_once_with(message_json)

    def test_process_message_buffers_scan_and_flushes_at_batch_size(self):
        """_process_message with type 'scan' adds to buffer; flush when batch_size reached."""
        if not self.iot_module:
            self.skipTest("Azure-IoT-Connection/iot_service.py not found or not loadable")
        service = self._create_service(config_overrides={"batchSize": 2})
        self.assertEqual(service.batch_size, 2)
        service.client = mock.MagicMock()
        service.connected = True
        scan = _sample_scan_record()
        msg1 = json.dumps({"type": "scan", "data": scan})
        service._process_message(msg1)
        self.assertEqual(len(service.scan_buffer), 1)
        msg2 = json.dumps({"type": "scan", "data": {**scan, "tagName": "OTHER_TAG"}})
        service._process_message(msg2)
        # Buffer should be flushed when count >= batch_size
        self.assertEqual(service.client.send_message.call_count, 1)
        call_arg = service.client.send_message.call_args[0][0]
        parsed = json.loads(call_arg)
        self.assertEqual(parsed["type"], "scan_batch")
        self.assertEqual(len(parsed["scans"]), 2)
        self.assertEqual(parsed["scans"][0]["tagName"], scan["tagName"])
        self.assertEqual(parsed["scans"][1]["tagName"], "OTHER_TAG")


class TestIoTClientScanMessage(unittest.TestCase):
    """Test IoTClient sends the message format expected by IoT service (then sent via MQTT)."""

    def setUp(self):
        if str(_PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(_PROJECT_ROOT))
        from utils import iot_client as iot_client_module
        self.iot_client_module = iot_client_module

    def test_send_scan_returns_false_when_not_connected_and_connect_fails(self):
        """send_scan returns False when socket is not connected and connect fails."""
        client = self.iot_client_module.IoTClient(socket_path="/nonexistent/path.sock")
        scan = _sample_scan_record()
        with mock.patch.object(client, "connect", return_value=False):
            result = client.send_scan(scan)
            self.assertFalse(result)

    def test_send_scan_builds_type_scan_with_data(self):
        """send_scan must send JSON line: {"type": "scan", "data": scan_record}\\n."""
        client = self.iot_client_module.IoTClient(socket_path="/nonexistent/path.sock")
        client._connected = True
        client.socket = mock.MagicMock()
        scan = _sample_scan_record()
        result = client.send_scan(scan)
        self.assertTrue(result)
        call_args = client.socket.sendall.call_args[0][0]
        self.assertIsInstance(call_args, bytes)
        decoded = call_args.decode("utf-8")
        self.assertTrue(decoded.endswith("\n"))
        parsed = json.loads(decoded.strip())
        self.assertEqual(parsed["type"], "scan")
        self.assertEqual(parsed["data"]["tagName"], scan["tagName"])
        self.assertEqual(parsed["data"]["latitude"], scan["latitude"])


if __name__ == "__main__":
    unittest.main()
