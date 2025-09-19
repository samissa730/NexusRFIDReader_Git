import os
import platform
import socket
import subprocess
import threading
import time
from utils.logger import logger
from geopy.distance import geodesic
from geographiclib.geodesic import Geodesic
import serial
import serial.tools.list_ports
from settings import BAUD_RATE_QUE, BAUD_RATE_DON, GPS_PORT

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
    """
    Convert GPS coordinates from degrees/minutes format to decimal degrees.
    User Story 13172: Convert to speed, latitude, longitude
    
    Args:
        coord: Coordinate string (e.g., "3745.1234")
        direction: Direction indicator ('N', 'S', 'E', 'W')
        is_latitude: True for latitude, False for longitude
        
    Returns:
        float: Decimal degrees coordinate
    """
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
    except ValueError as e:
        logger.error(f"Error converting coordinate: {e}")
        return 0
    except Exception as e:
        logger.error(f"Unexpected error in coordinate conversion: {e}")
        return 0


def extract_from_gps(gps_data):
    """
    Extract latitude and longitude from GPS data dictionary.
    User Story 13172: Convert to speed, latitude, longitude
    
    Args:
        gps_data: Dictionary containing GPS data
        
    Returns:
        tuple: (latitude, longitude) in decimal degrees
    """
    if not gps_data or gps_data == {}:
        return 0, 0
    try:
        # Extract and convert latitude and longitude
        latitude = convert_to_decimal(gps_data['lat'], gps_data['lat_dir'], is_latitude=True)
        longitude = convert_to_decimal(gps_data['lon'], gps_data['lon_dir'], is_latitude=False)
        return latitude, longitude
    except KeyError as e:
        logger.error(f"Missing key in GPS data: {e}")
        return 0, 0
    except ValueError as e:
        logger.error(f"Error extracting GPS data: {e}")
        return 0, 0
    except Exception as e:
        logger.error(f"Unexpected error extracting GPS data: {e}")
        return 0, 0


def calculate_speed_bearing(lat1, lon1, time1, lat2, lon2, time2):
    """
    Calculate speed and bearing between two GPS points.
    User Story 13172: Convert to speed, latitude, longitude
    
    Args:
        lat1, lon1: First GPS coordinates
        time1: First timestamp (microseconds)
        lat2, lon2: Second GPS coordinates  
        time2: Second timestamp (microseconds)
        
    Returns:
        tuple: (speed_mph, bearing_degrees)
    """
    try:
        # Calculate the distance in meters
        distance = geodesic((lat1, lon1), (lat2, lon2)).meters
        
        # Calculate the time difference in seconds
        time_diff = (time2 - time1) / 1_000_000
        
        # Calculate speed in m/s, then convert to mph
        if time_diff > 0:
            speed_ms = distance / time_diff
            speed_mph = speed_ms * 2.23694  # Convert m/s to mph
        else:
            speed_mph = 0  # If time difference is 0, speed is undefined or considered 0
        
        # Calculate bearing using geodesic calculation
        bearing = Geodesic.WGS84.Inverse(lat1, lon1, lat2, lon2)['azi1']
        
        return speed_mph, bearing
        
    except Exception as e:
        logger.error(f"Error calculating speed and bearing: {e}")
        return 0, 0


def validate_gps_coordinates(latitude, longitude):
    """
    Validate GPS coordinates are within valid ranges.
    
    Args:
        latitude: Latitude in decimal degrees
        longitude: Longitude in decimal degrees
        
    Returns:
        bool: True if coordinates are valid
    """
    try:
        # Check latitude range (-90 to 90)
        if not (-90 <= latitude <= 90):
            return False
        
        # Check longitude range (-180 to 180)
        if not (-180 <= longitude <= 180):
            return False
        
        return True
    except (TypeError, ValueError):
        return False


def format_coordinates(latitude, longitude, precision=6):
    """
    Format GPS coordinates for display.
    
    Args:
        latitude: Latitude in decimal degrees
        longitude: Longitude in decimal degrees
        precision: Number of decimal places
        
    Returns:
        str: Formatted coordinate string
    """
    try:
        return f"{latitude:.{precision}f}, {longitude:.{precision}f}"
    except (TypeError, ValueError):
        return "0.000000, 0.000000"


def get_distance_between_points(lat1, lon1, lat2, lon2):
    """
    Calculate distance between two GPS points in meters.
    
    Args:
        lat1, lon1: First GPS coordinates
        lat2, lon2: Second GPS coordinates
        
    Returns:
        float: Distance in meters
    """
    try:
        return geodesic((lat1, lon1), (lat2, lon2)).meters
    except Exception as e:
        logger.error(f"Error calculating distance: {e}")
        return 0


def is_gps_data_valid(gps_data):
    """
    Check if GPS data contains valid location information.
    
    Args:
        gps_data: GPS data dictionary
        
    Returns:
        bool: True if GPS data is valid
    """
    try:
        if not gps_data or not isinstance(gps_data, dict):
            return False
        
        # Check for required fields
        required_fields = ['latitude', 'longitude']
        if not all(field in gps_data for field in required_fields):
            return False
        
        # Validate coordinates
        lat = gps_data.get('latitude', 0)
        lon = gps_data.get('longitude', 0)
        
        return validate_gps_coordinates(lat, lon)
        
    except Exception as e:
        logger.error(f"Error validating GPS data: {e}")
        return False