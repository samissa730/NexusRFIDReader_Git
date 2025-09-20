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

    def test_convert_to_decimal_latitude(self):
        """utils.common.convert_to_decimal: converts N latitude correctly (in utils/common.py)."""
        val = self.common.convert_to_decimal("3745.1234", "N", is_latitude=True)
        # 37 + 45.1234/60 ≈ 37.7520567
        self.assertAlmostEqual(val, 37.7520567, places=6)
    def test_convert_to_decimal_longitude_west(self):
        """utils.common.convert_to_decimal: converts W longitude to negative (in utils/common.py)."""
        val = self.common.convert_to_decimal("12231.5000", "W", is_latitude=False)
        # -(122 + 31.5/60) = -122.525
        self.assertAlmostEqual(val, -122.525, places=6)
    def test_convert_to_decimal_invalid_inputs(self):
        """utils.common.convert_to_decimal: returns 0 for invalid inputs (in utils/common.py)."""
        self.assertEqual(self.common.convert_to_decimal("12", "N", True), 0)
        self.assertEqual(self.common.convert_to_decimal("1234", "E", False), 0)
    def test_extract_from_gps_valid(self):
        """utils.common.extract_from_gps: extracts and converts latitude/longitude (in utils/common.py)."""
        gps = {"lat": "3745.0000", "lat_dir": "N", "lon": "12231.0000", "lon_dir": "W"}
        lat, lon = self.common.extract_from_gps(gps)
        self.assertAlmostEqual(lat, 37 + 45/60, places=6)
        self.assertAlmostEqual(lon, -(122 + 31/60), places=6)
    def test_extract_from_gps_missing_or_empty(self):
        """utils.common.extract_from_gps: returns (0,0) for empty or missing keys (in utils/common.py)."""
        self.assertEqual(self.common.extract_from_gps({}), (0, 0))
        # Missing keys
        self.assertEqual(self.common.extract_from_gps({"lat": "3745.00", "lat_dir": "N"}), (0, 0))
    def test_calculate_speed_bearing(self):
        """utils.common.calculate_speed_bearing: computes m/s and bearing using geodesic (in utils/common.py)."""
        lat1, lon1 = 0.0, 0.0
        lat2, lon2 = 0.0, 0.001  # ~111.319 m east at equator
        time1 = 1_000_000
        time2 = 11_000_000  # 10 seconds later
        speed_mps, bearing = self.common.calculate_speed_bearing(lat1, lon1, time1, lat2, lon2, time2)
        # Expected ~11.13 m/s; allow tolerance due to geodesic precision differences
        self.assertTrue(10.0 <= speed_mps <= 12.0)
        # Bearing should be roughly east (≈ 90 degrees)
        self.assertTrue(85.0 <= bearing <= 95.0)
    
    def test_pre_config_gps_windows_returns_don(self):
        """utils.common.pre_config_gps: on Windows returns 9600 without probing ports (in utils/common.py)."""
        from utils import common as c
        with mock.patch("platform.system", return_value="Windows"), \
             mock.patch.object(c, "serial") as mock_serial:
            result = c.pre_config_gps()
            self.assertEqual(result, 9600)

    def test_pre_config_gps_linux_probes_and_returns_que(self):
        """utils.common.pre_config_gps: on Linux sends AT and returns GPS baud rate after first success (in utils/common.py)."""
        from utils import common as c
        fake_ports = [types.SimpleNamespace(device="/dev/ttyUSB0"), types.SimpleNamespace(device="/dev/ttyUSB1")]
        ser_mock = mock.MagicMock()
        context_mgr = mock.MagicMock()
        context_mgr.__enter__.return_value = ser_mock
        context_mgr.__exit__.return_value = False
        with mock.patch("platform.system", return_value="Linux"), \
             mock.patch.object(c, "serial") as mock_serial, \
             mock.patch.object(c, "time") as mock_time, \
             mock.patch.object(c, "GPS_CONFIG", {"external": {"baud_rate": 115200}}):
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
             mock.patch.object(c, "GPS_CONFIG", {"external": {"at_command_port": "COM3", "at_command_baud": 115200}}):
            mock_serial.Serial.return_value = ser_mock  # direct instance (since code does not use context manager)
            resp = c.send_at_command("AT+QGPS=1", delay=0.1)
            ser_mock.write.assert_called()
            mock_time.sleep.assert_called()
            self.assertEqual(resp, "OK\r\n")

    def test_get_date_from_utc_valid_timestamp(self):
        """utils.common.get_date_from_utc: formats UTC timestamp as YYYY/MM/DD HH:MM:SS (in utils/common.py)."""
        # Test with a known timestamp: 2024-09-20 17:09:38 UTC
        timestamp = 1726852178 * 1_000_000  # microseconds
        result = self.common.get_date_from_utc(timestamp)
        self.assertEqual(result, "2024/09/20 17:09:38")

    def test_get_date_from_utc_invalid_timestamp(self):
        """utils.common.get_date_from_utc: returns N/A for invalid timestamp (in utils/common.py)."""
        with mock.patch.object(self.common, "logger"):
            # Test with a very large timestamp that would cause an error
            result = self.common.get_date_from_utc(999999999999999999999)
            self.assertEqual(result, "N/A")

    def test_validate_gps_coordinates_valid(self):
        """utils.common.validate_gps_coordinates: returns True for valid coordinates (in utils/common.py)."""
        self.assertTrue(self.common.validate_gps_coordinates(33.2640, -96.8844))
        self.assertTrue(self.common.validate_gps_coordinates(0, 0))
        self.assertTrue(self.common.validate_gps_coordinates(90, 180))
        self.assertTrue(self.common.validate_gps_coordinates(-90, -180))

    def test_validate_gps_coordinates_invalid(self):
        """utils.common.validate_gps_coordinates: returns False for invalid coordinates (in utils/common.py)."""
        self.assertFalse(self.common.validate_gps_coordinates(91, 0))  # lat > 90
        self.assertFalse(self.common.validate_gps_coordinates(-91, 0))  # lat < -90
        self.assertFalse(self.common.validate_gps_coordinates(0, 181))  # lon > 180
        self.assertFalse(self.common.validate_gps_coordinates(0, -181))  # lon < -180

    def test_format_coordinates_valid(self):
        """utils.common.format_coordinates: formats valid coordinates with specified precision (in utils/common.py)."""
        result = self.common.format_coordinates(33.2640, -96.8844, precision=6)
        self.assertEqual(result, "33.264000, -96.884400")

    def test_format_coordinates_invalid(self):
        """utils.common.format_coordinates: returns N/A for invalid coordinates (in utils/common.py)."""
        result = self.common.format_coordinates(91, 0)
        self.assertEqual(result, "N/A")

    def test_format_speed_mps(self):
        """utils.common.format_speed: formats speed in m/s (in utils/common.py)."""
        result = self.common.format_speed(5.5, "mps")
        self.assertEqual(result, "5.5 m/s")

    def test_format_speed_mph(self):
        """utils.common.format_speed: formats speed in mph (in utils/common.py)."""
        result = self.common.format_speed(10.2, "mph")
        self.assertEqual(result, "10.2 mph")

    def test_format_speed_kmh(self):
        """utils.common.format_speed: formats speed in km/h (in utils/common.py)."""
        result = self.common.format_speed(15.7, "kmh")
        self.assertEqual(result, "15.7 km/h")

    def test_format_speed_default(self):
        """utils.common.format_speed: uses default unit when not specified (in utils/common.py)."""
        result = self.common.format_speed(8.3)
        self.assertEqual(result, "8.3 m/s")

    def test_format_bearing_north(self):
        """utils.common.format_bearing: formats bearing with cardinal directions (in utils/common.py)."""
        result = self.common.format_bearing(0)
        self.assertEqual(result, "0° N")

    def test_format_bearing_east(self):
        """utils.common.format_bearing: formats east bearing (in utils/common.py)."""
        result = self.common.format_bearing(90)
        self.assertEqual(result, "90° E")

    def test_format_bearing_south(self):
        """utils.common.format_bearing: formats south bearing (in utils/common.py)."""
        result = self.common.format_bearing(180)
        self.assertEqual(result, "180° S")

    def test_format_bearing_west(self):
        """utils.common.format_bearing: formats west bearing (in utils/common.py)."""
        result = self.common.format_bearing(270)
        self.assertEqual(result, "270° W")

    def test_format_bearing_northeast(self):
        """utils.common.format_bearing: formats northeast bearing (in utils/common.py)."""
        result = self.common.format_bearing(45)
        self.assertEqual(result, "45° NE")

    def test_format_bearing_negative(self):
        """utils.common.format_bearing: normalizes negative bearing (in utils/common.py)."""
        result = self.common.format_bearing(-45)
        self.assertEqual(result, "315° NW")

    def test_is_ipv4_address_valid(self):
        """utils.common.is_ipv4_address: validates correct IPv4 addresses (in utils/common.py)."""
        self.assertTrue(self.common.is_ipv4_address("192.168.1.1"))
        self.assertTrue(self.common.is_ipv4_address("127.0.0.1"))
        self.assertTrue(self.common.is_ipv4_address("255.255.255.255"))
        self.assertTrue(self.common.is_ipv4_address("0.0.0.0"))

    def test_is_ipv4_address_invalid(self):
        """utils.common.is_ipv4_address: rejects invalid IPv4 addresses (in utils/common.py)."""
        self.assertFalse(self.common.is_ipv4_address("256.1.1.1"))  # > 255
        self.assertFalse(self.common.is_ipv4_address("192.168.1"))  # missing octet
        self.assertFalse(self.common.is_ipv4_address("192.168.1.1.1"))  # extra octet
        self.assertFalse(self.common.is_ipv4_address("192.168.1.a"))  # non-numeric
        self.assertFalse(self.common.is_ipv4_address(""))  # empty string


if __name__ == "__main__":
    unittest.main()


