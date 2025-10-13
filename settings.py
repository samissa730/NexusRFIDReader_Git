import json
import os
import platform
# On Linux, prefer resolving the effective user's home directory via pwd to avoid
# relying on HOME when launched by systemd where HOME can be /root.
try:
    import pwd  # type: ignore
except Exception:
    pwd = None  # non-POSIX platforms

is_rpi = platform.system() == "Linux" and os.path.exists("/proc/device-tree/model")
is_win = platform.system() == "Windows"

if is_rpi:
    home_dir = None
    if pwd is not None:
        try:
            home_dir = pwd.getpwuid(os.getuid()).pw_dir
        except Exception:
            home_dir = None
    if not home_dir:
        home_dir = os.path.expanduser("~")
    ROOT_DIR = os.path.join(home_dir, ".nexusrfid")
elif is_win:
    ROOT_DIR = os.path.expanduser("~/Documents")
else:
    ROOT_DIR = os.path.expanduser("~/.nexusrfid")

os.makedirs(ROOT_DIR, exist_ok=True)

INIT_SCREEN = "overview"
APP_DIR = os.path.dirname(os.path.realpath(__file__))
CRASH_FILE = os.path.join(ROOT_DIR, "crash.dump")

# GPS Configuration - edit these values directly
GPS_CONFIG = {
    # use_external: use serial GPS (True) or internet (False)
    "use_external": True,
    # default baud rate and optional probe rate
    "baud_rate": 115200,
    "probe_baud_rate": 115200,
}

# RFID Configuration - edit these values directly
RFID_CONFIG = {
    "host": "169.254.10.1",
    "port": 5084,
    "report_every_n_tags": 1,
    "antennas": "1",
    "tx_power": 0,
    "tari": 0,
    "session": 1,
    "mode_identifier": None,
    "tag_population": 4,
    "impinj_search_mode": None,
    "impinj_reports": False,
}

# API Configuration - edit these values directly (token-based; no login UI)
API_CONFIG = {
    "login_url": "",  # optional, if you will use token refresh
    "health_url": "",
    "auth0_url": "https://dev-0m8cx6xlg7z8zy6j.us.auth0.com/oauth/token",
    "record_url": "http://dev-api-locate.nexusyms.com/api/sites/0198c311-4801-7445-b73a-3a7dce72c6f6/scans",
    "client_id": "enc:Aox9yhPiUr--4yjKyH27RGaV9Ca-Hm6SfLH5LbZObKw=",
    "client_secret": "enc:K5gX9RqiaKPVBSW7-DqdM2Ky3BehIGVmd8vtLqSOT9eIAGabLmtbnvrYNauPLsNh7eaVjZuevyBNYpsdAlu97w==",
    "audience": "https://nexus-locate-api",
    "email": "",      # optional, only if login_url used
    "password": "",   # optional, only if login_url used
    "token": "",      # set bearer token here if using token auth
    "user_name": "NexusUser",
    "spotter_id": "120",
    "site_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",  # siteId for new API format
    # intervals
    "record_interval_ms": 7000,
    "health_interval_ms": 15000,
}

# Data Storage Configuration - edit these values directly
DATABASE_CONFIG = {
    "use_db": True,
}

# Filter Configuration - edit these values directly
FILTER_CONFIG = {
    "speed": {
        "enabled": False,
        "min": 0,
        "max": 200,
    },
    "rssi": {
        "enabled": False,
        "min": -80,
        "max": 0,
    },
    "tag_range": {
        "enabled": False,
        "min": 0,
        "max": 999999999,
    },
}

BAUD_RATE_DON = 9600

INTERNET_LIMIT_TIME=10