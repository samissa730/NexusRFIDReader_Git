import json
import os
import platform
import socket
import subprocess
import threading
from utils.logger import logger

is_rpi = platform.system() == "Linux" and os.path.exists("/proc/device-tree/model")
is_win = platform.system() == "Windows"


def get_serial():
    """
    Get serial number of the device
    :return:
    """
    if is_rpi:
        cpuserial = "0000000000000000"
        f = open("/proc/cpuinfo", "r")
        for line in f:
            if line.startswith("Serial"):
                cpuserial = line[10:26].lstrip("0")
        f.close()
        return cpuserial
    elif is_win:
        # Prefer CPU ProcessorId to identify Windows device
        try:
            # Try PowerShell CIM first (modern and reliable)
            ps_cmd = [
                "powershell",
                "-NoProfile",
                "-Command",
                "(Get-CimInstance Win32_Processor | Select-Object -First 1 -ExpandProperty ProcessorId)"
            ]
            result = subprocess.run(ps_cmd, capture_output=True, text=True, check=True)
            proc_id = (result.stdout or "").strip().replace("\r", "").replace("\n", "")
            if proc_id:
                return proc_id
        except Exception as e:
            logger.debug(f"PowerShell ProcessorId retrieval failed: {str(e)}")

        try:
            # Fallback to legacy WMIC
            wmic_cmd = ["wmic", "cpu", "get", "ProcessorId"]
            result = subprocess.run(wmic_cmd, capture_output=True, text=True, check=True)
            # Output example:\nProcessorId\nBFEBFBFF00090672\n
            lines = [l.strip() for l in (result.stdout or "").splitlines() if l.strip()]
            for line in lines:
                if line and line.lower() != "processorid":
                    return line
        except Exception as e:
            logger.debug(f"WMIC ProcessorId retrieval failed: {str(e)}")

        try:
            # Last resort: system UUID (not CPU but stable enough)
            wmic_uuid_cmd = ["wmic", "csproduct", "get", "UUID"]
            result = subprocess.run(wmic_uuid_cmd, capture_output=True, text=True, check=True)
            lines = [l.strip() for l in (result.stdout or "").splitlines() if l.strip()]
            for line in lines:
                if line and line.lower() != "uuid":
                    return line
        except Exception as e:
            logger.debug(f"WMIC UUID retrieval failed: {str(e)}")

        logger.warning("Falling back to placeholder serial on Windows; unable to retrieve ProcessorId/UUID")
        return "UNKNOWN-WIN"
    else:
        return "12345678"


def kill_process_by_name(proc_name, use_sudo=False, sig=None):
    """Kill process by name"""
    try:
        if platform.system() == "Windows":
            subprocess.run(["taskkill", "/F", "/IM", proc_name], check=True)
        else:
            cmd = ["pkill"]
            if sig:
                cmd.extend(["-SIGTERM"])
            if use_sudo:
                cmd.insert(0, "sudo")
            cmd.append(proc_name)
            subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"Error killing process {proc_name}: {str(e)}")

def update_dict_recursively(dest, updated):
    """
    Update dictionary recursively.
    :param dest: Destination dict.
    :type dest: dict
    :param updated: Updated dict to be applied.
    :type updated: dict
    :return:
    """
    for k, v in updated.items():
        if isinstance(dest, dict):
            if isinstance(v, dict):
                r = update_dict_recursively(dest.get(k, {}), v)
                dest[k] = r
            else:
                dest[k] = updated[k]
        else:
            dest = {k: updated[k]}
    return dest


_c_lock = threading.Lock()

def is_numeric(val):
    try:
        float(val)
        return True
    except ValueError:
        return False

def check_internet_connection(host="8.8.8.8", port=53, timeout=3):
    try:
        socket.setdefaulttimeout(timeout)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((host, port))
    except OSError:
        return False
    else:
        s.close()
        return True
