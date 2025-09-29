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
    
    # Internet GPS Settings
    "internet": {
        "url": "http://ip-api.com/json/",
        "timeout": 3,  # seconds
        "retry_count": 1,
        "retry_backoff": 1,
        "retry_status_codes": [429, 500, 502, 503, 504],
        "cache_ttl": 30,  # seconds
        "user_agent": "NexusRFIDReader/1.0"
    },
    
    # External GPS Settings
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
    
    # GPS Data Processing Settings
    "processing": {
        "nmea_sentences": ["$GPRMC", "$GNRMC", "$GPGGA", "$GNGGA"],
        "speed_unit": "mps",  # mph, kmh, mps - using m/s as requested
        "coordinate_format": "decimal_degrees",
        "update_interval": 1,  # seconds
        "signal_quality_threshold": 3,  # minimum satellites
        "accuracy_threshold": 10  # meters
    },
    
    # Dashboard Settings
    "dashboard": {
        "update_rate": 1,  # seconds
        "stale_data_threshold": 5,  # seconds
        "show_signal_quality": True,
        "show_accuracy": True,
        "show_satellites": True
    }
}

# RFID Configuration
RFID_CONFIG = {
    "reader_ip": "169.254.216.147",
    "port": 5084,  # LLRP_DEFAULT_PORT
    "antennas": [1],
    "tx_power": 0,  # Max power
    "modulation": "M8",
    "tari": 0,  # Auto
    "session": 1,
    "tag_population": 4,
    "report_every_n_tags": 1,
    "impinj_search_mode": "1",  # Single
    "impinj_reports": False,
    "tag_content_selector": {
        "EnableROSpecID": True,
        "EnableSpecIndex": True,
        "EnableInventoryParameterSpecID": True,
        "EnableAntennaID": True,
        "EnableChannelIndex": True,
        "EnablePeakRSSI": True,
        "EnableFirstSeenTimestamp": True,
        "EnableLastSeenTimestamp": True,
        "EnableTagSeenCount": True,
        "EnableAccessSpecID": True,
        "C1G2EPCMemorySelector": {
            "EnableCRC": True,
            "EnablePCBits": True,
        }
    }
}

# API Configuration
API_CONFIG = {
    "login_url": "https://rfidngpsinventory.com/rfid/user/userLogin",
    "record_upload_url": "https://rfidngpsinventory.com/rfid/mobileApp/updateRfidScanning",
    "health_upload_url": "https://rfidngpsinventory.com/rfid/dashBoard/rfidapphealth",
    "timeout": 4,
    "retry_count": 3,
    "retry_backoff": 1,
    "retry_status_codes": [429, 500, 502, 503, 504],
    "chunk_size": 1000,
    "upload_interval": 7,  # seconds
    "health_interval": 15,  # seconds
    "token_refresh_interval": 600,  # 10 minutes
    "data_retention_hours": 10  # hours
}

# API Authentication (choose one: token, or username/password)
API_CREDENTIALS = {
    "token": "",          # Paste pre-issued token here (takes priority if set)
    "username": "",       # Used if token is empty
    "password": ""        # Used if token is empty
}

# Data Storage Configuration
DATABASE_CONFIG = {
    "use_database": True,
    "db_file": "database.db",
    "table_name": "records",
    "schema": {
        "id": "INTEGER PRIMARY KEY",
        "rfidTag": "TEXT NOT NULL",
        "antenna": "INTEGER NOT NULL",
        "RSSI": "INTEGER NOT NULL",
        "latitude": "REAL NOT NULL",
        "longitude": "REAL NOT NULL",
        "speed": "REAL NOT NULL",
        "heading": "REAL NOT NULL",
        "locationCode": "TEXT NOT NULL",
        "username": "TEXT NOT NULL",
        "tag1": "TEXT NOT NULL",
        "value1": "TEXT NOT NULL",
        "tag2": "TEXT NOT NULL",
        "value2": "TEXT NOT NULL",
        "tag3": "TEXT NOT NULL",
        "value3": "TEXT NOT NULL",
        "tag4": "TEXT NOT NULL",
        "value4": "TEXT NOT NULL",
        "timestamp": "INTEGER NOT NULL"
    }
}

# Filter Configuration
FILTER_CONFIG = {
    "speed": {
        "enabled": False,
        "min": 0,
        "max": 100
    },
    "rssi": {
        "enabled": False,
        "min": -100,
        "max": 0
    },
    "tag_range": {
        "enabled": False,
        "min": 0,
        "max": 999999999
    },
    "duplicate_window": 10_000_000  # microseconds (10 seconds)
}

# Sound Configuration
SOUND_CONFIG = {
    "enabled": True,
    "frequency": 1000,
    "duration": 800
}

# Legacy constants for backward compatibility
INTERNET_GPS_URL = GPS_CONFIG["internet"]["url"]
BAUD_RATE_QUE = GPS_CONFIG["external"]["baud_rate"]
BAUD_RATE_DON = 9600
GPS_PORT = GPS_CONFIG["external"]["port"]
RFID_CARD_READER = RFID_CONFIG["reader_ip"]
SOUND_FREQUENCY = SOUND_CONFIG["frequency"]
SOUND_DURATION = SOUND_CONFIG["duration"]