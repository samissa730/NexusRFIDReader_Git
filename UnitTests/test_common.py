import builtins
import types
import unittest
from unittest import mock


class TestCommon(unittest.TestCase):
    def setUp(self):
        # Import once; mutate module-level flags as needed per test
        from utils import common as common_module
        self.common = common_module

    def test_is_numeric(self):
        """utils.common.is_numeric: validates numeric detection for ints, floats, and non-numeric strings (in utils/common.py)."""
        self.assertTrue(self.common.is_numeric("123"))
        self.assertTrue(self.common.is_numeric("3.14"))
        self.assertFalse(self.common.is_numeric("abc"))

    def test_update_dict_recursively(self):
        """utils.common.update_dict_recursively: ensures nested dicts merge correctly, preserving and updating deeper keys (in utils/common.py)."""
        dest = {"a": 1, "b": {"c": 2, "d": 3}}
        updated = {"b": {"c": 20}, "e": 5}
        result = self.common.update_dict_recursively(dest, updated)
        self.assertEqual(result["a"], 1)
        self.assertEqual(result["b"]["c"], 20)
        self.assertEqual(result["b"]["d"], 3)
        self.assertEqual(result["e"], 5)

    def test_check_internet_connection_true(self):
        """utils.common.check_internet_connection: returns True when socket connect succeeds and closes the socket (in utils/common.py)."""
        with mock.patch("socket.socket") as mock_socket:
            instance = mock.MagicMock()
            mock_socket.return_value = instance
            instance.connect.return_value = None
            self.assertTrue(self.common.check_internet_connection())
            instance.close.assert_called_once()

    def test_check_internet_connection_false(self):
        """utils.common.check_internet_connection: returns False when socket connect raises OSError (in utils/common.py)."""
        with mock.patch("socket.socket") as mock_socket:
            instance = mock.MagicMock()
            mock_socket.return_value = instance
            instance.connect.side_effect = OSError("no network")
            self.assertFalse(self.common.check_internet_connection())

    def test_kill_process_by_name_windows(self):
        """utils.common.kill_process_by_name: on Windows uses taskkill with correct flags and process (in utils/common.py)."""
        with mock.patch("platform.system", return_value="Windows"), \
             mock.patch("subprocess.run") as mock_run:
            self.common.kill_process_by_name("notepad.exe")
            mock_run.assert_called_once()
            args, kwargs = mock_run.call_args
            self.assertIn("taskkill", args[0])
            self.assertIn("/F", args[0])
            self.assertIn("/IM", args[0])
            self.assertIn("notepad.exe", args[0])

    def test_kill_process_by_name_unix_with_sig_and_sudo(self):
        """utils.common.kill_process_by_name: on Linux uses sudo pkill with -SIGTERM and target (in utils/common.py)."""
        with mock.patch("platform.system", return_value="Linux"), \
             mock.patch("subprocess.run") as mock_run:
            self.common.kill_process_by_name("python", use_sudo=True, sig="TERM")
            mock_run.assert_called_once()
            args, kwargs = mock_run.call_args
            cmd = args[0]
            # Expect sudo pkill -SIGTERM python
            self.assertEqual(cmd[0], "sudo")
            self.assertIn("pkill", cmd)
            self.assertIn("-SIGTERM", cmd)
            self.assertIn("python", cmd)

    def test_get_serial_windows_powershell(self):
        """utils.common.get_serial: Windows path returns CPU ProcessorId via PowerShell CIM (in utils/common.py)."""
        self.common.is_rpi = False
        self.common.is_win = True

        def fake_run(cmd, capture_output=False, text=False, check=False):
            if isinstance(cmd, (list, tuple)) and cmd and str(cmd[0]).lower().startswith("powershell"):
                m = types.SimpleNamespace()
                m.stdout = "BFEBFBFF00090672\n"
                m.returncode = 0
                return m
            raise AssertionError("Unexpected command path in test")

        with mock.patch("subprocess.run", side_effect=fake_run):
            serial = self.common.get_serial()
            self.assertEqual(serial, "BFEBFBFF00090672")

    def test_get_serial_windows_wmic_fallback(self):
        """utils.common.get_serial: Windows path falls back to WMIC ProcessorId when PowerShell fails (in utils/common.py)."""
        self.common.is_rpi = False
        self.common.is_win = True

        def fake_run(cmd, capture_output=False, text=False, check=False):
            if isinstance(cmd, list) and cmd:
                if str(cmd[0]).lower().startswith("powershell"):
                    raise subprocess.CalledProcessError(returncode=1, cmd="powershell")
                if cmd[:4] == ["wmic", "cpu", "get", "ProcessorId"]:
                    m = types.SimpleNamespace()
                    m.stdout = "ProcessorId\nBFEBFBFF00090672\n"
                    m.returncode = 0
                    return m
            raise AssertionError("Unexpected command path in test")

        import subprocess
        with mock.patch("subprocess.run", side_effect=fake_run):
            serial = self.common.get_serial()
            self.assertEqual(serial, "BFEBFBFF00090672")

    def test_get_serial_windows_uuid_fallback(self):
        """utils.common.get_serial: Windows path falls back to WMIC csproduct UUID when CPU id retrieval fails (in utils/common.py)."""
        self.common.is_rpi = False
        self.common.is_win = True

        def fake_run(cmd, capture_output=False, text=False, check=False):
            if isinstance(cmd, list) and cmd:
                if str(cmd[0]).lower().startswith("powershell"):
                    raise subprocess.CalledProcessError(returncode=1, cmd="powershell")
                if cmd[:4] == ["wmic", "cpu", "get", "ProcessorId"]:
                    raise subprocess.CalledProcessError(returncode=1, cmd="wmic cpu")
                if cmd[:4] == ["wmic", "csproduct", "get", "UUID"]:
                    m = types.SimpleNamespace()
                    m.stdout = "UUID\nA1B2C3D4-E5F6-1122-3344-5566778899AA\n"
                    m.returncode = 0
                    return m
            raise AssertionError("Unexpected command path in test")

        import subprocess
        with mock.patch("subprocess.run", side_effect=fake_run):
            serial = self.common.get_serial()
            self.assertEqual(serial, "A1B2C3D4-E5F6-1122-3344-5566778899AA")

    def test_get_serial_windows_all_fail(self):
        """utils.common.get_serial: Windows path returns 'UNKNOWN-WIN' and logs warning when all methods fail (in utils/common.py)."""
        self.common.is_rpi = False
        self.common.is_win = True

        def fake_run(cmd, capture_output=False, text=False, check=False):
            raise subprocess.CalledProcessError(returncode=1, cmd=cmd)

        import subprocess
        with mock.patch("subprocess.run", side_effect=fake_run), \
             mock.patch.object(self.common, "logger") as mock_logger:
            serial = self.common.get_serial()
            self.assertEqual(serial, "UNKNOWN-WIN")
            mock_logger.warning.assert_called()

    def test_get_serial_rpi(self):
        """utils.common.get_serial: Raspberry Pi path parses Serial from /proc/cpuinfo and strips leading zeros (in utils/common.py)."""
        self.common.is_rpi = True
        self.common.is_win = False

        cpuinfo = """processor\t: 0\nSerial\t\t: 00000000ABCDEF01\n"""

        mock_open = mock.mock_open(read_data=cpuinfo)
        with mock.patch.object(builtins, "open", mock_open):
            serial = self.common.get_serial()
            # The code slices and strips leading zeros, expecting trailing 16 chars then lstrip zeros
            self.assertEqual(serial, "ABCDEF01")


    def test_pre_config_gps_windows_returns_don(self):
        """utils.common.pre_config_gps: on Windows returns BAUD_RATE_DON without probing ports (in utils/common.py)."""
        from utils import common as c
        with mock.patch("platform.system", return_value="Windows"), \
             mock.patch.object(c, "serial") as mock_serial, \
             mock.patch.object(c, "BAUD_RATE_DON", 9600):
            result = c.pre_config_gps()
            self.assertEqual(result, 9600)

    def test_pre_config_gps_linux_probes_and_returns_que(self):
        """utils.common.pre_config_gps: on Linux sends AT and returns BAUD_RATE_QUE after first success (in utils/common.py)."""
        from utils import common as c
        fake_ports = [types.SimpleNamespace(device="/dev/ttyUSB0"), types.SimpleNamespace(device="/dev/ttyUSB1")]
        ser_mock = mock.MagicMock()
        context_mgr = mock.MagicMock()
        context_mgr.__enter__.return_value = ser_mock
        context_mgr.__exit__.return_value = False
        with mock.patch("platform.system", return_value="Linux"), \
             mock.patch.object(c, "serial") as mock_serial, \
             mock.patch.object(c, "time") as mock_time, \
             mock.patch.object(c, "BAUD_RATE_QUE", 115200):
            mock_serial.tools.list_ports.comports.return_value = fake_ports
            mock_serial.Serial.return_value = context_mgr
            result = c.pre_config_gps()
            self.assertEqual(result, 115200)
            ser_mock.write.assert_called()
            mock_time.sleep.assert_called()

    def test_find_gps_port_detects_nmea(self):
        """utils.common.find_gps_port: returns port when line starts with $G (in utils/common.py)."""
        from utils import common as c
        fake_ports = [types.SimpleNamespace(device="/dev/ttyUSB0"), types.SimpleNamespace(device="/dev/ttyUSB1")]
        ser_mock = mock.MagicMock()
        ser_mock.in_waiting = 0
        ser_mock.readline.return_value = b"$GPGGA,....\r\n"
        context_mgr = mock.MagicMock()
        context_mgr.__enter__.return_value = ser_mock
        context_mgr.__exit__.return_value = False
        with mock.patch.object(c, "serial") as mock_serial, \
             mock.patch.object(c, "time") as mock_time:
            mock_serial.tools.list_ports.comports.return_value = fake_ports
            mock_serial.Serial.return_value = context_mgr
            port = c.find_gps_port(baud_rate=4800)
            self.assertIn(port, ["/dev/ttyUSB0", "/dev/ttyUSB1"])
            mock_time.sleep.assert_called()

    def test_find_gps_port_none_when_no_match(self):
        """utils.common.find_gps_port: returns None when no port outputs NMEA sentences (in utils/common.py)."""
        from utils import common as c
        fake_ports = [types.SimpleNamespace(device="/dev/ttyUSB0")]
        ser_mock = mock.MagicMock()
        ser_mock.in_waiting = 200
        ser_mock.readline.return_value = b"NOT_NMEA\r\n"
        context_mgr = mock.MagicMock()
        context_mgr.__enter__.return_value = ser_mock
        context_mgr.__exit__.return_value = False
        with mock.patch.object(c, "serial") as mock_serial:
            mock_serial.tools.list_ports.comports.return_value = fake_ports
            mock_serial.Serial.return_value = context_mgr
            port = c.find_gps_port(baud_rate=4800)
            self.assertIsNone(port)

    def test_send_at_command_writes_and_reads(self):
        """utils.common.send_at_command: opens serial, writes command with CRLF, delays, and returns response (in utils/common.py)."""
        from utils import common as c
        ser_mock = mock.MagicMock()
        ser_mock.inWaiting.return_value = 5
        ser_mock.read.return_value = b"OK\r\n"
        with mock.patch.object(c, "serial") as mock_serial, \
             mock.patch.object(c, "time") as mock_time, \
             mock.patch.object(c, "GPS_PORT", "COM3"):
            mock_serial.Serial.return_value = ser_mock  # direct instance (since code does not use context manager)
            resp = c.send_at_command("AT+QGPS=1", delay=0.1)
            ser_mock.write.assert_called()
            mock_time.sleep.assert_called()
            self.assertEqual(resp, "OK\r\n")


if __name__ == "__main__":
    unittest.main()


