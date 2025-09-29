import os
import platform
import socket
import subprocess
import threading
import time
import re
from datetime import datetime
from typing import Tuple, Optional, Dict, Any
from geopy.distance import geodesic
from geographiclib.geodesic import Geodesic

from utils.logger import logger
import serial
import serial.tools.list_ports
from settings import GPS_CONFIG

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
        return 9600  # BAUD_RATE_DON equivalent
    for port in serial_ports:
        try:
            baud_rate = GPS_CONFIG["external"]["baud_rate"]
            with serial.Serial(port, baudrate=baud_rate, timeout=1, rtscts=True, dsrdtr=True) as serw:
                serw.write('AT+QGPS=1\r'.encode())
                logger.debug(f"AT-{port}")
                serw.close()
                time.sleep(2)
                return baud_rate
        except (OSError, serial.SerialException):
            pass  # Ignore if the port can't be opened
    return 9600  # BAUD_RATE_DON equivalent

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

def convert_to_decimal(coord: str, direction: str, is_latitude: bool = True) -> float:
    """
    Convert GPS coordinates to decimal degrees.
    Args:
        coord: Coordinate string (e.g., "3342.1234")
        direction: Direction indicator (N, S, E, W)
        is_latitude: True for latitude, False for longitude
    Returns:
        Decimal degrees coordinate
    """
    try:
        # Validate input parameters
        if not coord or not isinstance(coord, str):
            return 0.0
            
        if not direction or direction not in ['N', 'S', 'E', 'W']:
            return 0.0
            
        # Clean the coordinate string
        coord = coord.strip()
        if not coord:
            return 0.0
            
        sign = -1 if direction in ['S', 'W'] else 1
        
        if is_latitude:
            if len(coord) < 4:
                return 0.0
            degrees = int(coord[:2])
            minutes = float(coord[2:])
        else:
            if len(coord) < 5:
                return 0.0
            degrees = int(coord[:3])
            minutes = float(coord[3:])
            
        decimal_coord = sign * (degrees + minutes / 60)
        logger.debug(f"Converted {coord} {direction} to {decimal_coord}")
        return decimal_coord
        
    except ValueError as e:
        logger.error(f"Error converting coordinate '{coord}' {direction}: {e}")
        return 0.0
    except Exception as e:
        logger.error(f"Unexpected error converting coordinate '{coord}' {direction}: {e}")
        return 0.0

def extract_from_gps(gps_data: Dict[str, Any]) -> Tuple[float, float]:
    """
    Extract latitude and longitude from GPS data.
    Args:
        gps_data: GPS data dictionary
    Returns:
        Tuple of (latitude, longitude) in decimal degrees
    """
    if not gps_data:
        logger.debug("No GPS data provided")
        return 0.0, 0.0
        
    # Check if required keys exist and have values
    lat = gps_data.get('lat', '')
    lon = gps_data.get('lon', '')
    lat_dir = gps_data.get('lat_dir', 'N')
    lon_dir = gps_data.get('lon_dir', 'E')
    
    if not lat or not lon:
        return 0.0, 0.0
        
    try:
        # Extract and convert latitude and longitude
        latitude = convert_to_decimal(
            str(lat), 
            str(lat_dir), 
            is_latitude=True
        )
        longitude = convert_to_decimal(
            str(lon), 
            str(lon_dir), 
            is_latitude=False
        )
        return latitude, longitude
        
    except KeyError as e:
        logger.error(f"Missing key in GPS data: {e}")
        return 0.0, 0.0
    except ValueError as e:
        logger.error(f"Error extracting GPS coordinates: {e}")
        return 0.0, 0.0

def calculate_speed_bearing(lat1: float, lon1: float, time1: int, 
                          lat2: float, lon2: float, time2: int) -> Tuple[float, float]:
    """
    Calculate speed and bearing between two GPS points.
    Args:
        lat1, lon1: First GPS coordinates
        time1: First timestamp in microseconds
        lat2, lon2: Second GPS coordinates  
        time2: Second timestamp in microsecond
    Returns:
        Tuple of (speed_mps, bearing_degrees) - using m/s as requested
    """
    try:
        # Calculate distance in meters
        distance = geodesic((lat1, lon1), (lat2, lon2)).meters
        
        # Calculate time difference in seconds
        time_diff = (time2 - time1) / 1_000_000
        
        # Calculate speed in m/s (keeping in m/s as requested)
        if time_diff > 0:
            speed_mps = distance / time_diff
        else:
            speed_mps = 0.0
            
        # Calculate bearing using geodesic calculations
        bearing = Geodesic.WGS84.Inverse(lat1, lon1, lat2, lon2)['azi1']
        
        return speed_mps, bearing
        
    except Exception as e:
        logger.error(f"Error calculating speed and bearing: {e}")
        return 0.0, 0.0

