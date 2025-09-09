import json
import os
import platform
import socket
import subprocess
import threading
from utils.logger import logger

is_rpi = platform.system() == "Linux" and os.path.exists("/proc/device-tree/model")


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
        return cpuserial[-8:]
    else:
        return "12345678"

def drop_cache():
    """Drop system cache to free memory"""
    if is_rpi:
        try:
            subprocess.run(["sync"], check=True)
            with open("/proc/sys/vm/drop_caches", "w") as f:
                f.write("3")
        except Exception as e:
            logger.error(f"Error dropping cache: {str(e)}")


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


def disable_screen_saver():
    if is_rpi:
        os.system('sudo sh -c "TERM=linux setterm -blank 0 >/dev/tty0"')


def set_brightness(val):
    logger.debug(f"Setting brightness to {val}")
    if is_rpi:
        os.system(f"echo {val} | sudo tee /sys/class/backlight/*/brightness")


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
