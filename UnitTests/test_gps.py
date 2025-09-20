import unittest
from unittest import mock


class TestGPS(unittest.TestCase):
    def setUp(self):
        # Import once; use module namespace to access GPS class and internals
        from utils import gps as gps_module
        self.gps_module = gps_module

    def test_set_GPS_port_success(self):
        """utils.gps.GPS.set_GPS_port: on external type with N/A status sends AT commands and sets status Connected (in utils/gps.py)."""
        with mock.patch.object(self.gps_module, "send_at_command", side_effect=["OK", "OK"]) as mock_send, mock.patch.object(self.gps_module, "logger"):
            gps = self.gps_module.GPS("external", current_status="N/A")
            gps.set_GPS_port()
            # First enables GPS, then queries status
            self.assertEqual(mock_send.call_count, 2)
            self.assertEqual(mock_send.call_args_list[0].args[0], "AT+QGPS=1")
            self.assertEqual(mock_send.call_args_list[1].args[0], "AT+QGPS?")
            self.assertEqual(gps._current_status, "Connected")

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


if __name__ == "__main__":
    unittest.main()


