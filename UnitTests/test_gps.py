import unittest
from unittest import mock
import time
import threading
from unittest.mock import MagicMock, patch, call

# Import the modules we're testing
from utils import gps as gps_module
from utils import common as common_module
from settings import GPS_CONFIG


class TestGPS(unittest.TestCase):
    """Comprehensive unit tests for GPS functionality covering all user stories."""

    def setUp(self):
        """Set up test fixtures."""
        self.gps_module = gps_module
        self.common_module = common_module

    # =============================================================================
    # User Story 13047: IP-based Geolocation Service Tests
    # =============================================================================

    def test_internet_gps_fetch_success(self):
        """Test successful internet GPS data fetch."""
        with mock.patch("utils.gps.requests.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session

            mock_response = MagicMock()
            mock_response.raise_for_status.return_value = None
            mock_response.json.return_value = {
                "status": "success",
                "lat": 33.1234,
                "lon": -117.5678,
                "country": "United States",
                "city": "San Diego"
            }
            mock_session.get.return_value = mock_response

            gps = self.gps_module.GPS("internet")
            success = gps._fetch_internet_gps()

            self.assertTrue(success)
            data = gps.get_data()
            self.assertEqual(data["status"], "success")
            self.assertEqual(data["lat"], 33.1234)
            self.assertEqual(data["lon"], -117.5678)

    def test_internet_gps_fetch_failure_status(self):
        """Test internet GPS fetch with failure status."""
        with mock.patch("utils.gps.requests.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session

            mock_response = MagicMock()
            mock_response.raise_for_status.return_value = None
            mock_response.json.return_value = {"status": "fail"}
            mock_session.get.return_value = mock_response

            gps = self.gps_module.GPS("internet")
            success = gps._fetch_internet_gps()

            self.assertFalse(success)
            self.assertEqual(gps.get_data(), {})

    def test_internet_gps_fetch_exception(self):
        """Test internet GPS fetch with network exception."""
        with mock.patch("utils.gps.requests.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session
            mock_session.get.side_effect = Exception("network error")

            gps = self.gps_module.GPS("internet")
            success = gps._fetch_internet_gps()

            self.assertFalse(success)
            self.assertEqual(gps.get_data(), {})

    def test_internet_gps_caching(self):
        """Test internet GPS caching functionality."""
        with mock.patch("utils.gps.requests.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session

            mock_response = MagicMock()
            mock_response.raise_for_status.return_value = None
            mock_response.json.return_value = {
                "status": "success",
                "lat": 33.1234,
                "lon": -117.5678
            }
            mock_session.get.return_value = mock_response

            gps = self.gps_module.GPS("internet")
            
            # First fetch
            success1 = gps._fetch_internet_gps()
            self.assertTrue(success1)
            
            # Second fetch should use cache (within TTL)
            success2 = gps._fetch_internet_gps()
            self.assertTrue(success2)
            
            # Should only make one network request due to caching
            self.assertEqual(mock_session.get.call_count, 1)

    # =============================================================================
    # User Story 13048: GPS Device Detection and Configuration Tests
    # =============================================================================

    def test_set_gps_port_success(self):
        """Test successful GPS port configuration."""
        with mock.patch.object(self.gps_module, "send_at_command", side_effect=["OK", "OK"]) as mock_send:
            gps = self.gps_module.GPS("external", current_status="N/A")
            gps.set_GPS_port()
            
            # Should send enable command and status query
            self.assertEqual(mock_send.call_count, 2)
            self.assertEqual(mock_send.call_args_list[0].args[0], "AT+QGPS=1")
            self.assertEqual(mock_send.call_args_list[1].args[0], "AT+QGPS?")
            self.assertEqual(gps._current_status, "Connected")

    def test_set_gps_port_error(self):
        """Test GPS port configuration with error."""
        with mock.patch.object(self.gps_module, "send_at_command", side_effect=Exception("serial error")):
            gps = self.gps_module.GPS("external", current_status="N/A")
            gps.set_GPS_port()
            self.assertEqual(gps._current_status, "Error")

    def test_gps_initialization_external(self):
        """Test GPS initialization for external type."""
        with mock.patch.object(self.gps_module, "pre_config_gps", return_value=115200), \
             mock.patch.object(self.gps_module, "find_gps_port", return_value="/dev/ttyUSB1"):
            
            gps = self.gps_module.GPS("external")
            self.assertEqual(gps._gps_type, "external")
            self.assertEqual(gps._baud_rate, 115200)
            self.assertEqual(gps._port, "/dev/ttyUSB1")
            self.assertEqual(gps._current_status, "Connected")

    def test_gps_initialization_internet(self):
        """Test GPS initialization for internet type."""
        gps = self.gps_module.GPS("internet")
        self.assertEqual(gps._gps_type, "internet")
        self.assertEqual(gps._current_status, "N/A")

    # =============================================================================
    # User Story 13170: GPS Data Listener Tests
    # =============================================================================

    def test_external_gps_serial_connection(self):
        """Test external GPS serial connection."""
        with mock.patch("serial.Serial") as mock_serial:
            mock_ser = MagicMock()
            mock_ser.is_open = True
            mock_serial.return_value = mock_ser
            
            gps = self.gps_module.GPS("external")
            gps._port = "/dev/ttyUSB1"
            gps._baud_rate = 115200
            
            result = gps._connect_serial()
            self.assertEqual(result, mock_ser)
            mock_serial.assert_called_once()

    def test_external_gps_serial_connection_failure(self):
        """Test external GPS serial connection failure."""
        with mock.patch("serial.Serial", side_effect=Exception("port not found")):
            gps = self.gps_module.GPS("external")
            gps._port = "/dev/ttyUSB1"
            gps._baud_rate = 115200
            
            result = gps._connect_serial()
            self.assertIsNone(result)

    def test_gps_stop_cleanup(self):
        """Test GPS stop and cleanup functionality."""
        gps = self.gps_module.GPS("external")
        mock_ser = MagicMock()
        mock_ser.is_open = True
        gps._ser = mock_ser
        
        # Avoid actually waiting
        with mock.patch.object(self.gps_module.GPS, "wait", return_value=None):
            gps.stop()
        
        mock_ser.close.assert_called_once()
        self.assertIsNone(gps._ser)

    # =============================================================================
    # User Story 13171: Parse Incoming GPS Data Tests
    # =============================================================================

    def test_parse_nmea_data_success(self):
        """Test successful NMEA data parsing."""
        gps = self.gps_module.GPS("external")
        
        # Mock pynmea2.parse to return a valid message
        mock_msg = MagicMock()
        mock_msg.fields = [("label1", "lat"), ("label2", "lon"), ("label3", "spd_over_grnd"), ("label4", "true_course")]
        mock_msg.lat = "3342.1234"
        mock_msg.lon = "11712.5678"
        mock_msg.spd_over_grnd = 5.5
        mock_msg.true_course = 180.0
        
        with mock.patch("pynmea2.parse", return_value=mock_msg):
            gps._parse_nmea_data("$GPRMC,123456.00,A,3342.1234,N,11712.5678,W,5.5,180.0,010120,1.2,E,A*3C")
            
            self.assertEqual(gps._data["lat"], "3342.1234")
            self.assertEqual(gps._data["lon"], "11712.5678")
            self.assertEqual(gps._sdata[0], 5.5 * 1.15078)  # Converted to mph
            self.assertEqual(gps._sdata[1], 180.0)

    def test_parse_nmea_data_error(self):
        """Test NMEA data parsing with error."""
        gps = self.gps_module.GPS("external")
        
        with mock.patch("pynmea2.parse", side_effect=Exception("parse error")):
            gps._parse_nmea_data("invalid nmea data")
            
            self.assertEqual(gps._data, {})
            self.assertEqual(gps._sdata, [0, 0])

    def test_read_serial_data(self):
        """Test reading serial data."""
        gps = self.gps_module.GPS("external")
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_ser.in_waiting = 100
        mock_ser.readline.return_value = b"$GPRMC,123456.00,A,3342.1234,N,11712.5678,W,5.5,180.0,010120,1.2,E,A*3C\n"
        gps._ser = mock_ser
        
        with mock.patch.object(gps, "_parse_nmea_data") as mock_parse:
            gps._read_serial_data()
            mock_parse.assert_called_once()

    # =============================================================================
    # User Story 13172: Convert Speed, Latitude, Longitude Tests
    # =============================================================================

    def test_convert_to_decimal_latitude(self):
        """Test latitude conversion to decimal degrees."""
        result = self.common_module.convert_to_decimal("3342.1234", "N", True)
        expected = 33 + 42.1234/60
        self.assertAlmostEqual(result, expected, places=6)

    def test_convert_to_decimal_longitude(self):
        """Test longitude conversion to decimal degrees."""
        result = self.common_module.convert_to_decimal("11712.5678", "W", False)
        expected = -(117 + 12.5678/60)
        self.assertAlmostEqual(result, expected, places=6)

    def test_convert_to_decimal_south_west(self):
        """Test conversion with South/West directions."""
        lat_result = self.common_module.convert_to_decimal("3342.1234", "S", True)
        lon_result = self.common_module.convert_to_decimal("11712.5678", "W", False)
        
        self.assertLess(lat_result, 0)  # South should be negative
        self.assertLess(lon_result, 0)  # West should be negative

    def test_extract_from_gps(self):
        """Test extracting coordinates from GPS data."""
        gps_data = {
            "lat": "3342.1234",
            "lat_dir": "N",
            "lon": "11712.5678",
            "lon_dir": "W"
        }
        
        lat, lon = self.common_module.extract_from_gps(gps_data)
        self.assertNotEqual(lat, 0)
        self.assertNotEqual(lon, 0)

    def test_calculate_speed_bearing(self):
        """Test speed and bearing calculation."""
        lat1, lon1 = 33.1234, -117.5678
        lat2, lon2 = 33.1244, -117.5688
        time1 = 1000000
        time2 = 2000000
        
        speed, bearing = self.common_module.calculate_speed_bearing(lat1, lon1, time1, lat2, lon2, time2)
        
        self.assertGreater(speed, 0)
        self.assertGreaterEqual(bearing, 0)
        self.assertLessEqual(bearing, 360)

    def test_format_coordinates(self):
        """Test coordinate formatting."""
        result = self.common_module.format_coordinates(33.1234, -117.5678, 2)
        self.assertEqual(result, "33.12, -117.57")

    def test_format_speed(self):
        """Test speed formatting."""
        mph_result = self.common_module.format_speed(60.5, "mph")
        kmh_result = self.common_module.format_speed(60.5, "kmh")
        
        self.assertEqual(mph_result, "60.5 mph")
        self.assertEqual(kmh_result, "60.5 km/h")

    def test_format_bearing(self):
        """Test bearing formatting with cardinal directions."""
        north_result = self.common_module.format_bearing(0)
        east_result = self.common_module.format_bearing(90)
        south_result = self.common_module.format_bearing(180)
        west_result = self.common_module.format_bearing(270)
        
        self.assertIn("N", north_result)
        self.assertIn("E", east_result)
        self.assertIn("S", south_result)
        self.assertIn("W", west_result)

    # =============================================================================
    # User Story 13173: Update Dashboard Tests
    # =============================================================================

    def test_gps_get_coordinates(self):
        """Test getting GPS coordinates."""
        gps = self.gps_module.GPS("internet")
        gps._data = {"lat": 33.1234, "lon": -117.5678}
        
        lat, lon = gps.get_coordinates()
        self.assertEqual(lat, 33.1234)
        self.assertEqual(lon, -117.5678)

    def test_gps_get_speed_bearing(self):
        """Test getting GPS speed and bearing."""
        gps = self.gps_module.GPS("external")
        gps._sdata = [25.5, 180.0]
        
        speed, bearing = gps.get_speed_bearing()
        self.assertEqual(speed, 25.5)
        self.assertEqual(bearing, 180.0)

    def test_gps_get_signal_quality(self):
        """Test getting GPS signal quality."""
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

    def test_gps_is_data_stale(self):
        """Test GPS data staleness check."""
        gps = self.gps_module.GPS("internet")
        
        # Fresh data
        gps._last_update_time = time.time()
        self.assertFalse(gps.is_data_stale())
        
        # Stale data
        gps._last_update_time = time.time() - 10
        self.assertTrue(gps.is_data_stale())

    def test_validate_gps_coordinates(self):
        """Test GPS coordinate validation."""
        # Valid coordinates
        self.assertTrue(self.common_module.validate_gps_coordinates(33.1234, -117.5678))
        self.assertTrue(self.common_module.validate_gps_coordinates(90, 180))
        self.assertTrue(self.common_module.validate_gps_coordinates(-90, -180))
        
        # Invalid coordinates
        self.assertFalse(self.common_module.validate_gps_coordinates(91, 0))  # Lat too high
        self.assertFalse(self.common_module.validate_gps_coordinates(-91, 0))  # Lat too low
        self.assertFalse(self.common_module.validate_gps_coordinates(0, 181))  # Lon too high
        self.assertFalse(self.common_module.validate_gps_coordinates(0, -181))  # Lon too low

    # =============================================================================
    # Integration Tests
    # =============================================================================

    def test_gps_signals(self):
        """Test GPS signal emissions."""
        gps = self.gps_module.GPS("internet")
        
        # Mock signal handlers
        status_handler = MagicMock()
        data_handler = MagicMock()
        error_handler = MagicMock()
        
        gps.sig_status_changed.connect(status_handler)
        gps.sig_data_updated.connect(data_handler)
        gps.sig_error_occurred.connect(error_handler)
        
        # Test status change signal
        gps.sig_status_changed.emit(True)
        status_handler.assert_called_once_with(True)
        
        # Test data update signal
        test_data = {"lat": 33.1234, "lon": -117.5678}
        gps.sig_data_updated.emit(test_data)
        data_handler.assert_called_once_with(test_data)
        
        # Test error signal
        gps.sig_error_occurred.emit("Test error")
        error_handler.assert_called_once_with("Test error")

    def test_gps_configuration_loading(self):
        """Test GPS configuration loading from settings."""
        gps = self.gps_module.GPS("internet")
        
        # Check that configuration is loaded
        self.assertIsNotNone(gps._config)
        self.assertIsNotNone(gps._internet_config)
        self.assertIsNotNone(gps._external_config)
        self.assertIsNotNone(gps._processing_config)
        
        # Check specific configuration values
        self.assertEqual(gps._internet_config["timeout"], 3)
        self.assertEqual(gps._processing_config["speed_unit"], "mph")


if __name__ == "__main__":
    unittest.main()


