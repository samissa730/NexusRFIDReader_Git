import json
import os
import platform

is_rpi = platform.system() == "Linux" and os.path.exists("/proc/device-tree/model")
is_win = platform.system() == "Windows"

if is_rpi:
    ROOT_DIR = os.path.expanduser("~/.pl")
elif is_win:
    ROOT_DIR = os.path.expanduser("~/Documents")

os.makedirs(ROOT_DIR, exist_ok=True)

INIT_SCREEN = "overview"
INTERNET_GPS_URL = "http://ip-api.com/json/"
APP_DIR = os.path.dirname(os.path.realpath(__file__))
CRASH_FILE = os.path.join(ROOT_DIR, "crash.dump")

# GPS Configuration - All hardcoded for production
GPS_CONFIG = {
    "enabled": True,
    "type": "internet",  # "internet" or "external"
    "timeout_seconds": 3,
    "retry_count": 1,
    "retry_backoff_factor": 1,
    "retry_status_codes": [429, 500, 502, 503, 504],
    "update_interval_seconds": 4,
    "external": {
        "port": "/dev/ttyUSB1",
        "baud_rate": 115200,
        "timeout": 1,
        "write_timeout": 1,
        "at_commands": {
            "enable": "AT+QGPS=1",
            "status": "AT+QGPS?"
        }
    },
    "internet": {
        "url": "http://ip-api.com/json/",
        "user_agent": "NexusRFIDReader/1.0",
        "timeout": 3
    }
}

# Serial Port Configuration
BAUD_RATE_QUE = 115200
BAUD_RATE_DON = 9600
GPS_PORT = "/dev/ttyUSB1"

# GPS Data Processing Configuration
GPS_DATA_CONFIG = {
    "speed_unit": "mph",  # "mph", "kmh", "mps"
    "coordinate_precision": 6,
    "min_signal_strength": 0,
    "max_age_seconds": 300,  # 5 minutes
    "nmea_sentences": ["$GPRMC", "$GNRMC", "$GPGGA", "$GNGGA"]
}