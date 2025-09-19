import os
import platform
import socket
import subprocess
import threading
import time
import re
from datetime import datetime
from utils.logger import logger
from geopy.distance import geodesic
from geographiclib.geodesic import Geodesic
import serial
import serial.tools.list_ports
from settings import GPS_CONFIG, BAUD_RATE_QUE, BAUD_RATE_DON, GPS_PORT

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

def pre_config_gps():
    serial_ports = [port.device for port in serial.tools.list_ports.comports()]
    logger.debug(f"Available ports:{serial_ports}")
    if platform.system() == 'Windows':
        return BAUD_RATE_DON
    for port in serial_ports:
        try:
            with serial.Serial(port, baudrate=BAUD_RATE_QUE, timeout=1, rtscts=True, dsrdtr=True) as serw:
                serw.write('AT+QGPS=1\r'.encode())
                logger.debug(f"AT-{port}")
                serw.close()
                time.sleep(2)
                return BAUD_RATE_QUE
        except (OSError, serial.SerialException):
            pass  # Ignore if the port can't be opened
    return BAUD_RATE_DON

def find_gps_port(baud_rate):
    serial_ports = [port.device for port in serial.tools.list_ports.comports()]
    logger.debug(f"Available ports:{serial_ports}")
    for port in serial_ports:
        try:
            # Open each port
            with serial.Serial(port, baudrate=baud_rate, timeout=1, rtscts=True, dsrdtr=True) as ser:
                buffer = ser.in_waiting
                if buffer < 80:
                    time.sleep(.5)
                # Try reading from the port
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                # logger.debug(f"{line}, {port}")
                if line.startswith('$G'):
                    logger.info(f"GPS found on port: {port}")
                    return port
        except (OSError, serial.SerialException):
            pass  # Ignore if the port can't be opened

    logger.info("No GPS port found")
    return None

def send_at_command(command, delay=1):
    ser = serial.Serial(port=GPS_PORT, baudrate=115200, timeout=1)
    """Send AT command and read the response"""
    ser.write((command + "\r\n").encode())  # Send command
    time.sleep(delay)  # Wait for response
    response = ser.read(ser.inWaiting()).decode(errors='ignore')  # Read response
    return response

def convert_to_decimal(coord, direction, is_latitude):
    try:
        sign = -1 if direction in ['S', 'W'] else 1
        if is_latitude:
            if len(coord) < 4:
                raise ValueError("Invalid latitude coordinate format")
            degrees = int(coord[:2])
            minutes = float(coord[2:])
        else:
            if len(coord) < 5:
                raise ValueError("Invalid longitude coordinate format")
            degrees = int(coord[:3])
            minutes = float(coord[3:])
        decimal_coord = sign * (degrees + minutes / 60)
        return decimal_coord
    except ValueError:
        # logger.error(f"Error converting coordinate: {e}")
        return 0
def extract_from_gps(gps_data):
    if gps_data == {}:
        return 0, 0
    try:
        # Extract and convert latitude and longitude
        latitude = convert_to_decimal(gps_data['lat'], gps_data['lat_dir'], is_latitude=True)
        longitude = convert_to_decimal(gps_data['lon'], gps_data['lon_dir'], is_latitude=False)
        return latitude, longitude
    except KeyError:
        # logger.error(f"Missing key in GPS data: {e}")
        return 0, 0
    except ValueError:
        # logger.error(f"Error: {e}")
        return 0, 0
def calculate_speed_bearing(lat1, lon1, time1, lat2, lon2, time2):
    # Calculate the distance in meters
    distance = geodesic((lat1, lon1), (lat2, lon2)).meters
    # Calculate the time difference in seconds
    time_diff = (time2 - time1) / 1_000_000
    # Calculate speed in m/s
    if time_diff > 0:
        speed = distance / time_diff
    else:
        speed = 0  # If time difference is 0, speed is undefined or considered 0
    return speed * 2.23694, Geodesic.WGS84.Inverse(lat1, lon1, lat2, lon2)['azi1']


