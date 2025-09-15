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
        self.assertTrue(self.common.is_numeric("123"))
        self.assertTrue(self.common.is_numeric("3.14"))
        self.assertFalse(self.common.is_numeric("abc"))

    def test_update_dict_recursively(self):
        dest = {"a": 1, "b": {"c": 2, "d": 3}}
        updated = {"b": {"c": 20}, "e": 5}
        result = self.common.update_dict_recursively(dest, updated)
        self.assertEqual(result["a"], 1)
        self.assertEqual(result["b"]["c"], 20)
        self.assertEqual(result["b"]["d"], 3)
        self.assertEqual(result["e"], 5)

    def test_check_internet_connection_true(self):
        with mock.patch("socket.socket") as mock_socket:
            instance = mock.MagicMock()
            mock_socket.return_value = instance
            instance.connect.return_value = None
            self.assertTrue(self.common.check_internet_connection())
            instance.close.assert_called_once()

    def test_check_internet_connection_false(self):
        with mock.patch("socket.socket") as mock_socket:
            instance = mock.MagicMock()
            mock_socket.return_value = instance
            instance.connect.side_effect = OSError("no network")
            self.assertFalse(self.common.check_internet_connection())

    def test_kill_process_by_name_windows(self):
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
        self.common.is_rpi = True
        self.common.is_win = False

        cpuinfo = """processor\t: 0\nSerial\t\t: 00000000ABCDEF01\n"""

        mock_open = mock.mock_open(read_data=cpuinfo)
        with mock.patch.object(builtins, "open", mock_open):
            serial = self.common.get_serial()
            # The code slices and strips leading zeros, expecting trailing 16 chars then lstrip zeros
            self.assertEqual(serial, "ABCDEF01")


if __name__ == "__main__":
    unittest.main()


