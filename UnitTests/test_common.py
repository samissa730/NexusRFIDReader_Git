import builtins
import os
import types
import unittest
from unittest import mock


class TestCommon(unittest.TestCase):
    def setUp(self):
        # Import fresh module copy each time to re-evaluate platform flags
        self.common_module_name = 'utils.common'

    def _reload_common_with_platform(self, system_name: str, has_rpi_model: bool = False):
        with mock.patch('platform.system', return_value=system_name):
            # Simulate existence of RPi model path
            with mock.patch('os.path.exists', return_value=has_rpi_model):
                # Remove cached module to force re-import
                if self.common_module_name in builtins.__import__('sys').modules:
                    del builtins.__import__('sys').modules[self.common_module_name]
                import importlib
                return importlib.import_module(self.common_module_name)

    def test_flags_windows(self):
        common = self._reload_common_with_platform('Windows')
        self.assertFalse(common.is_rpi)
        self.assertTrue(common.is_win)

    def test_flags_rpi(self):
        common = self._reload_common_with_platform('Linux', has_rpi_model=True)
        self.assertTrue(common.is_rpi)
        self.assertFalse(common.is_win)

    def test_is_numeric(self):
        from utils import common
        self.assertTrue(common.is_numeric('123'))
        self.assertTrue(common.is_numeric('12.3'))
        self.assertFalse(common.is_numeric('abc'))

    def test_check_internet_connection_success(self):
        from utils import common
        with mock.patch('socket.socket') as mock_socket_cls:
            mock_socket = mock.Mock()
            mock_socket_cls.return_value = mock_socket
            mock_socket.connect.return_value = None
            self.assertTrue(common.check_internet_connection())
            mock_socket.connect.assert_called()

    def test_check_internet_connection_failure(self):
        from utils import common
        with mock.patch('socket.socket') as mock_socket_cls:
            mock_socket = mock.Mock()
            mock_socket_cls.return_value = mock_socket
            mock_socket.connect.side_effect = OSError('no route')
            self.assertFalse(common.check_internet_connection())

    def test_get_serial_windows_powershell(self):
        common = self._reload_common_with_platform('Windows')
        with mock.patch('subprocess.run') as mrun:
            mrun.return_value = types.SimpleNamespace(stdout='BFEBFBFF00090672\n')
            serial = common.get_serial()
            self.assertEqual(serial, 'BFEBFBFF00090672')

    def test_get_serial_windows_wmic_fallback(self):
        common = self._reload_common_with_platform('Windows')
        with mock.patch('subprocess.run') as mrun:
            # First call (PowerShell) raises, second call (WMIC cpu) returns, third unused
            def side_effect(*args, **kwargs):
                cmd = args[0]
                if isinstance(cmd, list) and 'powershell' in cmd[0].lower():
                    raise RuntimeError('ps failed')
                if isinstance(cmd, list) and cmd[:3] == ['wmic', 'cpu', 'get']:
                    return types.SimpleNamespace(stdout='ProcessorId\nBFEBFBFF00090672\n')
                return types.SimpleNamespace(stdout='')

            mrun.side_effect = side_effect
            serial = common.get_serial()
            self.assertEqual(serial, 'BFEBFBFF00090672')

    def test_get_serial_windows_uuid_last_resort(self):
        common = self._reload_common_with_platform('Windows')
        with mock.patch('subprocess.run') as mrun:
            def side_effect(*args, **kwargs):
                cmd = args[0]
                # PowerShell fails
                if isinstance(cmd, list) and 'powershell' in cmd[0].lower():
                    raise RuntimeError('ps failed')
                # WMIC cpu fails
                if isinstance(cmd, list) and cmd[:3] == ['wmic', 'cpu', 'get']:
                    raise RuntimeError('wmic cpu failed')
                # WMIC csproduct UUID returns
                if isinstance(cmd, list) and cmd[:3] == ['wmic', 'csproduct', 'get']:
                    return types.SimpleNamespace(stdout='UUID\n123e4567-e89b-12d3-a456-426614174000\n')
                return types.SimpleNamespace(stdout='')

            mrun.side_effect = side_effect
            serial = common.get_serial()
            self.assertEqual(serial, '123e4567-e89b-12d3-a456-426614174000')

    def test_get_serial_linux_rpi(self):
        # Simulate /proc/cpuinfo containing Serial line
        with mock.patch('platform.system', return_value='Linux'):
            with mock.patch('os.path.exists', return_value=True):
                # Re-import with RPi flags
                if 'utils.common' in builtins.__import__('sys').modules:
                    del builtins.__import__('sys').modules['utils.common']
                import importlib
                # Mock open to return cpuinfo with Serial
                fake_data = 'processor\t: 0\nSerial\t\t: 00000000BFEBFBFF00090672\n'
                with mock.patch('builtins.open', mock.mock_open(read_data=fake_data)):
                    common = importlib.import_module('utils.common')
                    serial = common.get_serial()
                    # Implementation strips leading zeros
                    self.assertEqual(serial, 'BFEBFBFF00090672')


if __name__ == '__main__':
    unittest.main()