def get_date_from_utc(timestamp_microseconds):
    """Convert UTC timestamp in microseconds to formatted date string."""
    timestamp_seconds = timestamp_microseconds / 1_000_000
    utc_datetime = datetime.utcfromtimestamp(timestamp_seconds)
    formatted_date = "{}/{}/{} {}:{}:{} {}".format(
        utc_datetime.month,
        utc_datetime.day,
        utc_datetime.year,
        utc_datetime.hour % 12 or 12,
        f"{utc_datetime.minute:02}",
        f"{utc_datetime.second:02}",
        "AM" if utc_datetime.hour < 12 else "PM"
    )
    return formatted_date


def is_ipv4_address(ip):
    """Validate IPv4 address format."""
    ipv4_regex = re.compile(r'^(?:\d{1,3}\.){3}\d{1,3}$')
    if ipv4_regex.match(ip):
        parts = ip.split('.')
        if all(0 <= int(part) <= 255 for part in parts):
            return True
    return False


def validate_gps_data(gps_data):
    """Validate GPS data for reasonable ranges."""
    if not isinstance(gps_data, dict):
        return False
    
    # Check for required fields
    required_fields = ['lat', 'lon']
    if not all(field in gps_data for field in required_fields):
        return False
    
    try:
        lat = float(gps_data['lat'])
        lon = float(gps_data['lon'])
        
        # Validate coordinate ranges
        if not (-90 <= lat <= 90):
            return False
        if not (-180 <= lon <= 180):
            return False
            
        return True
    except (ValueError, TypeError):
        return False


def format_coordinates(lat, lon, precision=None):
    """Format coordinates with specified precision."""
    if precision is None:
        precision = GPS_CONFIG["data_processing"]["coordinate_precision"]
    
    if lat == 0 and lon == 0:
        return "N/A"
    
    return f"{lat:.{precision}f}, {lon:.{precision}f}"


def format_speed(speed, unit="mph"):
    """Format speed with appropriate precision."""
    if speed == 0:
        return "0.0"
    
    if unit == "mph":
        return f"{speed:.1f}"
    elif unit == "kmh":
        return f"{speed * 1.60934:.1f}"
    else:
        return f"{speed:.2f}"


def format_bearing(bearing):
    """Format bearing with appropriate precision."""
    if bearing == 0:
        return "0°"
    
    return f"{bearing:.0f}°"


def get_gps_age_seconds(timestamp_microseconds):
    """Calculate age of GPS data in seconds."""
    current_time = int(time.time() * 1_000_000)
    age_microseconds = current_time - timestamp_microseconds
    return age_microseconds / 1_000_000


def is_gps_data_stale(timestamp_microseconds, max_age_seconds=None):
    """Check if GPS data is stale."""
    if max_age_seconds is None:
        max_age_seconds = GPS_CONFIG["data_processing"]["max_age_seconds"]
    
    age = get_gps_age_seconds(timestamp_microseconds)
    return age > max_age_seconds


def extract_gps_from_internet_data(data):
    """Extract GPS coordinates from internet geolocation API response."""
    if not isinstance(data, dict):
        return 0, 0
    
    try:
        if data.get("status") == "success":
            lat = float(data.get("lat", 0))
            lon = float(data.get("lon", 0))
            return lat, lon
    except (ValueError, TypeError):
        pass
    
    return 0, 0


def get_gps_signal_quality(gps_data):
    """Determine GPS signal quality based on available data."""
    if not isinstance(gps_data, dict):
        return 0
    
    # For internet GPS, we assume good quality if we have valid coordinates
    if 'lat' in gps_data and 'lon' in gps_data:
        if validate_gps_data(gps_data):
            return 3  # Good quality
    
    # For external GPS, check for additional quality indicators
    if 'fix_quality' in gps_data:
        return int(gps_data['fix_quality'])
    
    return 0  # No signal


def convert_speed_units(speed, from_unit="knots", to_unit="mph"):
    """Convert speed between different units."""
    if speed == 0:
        return 0
    
    # Convert to m/s first
    if from_unit == "knots":
        speed_ms = speed * 0.514444
    elif from_unit == "mph":
        speed_ms = speed * 0.44704
    elif from_unit == "kmh":
        speed_ms = speed * 0.277778
    else:  # assume m/s
        speed_ms = speed
    
    # Convert to target unit
    if to_unit == "knots":
        return speed_ms / 0.514444
    elif to_unit == "mph":
        return speed_ms / 0.44704
    elif to_unit == "kmh":
        return speed_ms / 0.277778
    else:  # m/s
        return speed_ms