import unittest
from unittest import mock


class TestCommon(unittest.TestCase):
    def setUp(self):
        from utils import common as c
        self.c = c

    def test_convert_to_decimal(self):
        self.assertAlmostEqual(self.c.convert_to_decimal('3745.1234', 'N', True), 37.7520567, places=5)
        self.assertAlmostEqual(self.c.convert_to_decimal('12231.5000', 'W', False), -122.525, places=5)
        self.assertEqual(self.c.convert_to_decimal('12', 'N', True), 0)

    def test_extract_from_gps(self):
        lat, lon = self.c.extract_from_gps({'lat': '3745.00', 'lat_dir': 'N', 'lon': '12231.00', 'lon_dir': 'W'})
        self.assertAlmostEqual(lat, 37 + 45/60, places=6)
        self.assertAlmostEqual(lon, -(122 + 31/60), places=6)
        self.assertEqual(self.c.extract_from_gps({}), (0, 0))

    def test_get_date_from_utc(self):
        ts = 1726852178 * 1_000_000
        self.assertEqual(self.c.get_date_from_utc(ts), '2024/09/20 17:09:38')

    def test_calculate_speed_bearing(self):
        spd_mph, brg = self.c.calculate_speed_bearing(0.0, 0.0, 1_000_000, 0.0, 0.001, 11_000_000)
        self.assertTrue(24.0 <= spd_mph <= 26.0)
        self.assertTrue(85.0 <= brg <= 95.0)

    def test_is_ipv4_address(self):
        self.assertTrue(self.c.is_ipv4_address('192.168.0.1'))
        self.assertFalse(self.c.is_ipv4_address('999.168.0.1'))

    def test_get_mac_address(self):
        with mock.patch('utils.common.uuid.getnode', return_value=0x123456789ABCDEF0):
            mac = self.c.get_mac_address()
            self.assertRegex(mac, r'^(?:[0-9A-F]{2}:){5,7}[0-9A-F]{2}$')

    def test_pre_config_gps_windows_and_linux(self):
        with mock.patch('platform.system', return_value='Windows'), \
             mock.patch.object(self.c, 'GPS_CONFIG', {}), \
             mock.patch.object(self.c, 'BAUD_RATE_DON', 9600):
            self.assertEqual(self.c.pre_config_gps(), 9600)

        fake_ports = [mock.MagicMock(device='/dev/ttyUSB0')]
        with mock.patch('platform.system', return_value='Linux'), \
             mock.patch.object(self.c, 'serial') as mser, \
             mock.patch.object(self.c, 'GPS_CONFIG', {'baud_rate': 115200, 'probe_baud_rate': 115200}), \
             mock.patch.object(self.c, 'time') as mt:
            ctx = mock.MagicMock()
            ser = mock.MagicMock()
            ctx.__enter__.return_value = ser
            mser.Serial.return_value = ctx
            mser.tools.list_ports.comports.return_value = fake_ports
            self.assertEqual(self.c.pre_config_gps(), 115200)
            ser.write.assert_called()
            mt.sleep.assert_called()

    def test_find_gps_port(self):
        fake_ports = [mock.MagicMock(device='/dev/ttyUSB0')]
        with mock.patch.object(self.c, 'serial') as mser, \
             mock.patch.object(self.c, 'time') as mt:
            ctx = mock.MagicMock()
            ser = mock.MagicMock()
            ser.in_waiting = 0
            ser.readline.return_value = b"$GPGGA,\r\n"
            ctx.__enter__.return_value = ser
            mser.Serial.return_value = ctx
            mser.tools.list_ports.comports.return_value = fake_ports
            port = self.c.find_gps_port(4800)
            self.assertEqual(port, '/dev/ttyUSB0')
            mt.sleep.assert_called()

        with mock.patch.object(self.c, 'serial') as mser:
            ctx = mock.MagicMock()
            ser = mock.MagicMock()
            ser.in_waiting = 200
            ser.readline.return_value = b"NOT_NMEA\r\n"
            ctx.__enter__.return_value = ser
            mser.Serial.return_value = ctx
            mser.tools.list_ports.comports.return_value = fake_ports
            port = self.c.find_gps_port(4800)
            self.assertIsNone(port)


if __name__ == '__main__':
    unittest.main()


