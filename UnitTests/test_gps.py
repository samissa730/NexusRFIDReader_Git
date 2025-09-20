import unittest
from unittest import mock


class TestGPS(unittest.TestCase):
    def setUp(self):
        # Import once; use module namespace to access GPS class and internals
        from utils import gps as gps_module
        self.gps_module = gps_module

    def test_set_GPS_port_success(self):
        """utils.gps.GPS.set_GPS_port: on external type with N/A status sends AT commands and sets status External (in utils/gps.py)."""
        with mock.patch.object(self.gps_module, "send_at_command", side_effect=["OK", "OK"]) as mock_send, mock.patch.object(self.gps_module, "logger"):
            gps = self.gps_module.GPS("external", current_status="N/A")
            gps.set_GPS_port()
            # First enables GPS, then queries status
            self.assertEqual(mock_send.call_count, 2)
            self.assertEqual(mock_send.call_args_list[0].args[0], "AT+QGPS=1")
            self.assertEqual(mock_send.call_args_list[1].args[0], "AT+QGPS?")
            self.assertEqual(gps._current_status, "External")

    def test_set_GPS_port_error(self):
        """utils.gps.GPS.set_GPS_port: sets status Error when send_at_command raises (in utils/gps.py)."""
        with mock.patch.object(self.gps_module, "send_at_command", side_effect=Exception("serial error")) as _, mock.patch.object(self.gps_module, "logger"):
            gps = self.gps_module.GPS("external", current_status="N/A")
            gps.set_GPS_port()
            self.assertEqual(gps._current_status, "Error")

    def test_stop_closes_serial(self):
        """utils.gps.GPS.stop: closes open serial via _close_serial and clears reference (in utils/gps.py)."""
        gps = self.gps_module.GPS("external")
        ser_mock = mock.MagicMock()
        ser_mock.is_open = True
        gps._ser = ser_mock
        # Avoid actually waiting
        with mock.patch.object(self.gps_module.GPS, "wait", return_value=None):
            gps.stop()
        ser_mock.close.assert_called_once()
        self.assertIsNone(gps._ser)

    def test_fetch_internet_gps_success(self):
        """utils.gps.GPS._fetch_internet_gps: returns True and stores JSON when status is success (in utils/gps.py)."""
        with mock.patch("utils.gps.requests.Session") as mock_session_cls:
            mock_session = mock.MagicMock()
            mock_session_cls.return_value = mock_session

            mock_response = mock.MagicMock()
            mock_response.raise_for_status.return_value = None
            mock_response.json.return_value = {
                "status": "success",
                "lat": 33.1234,
                "lon": -117.5678,
                "country": "United States",
            }
            mock_session.get.return_value = mock_response

            gps = self.gps_module.GPS("internet")
            ok = gps._fetch_internet_gps()

            self.assertTrue(ok)
            data = gps.get_data()
            self.assertIsInstance(data, dict)
            self.assertEqual(data.get("status"), "success")
            self.assertEqual(data.get("lat"), 33.1234)
            self.assertEqual(data.get("lon"), -117.5678)

    def test_fetch_internet_gps_failure_status(self):
        """utils.gps.GPS._fetch_internet_gps: returns False and clears data when API returns status fail (in utils/gps.py)."""
        with mock.patch("utils.gps.requests.Session") as mock_session_cls:
            mock_session = mock.MagicMock()
            mock_session_cls.return_value = mock_session

            mock_response = mock.MagicMock()
            mock_response.raise_for_status.return_value = None
            mock_response.json.return_value = {"status": "fail"}
            mock_session.get.return_value = mock_response

            gps = self.gps_module.GPS("internet")
            ok = gps._fetch_internet_gps()

            self.assertFalse(ok)
            self.assertEqual(gps.get_data(), {})

    def test_fetch_internet_gps_exception(self):
        """utils.gps.GPS._fetch_internet_gps: returns False and clears data when request raises exception (in utils/gps.py)."""
        with mock.patch("utils.gps.requests.Session") as mock_session_cls:
            mock_session = mock.MagicMock()
            mock_session_cls.return_value = mock_session
            mock_session.get.side_effect = Exception("network error")

            gps = self.gps_module.GPS("internet")
            ok = gps._fetch_internet_gps()

            self.assertFalse(ok)
            self.assertEqual(gps.get_data(), {})

    def test_gps_initialization_external(self):
        """utils.gps.GPS.__init__: initializes external GPS with correct status (in utils/gps.py)."""
        with mock.patch.object(self.gps_module, "pre_config_gps", return_value=115200), \
             mock.patch.object(self.gps_module, "find_gps_port", return_value="/dev/ttyUSB0"):
            gps = self.gps_module.GPS("external")
            self.assertEqual(gps._gps_type, "external")
            self.assertEqual(gps._current_status, "External")
            self.assertEqual(gps._port, "/dev/ttyUSB0")
            self.assertEqual(gps._baud_rate, 115200)

    def test_gps_initialization_external_no_port(self):
        """utils.gps.GPS.__init__: initializes external GPS as Disconnected when no port found (in utils/gps.py)."""
        with mock.patch.object(self.gps_module, "pre_config_gps", return_value=115200), \
             mock.patch.object(self.gps_module, "find_gps_port", return_value=None):
            gps = self.gps_module.GPS("external")
            self.assertEqual(gps._gps_type, "external")
            self.assertEqual(gps._current_status, "Disconnected")
            self.assertIsNone(gps._port)

    def test_gps_initialization_internet(self):
        """utils.gps.GPS.__init__: initializes internet GPS with Internal status (in utils/gps.py)."""
        gps = self.gps_module.GPS("internet")
        self.assertEqual(gps._gps_type, "internet")
        self.assertEqual(gps._current_status, "Internal")

    def test_get_coordinates_external(self):
        """utils.gps.GPS.get_coordinates: returns coordinates for external GPS (in utils/gps.py)."""
        gps = self.gps_module.GPS("external")
        gps._data = {"lat": "3342.1234", "lat_dir": "N", "lon": "96884.5678", "lon_dir": "W"}
        
        with mock.patch.object(self.gps_module, "convert_to_decimal", side_effect=[33.7020567, -96.8094633]):
            lat, lon = gps.get_coordinates()
            self.assertAlmostEqual(lat, 33.7020567, places=6)
            self.assertAlmostEqual(lon, -96.8094633, places=6)

    def test_get_coordinates_internet(self):
        """utils.gps.GPS.get_coordinates: returns coordinates for internet GPS (in utils/gps.py)."""
        gps = self.gps_module.GPS("internet")
        gps._data = {"lat": 33.2640, "lon": -96.8844}
        
        lat, lon = gps.get_coordinates()
        self.assertEqual(lat, 33.2640)
        self.assertEqual(lon, -96.8844)

    def test_get_coordinates_no_data(self):
        """utils.gps.GPS.get_coordinates: returns (0,0) when no data available (in utils/gps.py)."""
        gps = self.gps_module.GPS("external")
        gps._data = {}
        
        lat, lon = gps.get_coordinates()
        self.assertEqual(lat, 0)
        self.assertEqual(lon, 0)

    def test_get_speed_bearing(self):
        """utils.gps.GPS.get_speed_bearing: returns speed and bearing from sdata (in utils/gps.py)."""
        gps = self.gps_module.GPS("external")
        gps._sdata = [5.5, 45.0]
        
        speed, bearing = gps.get_speed_bearing()
        self.assertEqual(speed, 5.5)
        self.assertEqual(bearing, 45.0)

    def test_get_speed_bearing_no_data(self):
        """utils.gps.GPS.get_speed_bearing: returns (0,0) when no sdata (in utils/gps.py)."""
        gps = self.gps_module.GPS("external")
        gps._sdata = []
        
        speed, bearing = gps.get_speed_bearing()
        self.assertEqual(speed, 0)
        self.assertEqual(bearing, 0)

    def test_get_status(self):
        """utils.gps.GPS.get_status: returns current GPS status (in utils/gps.py)."""
        gps = self.gps_module.GPS("external")
        gps._current_status = "External"
        
        status = gps.get_status()
        self.assertEqual(status, "External")

    def test_is_data_stale_true(self):
        """utils.gps.GPS.is_data_stale: returns True when data is older than threshold (in utils/gps.py)."""
        gps = self.gps_module.GPS("external")
        gps._last_update_time = 0  # Very old data
        
        with mock.patch.object(self.gps_module, "time") as mock_time:
            mock_time.time.return_value = 1000  # Current time
            stale = gps.is_data_stale()
            self.assertTrue(stale)

    def test_is_data_stale_false(self):
        """utils.gps.GPS.is_data_stale: returns False when data is recent (in utils/gps.py)."""
        gps = self.gps_module.GPS("external")
        
        with mock.patch.object(self.gps_module, "time") as mock_time:
            current_time = 1000
            mock_time.time.return_value = current_time
            gps._last_update_time = current_time - 1  # 1 second ago
            stale = gps.is_data_stale()
            self.assertFalse(stale)

    def test_get_signal_quality_external(self):
        """utils.gps.GPS.get_signal_quality: returns signal quality for external GPS (in utils/gps.py)."""
        gps = self.gps_module.GPS("external")
        gps._data = {
            "num_sats": 8,
            "fix_quality": 1,
            "horizontal_dil": 2.5
        }
        
        quality = gps.get_signal_quality()
        self.assertEqual(quality["satellites"], 8)
        self.assertEqual(quality["fix_quality"], 1)
        self.assertEqual(quality["accuracy"], 2.5)
        self.assertEqual(quality["status"], "Fix")

    def test_get_signal_quality_external_no_fix(self):
        """utils.gps.GPS.get_signal_quality: returns No Fix for external GPS with no fix (in utils/gps.py)."""
        gps = self.gps_module.GPS("external")
        gps._data = {
            "num_sats": 3,
            "fix_quality": 0,
            "horizontal_dil": 10.0
        }
        
        quality = gps.get_signal_quality()
        self.assertEqual(quality["status"], "No Fix")

    def test_get_signal_quality_internet(self):
        """utils.gps.GPS.get_signal_quality: returns signal quality for internet GPS (in utils/gps.py)."""
        gps = self.gps_module.GPS("internet")
        gps._data = {"lat": 33.2640, "lon": -96.8844}
        
        quality = gps.get_signal_quality()
        self.assertEqual(quality["status"], "Internet Fix")
        self.assertEqual(quality["accuracy"], 1000)

    def test_get_signal_quality_no_data(self):
        """utils.gps.GPS.get_signal_quality: returns default quality when no data (in utils/gps.py)."""
        gps = self.gps_module.GPS("external")
        gps._data = {}
        
        quality = gps.get_signal_quality()
        self.assertEqual(quality["satellites"], 0)
        self.assertEqual(quality["accuracy"], 0)
        self.assertEqual(quality["fix_quality"], 0)
        self.assertEqual(quality["status"], "No Fix")

    def test_parse_nmea_data_valid(self):
        """utils.gps.GPS._parse_nmea_data: parses valid NMEA sentence and extracts data (in utils/gps.py)."""
        gps = self.gps_module.GPS("external")
        
        with mock.patch("utils.gps.pynmea2.parse") as mock_parse:
            mock_msg = mock.MagicMock()
            mock_msg.fields = [("Latitude", "lat"), ("Longitude", "lon"), ("Speed", "spd_over_grnd"), ("Course", "true_course")]
            mock_msg.lat = "3342.1234"
            mock_msg.lon = "96884.5678"
            mock_msg.spd_over_grnd = 5.5
            mock_msg.true_course = 45.0
            mock_parse.return_value = mock_msg
            
            gps._parse_nmea_data("$GPRMC,123456.00,A,3342.1234,N,96884.5678,W,5.5,45.0,200920,1.2,E,A*12")
            
            self.assertEqual(gps._data["lat"], "3342.1234")
            self.assertEqual(gps._data["lon"], "96884.5678")
            self.assertAlmostEqual(gps._sdata[0], 2.83, places=2)  # 5.5 knots * 0.514444 = 2.83 m/s
            self.assertEqual(gps._sdata[1], 45.0)

    def test_parse_nmea_data_invalid(self):
        """utils.gps.GPS._parse_nmea_data: handles invalid NMEA sentence (in utils/gps.py)."""
        gps = self.gps_module.GPS("external")
        
        with mock.patch("utils.gps.pynmea2.parse", side_effect=self.gps_module.pynmea2.ParseError("Invalid sentence", "INVALID_SENTENCE")):
            gps._parse_nmea_data("INVALID_SENTENCE")
            
            self.assertEqual(gps._data, {})
            self.assertEqual(gps._sdata, [0, 0])

    def test_connect_serial_success(self):
        """utils.gps.GPS._connect_serial: connects to serial port successfully (in utils/gps.py)."""
        gps = self.gps_module.GPS("external")
        gps._port = "/dev/ttyUSB0"
        gps._baud_rate = 115200
        
        with mock.patch("utils.gps.serial.Serial") as mock_serial:
            mock_ser = mock.MagicMock()
            mock_serial.return_value = mock_ser
            
            result = gps._connect_serial()
            
            self.assertEqual(result, mock_ser)
            mock_serial.assert_called_once_with(
                port="/dev/ttyUSB0",
                baudrate=115200,
                timeout=1,
                write_timeout=1,
                bytesize=8,
                stopbits=1,
                parity="N"
            )

    def test_connect_serial_failure(self):
        """utils.gps.GPS._connect_serial: returns None on connection failure (in utils/gps.py)."""
        gps = self.gps_module.GPS("external")
        gps._port = "/dev/ttyUSB0"
        gps._baud_rate = 115200
        
        with mock.patch("utils.gps.serial.Serial", side_effect=self.gps_module.serial.SerialException("Port not found")):
            result = gps._connect_serial()
            
            self.assertIsNone(result)

    def test_connect_serial_no_port(self):
        """utils.gps.GPS._connect_serial: returns None when no port configured (in utils/gps.py)."""
        gps = self.gps_module.GPS("external")
        gps._port = None
        
        result = gps._connect_serial()
        
        self.assertIsNone(result)

    def test_close_serial(self):
        """utils.gps.GPS._close_serial: closes open serial connection (in utils/gps.py)."""
        gps = self.gps_module.GPS("external")
        mock_ser = mock.MagicMock()
        mock_ser.is_open = True
        gps._ser = mock_ser
        
        gps._close_serial()
        
        mock_ser.close.assert_called_once()
        self.assertIsNone(gps._ser)

    def test_close_serial_already_closed(self):
        """utils.gps.GPS._close_serial: handles already closed serial connection (in utils/gps.py)."""
        gps = self.gps_module.GPS("external")
        mock_ser = mock.MagicMock()
        mock_ser.is_open = False
        gps._ser = mock_ser
        
        gps._close_serial()
        
        mock_ser.close.assert_not_called()
        self.assertIsNone(gps._ser)


if __name__ == "__main__":
    unittest.main()