def get_date_from_utc(timestamp_microseconds: int) -> str:
    """
    Convert UTC timestamp to formatted date string.
    Args:
        timestamp_microseconds: UTC timestamp in microseconds
    Returns:
        Formatted date string
    """
    try:
        timestamp_seconds = timestamp_microseconds / 1_000_000
        # Use utcfromtimestamp for compatibility with older Python versions
        utc_datetime = datetime.utcfromtimestamp(timestamp_seconds)
        
        # Format the datetime object as YYYY/MM/DD HH:MM:SS
        formatted_date = "{}/{}/{} {}:{}:{}".format(
            utc_datetime.year,
            f"{utc_datetime.month:02d}",
            f"{utc_datetime.day:02d}",
            f"{utc_datetime.hour:02d}",
            f"{utc_datetime.minute:02d}",
            f"{utc_datetime.second:02d}"
        )
        return formatted_date
        
    except Exception as e:
        logger.error(f"Error formatting date: {e}")
        return "N/A"

def validate_gps_coordinates(lat: float, lon: float) -> bool:
    """
    Validate GPS coordinates are within reasonable ranges.
    Args:
        lat: Latitude in decimal degrees
        lon: Longitude in decimal degree
    Returns:
        True if coordinates are valid, False otherwise
    """
    return (-90 <= lat <= 90) and (-180 <= lon <= 180)

def format_coordinates(lat: float, lon: float, precision: int = 4) -> str:
    """
    Format GPS coordinates for display
    Args:
        lat: Latitude in decimal degrees
        lon: Longitude in decimal degrees
        precision: Number of decimal places
    Returns:
        Formatted coordinate string
    """
    if not validate_gps_coordinates(lat, lon):
        return "N/A"
        
    return f"{lat:.{precision}f}, {lon:.{precision}f}"

def format_speed(speed: float, unit: str = "mps") -> str:
    """
    Format speed for display.
    Args:
        speed: Speed value
        unit: Speed unit (mph, kmh, mps)
    Returns:
        Formatted speed string
    """
    if unit == "mph":
        return f"{speed:.1f} mph"
    elif unit == "kmh":
        return f"{speed:.1f} km/h"
    elif unit == "mps":
        return f"{speed:.1f} m/s"
    else:
        return f"{speed:.1f}"

def format_bearing(bearing: float) -> str:
    """
    Format bearing for display with cardinal directions.
    Args:
        bearing: Bearing in degree
    Returns:
        Formatted bearing string with cardinal direction
    """
    if bearing < 0:
        bearing += 360
        
    directions = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                  "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    
    index = int((bearing + 11.25) / 22.5) % 16
    direction = directions[index]
    
    return f"{bearing:.0f}° {direction}"

def is_ipv4_address(ip: str) -> bool:
    """
    Validate IPv4 address format.    
    Args:
        ip: IP address string
    Returns:
        True if valid IPv4 address, False otherwise
    """
    ipv4_regex = re.compile(r'^(?:\d{1,3}\.){3}\d{1,3}$')
    if ipv4_regex.match(ip):
        parts = ip.split('.')
        return all(0 <= int(part) <= 255 for part in parts)
    return False

def send_at_command(command: str, delay: float = 1) -> str:
    """
    Send AT command to GPS module.
    Args:
        command: AT command to send
        delay: Delay before reading response
    Returns:
        Response from GPS module
    """
    try:
        at_port = GPS_CONFIG["external"]["at_command_port"]
        at_baud = GPS_CONFIG["external"]["at_command_baud"]
        
        ser = serial.Serial(port=at_port, baudrate=at_baud, timeout=1)
        ser.write((command + "\r\n").encode())
        time.sleep(delay)
        response = ser.read(ser.inWaiting()).decode(errors='ignore')
        ser.close()
        return response
        
    except Exception as e:
        logger.error(f"Error sending AT command: {e}")
        return ""