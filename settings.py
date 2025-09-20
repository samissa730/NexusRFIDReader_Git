import json
import os
import platform

is_rpi = platform.system() == "Linux" and os.path.exists("/proc/device-tree/model")
is_win = platform.system() == "Windows"

if is_rpi:
    ROOT_DIR = os.path.expanduser("~/.nexusrfid")
elif is_win:
    ROOT_DIR = os.path.expanduser("~/Documents")

os.makedirs(ROOT_DIR, exist_ok=True)

INIT_SCREEN = "overview"
APP_DIR = os.path.dirname(os.path.realpath(__file__))
CRASH_FILE = os.path.join(ROOT_DIR, "crash.dump")

# GPS Configuration - Hardcoded for Production
GPS_CONFIG = {
    # GPS Type: "internet" or "external"
    "type": "external",
    
    # Internet GPS Settings (User Story 13047)
    "internet": {
        "url": "http://ip-api.com/json/",
        "timeout": 3,  # seconds
        "retry_count": 1,
        "retry_backoff": 1,
        "retry_status_codes": [429, 500, 502, 503, 504],
        "cache_ttl": 30,  # seconds
        "user_agent": "NexusRFIDReader/1.0"
    },
    
    # External GPS Settings (User Story 13048)
    "external": {
        "port": "/dev/ttyUSB1" if is_rpi else "COM4",
        "baud_rate": 115200,
        "timeout": 1,
        "write_timeout": 1,
        "data_bits": 8,
        "stop_bits": 1,
        "parity": "N",
        "handshake": "none",
        "at_command_port": "/dev/ttyUSB2" if is_rpi else "COM5",
        "at_command_baud": 115200
    },
    
    # GPS Data Processing Settings (User Stories 13170-13172)
    "processing": {
        "nmea_sentences": ["$GPRMC", "$GNRMC", "$GPGGA", "$GNGGA"],
        "speed_unit": "mps",  # mph, kmh, mps - using m/s as requested
        "coordinate_format": "decimal_degrees",
        "update_interval": 1,  # seconds
        "signal_quality_threshold": 3,  # minimum satellites
        "accuracy_threshold": 10  # meters
    },
    
    # Dashboard Settings (User Story 13173)
    "dashboard": {
        "update_rate": 1,  # seconds
        "stale_data_threshold": 5,  # seconds
        "show_signal_quality": True,
        "show_accuracy": True,
        "show_satellites": True
    }
}

# Legacy constants for backward compatibility
INTERNET_GPS_URL = GPS_CONFIG["internet"]["url"]
BAUD_RATE_QUE = GPS_CONFIG["external"]["baud_rate"]
BAUD_RATE_DON = 9600
GPS_PORT = GPS_CONFIG["external"]["port"]