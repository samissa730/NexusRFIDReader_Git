import re
import time
import uuid
import platform
import subprocess
import os
from datetime import datetime

from geopy.distance import geodesic
from geographiclib.geodesic import Geodesic

import serial
import serial.tools.list_ports

from settings import BAUD_RATE_DON, GPS_CONFIG
from utils.logger import logger


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
        return 0


def extract_from_gps(gps_data):
    if gps_data == {}:
        return 0, 0
    try:
        latitude = convert_to_decimal(gps_data['lat'], gps_data['lat_dir'], is_latitude=True)
        longitude = convert_to_decimal(gps_data['lon'], gps_data['lon_dir'], is_latitude=False)
        return latitude, longitude
    except KeyError:
        return 0, 0
    except ValueError:
        return 0, 0


def get_date_from_utc(timestamp_microseconds):
    timestamp_seconds = timestamp_microseconds / 1_000_000
    utc_datetime = datetime.utcfromtimestamp(timestamp_seconds)
    formatted_date = "{}/{:02}/{:02} {:02}:{:02}:{:02}".format(
        utc_datetime.year,
        utc_datetime.month,
        utc_datetime.day,
        utc_datetime.hour,
        utc_datetime.minute,
        utc_datetime.second,
    )
    return formatted_date


def calculate_speed_bearing(lat1, lon1, time1, lat2, lon2, time2):
    distance = geodesic((lat1, lon1), (lat2, lon2)).meters
    time_diff = (time2 - time1) / 1_000_000
    if time_diff > 0:
        speed = distance / time_diff
    else:
        speed = 0
    return speed * 2.23694, Geodesic.WGS84.Inverse(lat1, lon1, lat2, lon2)['azi1']


def is_ipv4_address(ip):
    ipv4_regex = re.compile(r'^(?:\d{1,3}\.){3}\d{1,3}$')
    if ipv4_regex.match(ip):
        parts = ip.split('.')
        if all(0 <= int(part) <= 255 for part in parts):
            return True
    return False


def get_mac_address():
    mac_address = hex(uuid.getnode())
    mac_address = mac_address[2:]
    formatted_mac_address = ':'.join(mac_address[i:i + 2] for i in range(0, len(mac_address), 2)).upper()
    return formatted_mac_address


def enable_gps_at_command():
    """Send AT+QGPS=1 command to ttyUSB2 to enable GPS"""
    try:
        with serial.Serial('/dev/ttyUSB2', baudrate=115200, timeout=1, rtscts=True, dsrdtr=True) as ser:
            ser.write('AT+QGPS=1\r'.encode())
            logger.info("Sent AT+QGPS=1 command to ttyUSB2")
            ser.close()
            time.sleep(2)  # Give GPS time to initialize
            return True
    except (OSError, serial.SerialException) as e:
        logger.warning(f"Failed to send AT+QGPS=1 command to ttyUSB2: {e}")
        return False

def pre_config_gps():
    serial_ports = [port.device for port in serial.tools.list_ports.comports()]
    logger.debug(f"Available ports:{serial_ports}")
    if platform.system() == 'Windows':
        return GPS_CONFIG.get('baud_rate', BAUD_RATE_DON) or BAUD_RATE_DON
    try_rate = GPS_CONFIG.get('probe_baud_rate', GPS_CONFIG.get('baud_rate', BAUD_RATE_DON)) if isinstance(GPS_CONFIG, dict) else BAUD_RATE_DON
    for port in serial_ports:
        try:
            with serial.Serial(port, baudrate=try_rate, timeout=1, rtscts=True, dsrdtr=True) as serw:
                serw.write('AT+QGPS=1\r'.encode())
                logger.debug(f"AT-{port}")
                serw.close()
                time.sleep(2)
                return try_rate
        except (OSError, serial.SerialException):
            pass
    return GPS_CONFIG.get('baud_rate', BAUD_RATE_DON) or BAUD_RATE_DON


def find_gps_port(baud_rate):
    serial_ports = [port.device for port in serial.tools.list_ports.comports()]
    logger.debug(f"Available ports:{serial_ports}")
    for port in serial_ports:
        try:
            with serial.Serial(port, baudrate=baud_rate, timeout=0.1, rtscts=True, dsrdtr=True) as ser:
                buffer = ser.in_waiting
                if buffer < 80:
                    time.sleep(0.1)  # Reduced from 0.5 to 0.1 seconds
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                if line.startswith('$G'):
                    logger.info(f"GPS found on port: {port}")
                    return port
        except (OSError, serial.SerialException):
            pass
    logger.info("No GPS port found")
    return None


def find_smallest_available_id(used_ids):
    smallest_available_id = 1
    for record in used_ids:
        current_id = record[0]
        if current_id == smallest_available_id:
            smallest_available_id += 1
        else:
            break
    return smallest_available_id


def get_processor_id():
    """
    Get the processor ID for both Windows and Raspberry Pi systems.
    Returns the full processor ID as a string.
    """
    try:
        if platform.system() == 'Windows':
            # For Windows, use wmic to get processor ID
            result = subprocess.run(['wmic', 'cpu', 'get', 'ProcessorId'], 
                                 capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                # Clean up the output - remove extra whitespace and carriage returns
                output = result.stdout.replace('\r', '').strip()
                lines = [line.strip() for line in output.split('\n') if line.strip()]
                
                # Find the line with the actual processor ID (not the header)
                for line in lines:
                    if line and line != 'ProcessorId' and len(line) > 8:  # Processor ID should be longer than 8 chars
                        # logger.info(f"Found processor ID: {line}")
                        return line
                        
        elif platform.system() == 'Linux':
            # For Raspberry Pi, read the serial number from /proc/cpuinfo
            if os.path.exists('/proc/cpuinfo'):
                with open('/proc/cpuinfo', 'r') as f:
                    content = f.read()
                    for line in content.split('\n'):
                        if line.startswith('Serial'):
                            serial = line.split(':')[1].strip()
                            if serial and serial != '0000000000000000':  # Avoid default/empty serial
                                # logger.info(f"Found Raspberry Pi serial: {serial}")
                                return serial
    except Exception as e:
        logger.warning(f"Failed to get processor ID: {e}")
    
    # Fallback to MAC address if processor ID cannot be obtained
    logger.info("Using MAC address as fallback for device ID")
    return get_mac_address()


