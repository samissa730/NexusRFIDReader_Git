import importlib
import builtins

import pytest


MODULE_PATH = "utils.common"


def reload_common(monkeypatch, platform_system: str, is_rpi_exists: bool):
    monkeypatch.setattr("platform.system", lambda: platform_system, raising=False)
    # Control RPi detection via os.path.exists("/proc/device-tree/model")
    monkeypatch.setattr("os.path.exists", lambda p: is_rpi_exists if p == "/proc/device-tree/model" else False, raising=False)
    import utils.common as common
    importlib.reload(common)
    return common


def test_is_win_flag_true_on_windows(monkeypatch):
    common = reload_common(monkeypatch, platform_system="Windows", is_rpi_exists=False)
    assert common.is_win is True
    assert common.is_rpi is False


def test_get_serial_windows_powershell_success(monkeypatch):
    common = reload_common(monkeypatch, platform_system="Windows", is_rpi_exists=False)

    class Result:
        def __init__(self, stdout=""):
            self.stdout = stdout

    def fake_run(cmd, capture_output=False, text=False, check=False):
        command_str = " ".join(cmd)
        if "powershell" in command_str:
            return Result(stdout="BFEBFBFF00090672\r\n")
        raise AssertionError("Unexpected command in this test: " + command_str)

    monkeypatch.setattr(common.subprocess, "run", fake_run)

    assert common.get_serial() == "BFEBFBFF00090672"


def test_get_serial_windows_wmic_fallback(monkeypatch):
    common = reload_common(monkeypatch, platform_system="Windows", is_rpi_exists=False)

    class Result:
        def __init__(self, stdout=""):
            self.stdout = stdout

    def fake_run(cmd, capture_output=False, text=False, check=False):
        command_str = " ".join(cmd)
        if "powershell" in command_str:
            raise Exception("powershell failed")
        if command_str.startswith("wmic cpu get ProcessorId"):
            return Result(stdout="ProcessorId\nABCDEF1234567890\n")
        raise AssertionError("Unexpected command in this test: " + command_str)

    monkeypatch.setattr(common.subprocess, "run", fake_run)

    assert common.get_serial() == "ABCDEF1234567890"


def test_get_serial_windows_uuid_last_resort(monkeypatch):
    common = reload_common(monkeypatch, platform_system="Windows", is_rpi_exists=False)

    class Result:
        def __init__(self, stdout=""):
            self.stdout = stdout

    def fake_run(cmd, capture_output=False, text=False, check=False):
        command_str = " ".join(cmd)
        if "powershell" in command_str:
            raise Exception("powershell failed")
        if command_str.startswith("wmic cpu get ProcessorId"):
            raise Exception("wmic cpu failed")
        if command_str.startswith("wmic csproduct get UUID"):
            return Result(stdout="UUID\nU-123-456\n")
        raise AssertionError("Unexpected command in this test: " + command_str)

    monkeypatch.setattr(common.subprocess, "run", fake_run)

    assert common.get_serial() == "U-123-456"


def test_get_serial_non_rpi_non_win_default(monkeypatch):
    common = reload_common(monkeypatch, platform_system="Darwin", is_rpi_exists=False)
    assert common.is_rpi is False
    assert common.is_win is False
    assert common.get_serial() == "12345678"


def test_get_serial_rpi_reads_cpuinfo(monkeypatch):
    # Simulate Raspberry Pi with a Serial line
    common = reload_common(monkeypatch, platform_system="Linux", is_rpi_exists=True)

    cpuinfo = (
        "processor\t: 0\n"
        "Model\t\t: Raspberry Pi\n"
        "Serial\t\t: 00000000ABCDEF12\n"
    )

    def fake_open(file, mode="r", *args, **kwargs):
        if file == "/proc/cpuinfo" and "r" in mode:
            return FakeFile(cpuinfo)
        raise FileNotFoundError(file)

    class FakeFile:
        def __init__(self, content):
            self._lines = content.splitlines(True)

        def __iter__(self):
            return iter(self._lines)

        def close(self):
            pass

    monkeypatch.setattr(builtins, "open", fake_open)

    assert common.get_serial() == "ABCDEF12"


