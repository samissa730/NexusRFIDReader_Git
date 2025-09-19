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
APP_DIR = os.path.dirname(os.path.realpath(__file__))
CRASH_FILE = os.path.join(ROOT_DIR, "crash.dump")

# GPS Configuration - All hardcoded for production
GPS_CONFIG = {
    # GPS Type: "internet" or "external"
    "gps_type": "internet",
    
    # Internet GPS Settings
    "internet_gps": {
        "url": "http://ip-api.com/json/",
        "timeout": 3,
        "retry_count": 1,
        "retry_delay": 1,
        "update_interval": 4,  # seconds
        "retry_status_codes": [429, 500, 502, 503, 504]
    },
    
    # External GPS Settings
    "external_gps": {
        "port": "/dev/ttyUSB1" if is_rpi else "COM4",
        "baud_rate": 115200,
        "timeout": 1,
        "write_timeout": 1,
        "data_bits": 8,
        "stop_bits": 1,
        "parity": "N",
        "handshake": "None",
        "nmea_sentences": ["$GPRMC", "$GNRMC", "$GPGGA", "$GNGGA"],
        "buffer_size": 80,
        "read_delay": 0.2,
        "reconnect_delay": 0.1
    },
    
    # Cellular GPS Settings (for internal GPS)
    "cellular_gps": {
        "port": "/dev/ttyUSB2" if is_rpi else "COM3",
        "baud_rate": 115200,
        "at_commands": {
            "enable": "AT+QGPS=1",
            "status": "AT+QGPS?",
            "disable": "AT+QGPS=0"
        },
        "command_delay": 1
    },
    
    # GPS Data Processing
    "data_processing": {
        "speed_conversion": {
            "from_knots_to_mph": 1.15078,
            "from_mph_to_ms": 0.44704
        },
        "coordinate_precision": 4,
        "max_age_seconds": 300,  # 5 minutes
        "min_signal_quality": 1
    },
    
    # GPS Status Display
    "status_display": {
        "update_interval": 1,  # seconds
        "connection_timeout": 10,  # seconds
        "stale_data_threshold": 5  # seconds
    }
}

# Legacy settings for backward compatibility
INTERNET_GPS_URL = GPS_CONFIG["internet_gps"]["url"]
BAUD_RATE_QUE = GPS_CONFIG["external_gps"]["baud_rate"]
BAUD_RATE_DON = 9600
GPS_PORT = GPS_CONFIG["external_gps"]["port"]