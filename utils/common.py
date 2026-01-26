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

import settings
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


def _is_port_available(port):
    """
    Check if a serial port is available (not in use by another process).
    Returns True if port is available, False otherwise.
    Uses a non-intrusive check that doesn't leave the port locked.
    """
    try:
        # First check if port file exists (Linux) or is accessible
        if platform.system() == 'Linux':
            if not os.path.exists(port):
                return False
        
        # Try to open the port briefly to check if it's available
        # Use a very short timeout to minimize impact
        test_ser = None
        try:
            test_ser = serial.Serial(port=port, baudrate=115200, timeout=0.05)
            # If we can open it, it's available
            return True
        except (serial.SerialException, OSError, PermissionError) as e:
            # Port is busy or not accessible
            if "busy" in str(e).lower() or "resource busy" in str(e).lower() or "[Errno 16]" in str(e):
                return False
            # For other errors, assume port might be available (let the actual open handle it)
            return True
        finally:
            # Always close the test connection if it was opened
            if test_ser is not None and test_ser.is_open:
                try:
                    test_ser.close()
                    time.sleep(0.05)  # Small delay to ensure port is fully released
                except Exception:
                    pass
    except Exception:
        # If any error occurs during check, assume port might be available
        # (let the actual operation handle the error)
        return True

def enable_gps_at_command():
    """
    Send AT+QGPS=1 command to ttyUSB2 to enable GPS.
    Works the same way as gps_enable.py script - mimics minicom action.
    """
    port = '/dev/ttyUSB2'
    baud_rate = 115200
    command = 'AT+QGPS=1'
    wait_time = 2.0
    ser = None
    
    try:
        # Check if port is available before trying to open it
        if not _is_port_available(port):
            logger.warning(f"Port {port} is busy, waiting 0.5 seconds before retry...")
            time.sleep(0.5)
            if not _is_port_available(port):
                logger.warning(f"Port {port} is still busy, skipping GPS enable command")
                return False
        
        logger.info(f"Opening serial connection to {port} at {baud_rate} baud...")
        ser = serial.Serial(
            port=port,
            baudrate=baud_rate,
            timeout=1,
            write_timeout=1,
            rtscts=True,
            dsrdtr=True
        )
        logger.info(f"✓ Connected to {port}")
        
        # Clear any existing data in buffer (like gps_enable.py)
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        
        # Prepare command (add carriage return like minicom)
        at_command = command if command.endswith('\r') else command + '\r'
        command_bytes = at_command.encode('utf-8')
        
        # Send command
        logger.info(f"Sending command: {command}")
        ser.write(command_bytes)
        logger.info(f"✓ Command sent: {command_bytes}")
        
        # Wait for GPS to initialize
        if wait_time > 0:
            logger.debug(f"Waiting {wait_time} seconds for GPS to initialize...")
            time.sleep(wait_time)
        
        # Read response (optional, but helpful for debugging)
        logger.debug("Reading response...")
        response_lines = []
        start_time = time.time()
        timeout = 2.0  # 2 second timeout for reading
        
        while (time.time() - start_time) < timeout:
            if ser.in_waiting > 0:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                if line:
                    response_lines.append(line)
                    logger.debug(f"  Response: {line}")
            else:
                time.sleep(0.1)
        
        if response_lines:
            logger.info(f"✓ Received {len(response_lines)} response line(s)")
        else:
            logger.debug("No response received (this may be normal)")
        
        logger.info("GPS enable command completed successfully")
        
        return True
        
    except serial.SerialException as e:
        logger.warning(f"Failed to send AT+QGPS=1 command to {port}: {e}")
        return False
    except PermissionError as e:
        logger.warning(f"Permission denied accessing {port}: {e}")
        return False
    except (OSError, Exception) as e:
        logger.warning(f"Failed to send AT+QGPS=1 command to {port}: {e}")
        return False
    finally:
        # Always close the port, even if an exception occurred
        if ser is not None and ser.is_open:
            try:
                ser.close()
                logger.info(f"✓ Connection closed for {port}")
                time.sleep(0.1)  # Small delay to ensure port is fully released
            except Exception as e:
                logger.debug(f"Error closing port {port}: {e}")

def pre_config_gps():
    """
    Pre-configure GPS by sending AT+QGPS=1 to all available ports.
    Works the same way as enable_gps_at_command() for each port.
    Returns the baud rate to use for GPS scanning.
    """
    serial_ports = [port.device for port in serial.tools.list_ports.comports()]
    logger.debug(f"Available ports: {serial_ports}")
    
    if platform.system() == 'Windows':
        return settings.GPS_CONFIG.get('baud_rate', settings.BAUD_RATE_DON) or settings.BAUD_RATE_DON
    
    # Get probe baud rate (default: 115200)
    try_rate = settings.GPS_CONFIG.get('probe_baud_rate', settings.GPS_CONFIG.get('baud_rate', settings.BAUD_RATE_DON)) if isinstance(settings.GPS_CONFIG, dict) else settings.BAUD_RATE_DON
    command = 'AT+QGPS=1'
    wait_time = 2.0
    
    logger.info("Attempting to enable GPS on all ports with AT+QGPS=1 command...")
    for port in serial_ports:
        ser = None
        try:
            # Check if port is available before trying to open it
            if not _is_port_available(port):
                logger.debug(f"Port {port} is busy, skipping...")
                continue
            
            logger.debug(f"Trying port: {port} at {try_rate} baud...")
            ser = serial.Serial(
                port=port,
                baudrate=try_rate,
                timeout=1,
                write_timeout=1,
                rtscts=True,
                dsrdtr=True
            )
            logger.debug(f"✓ Connected to {port}")
            
            # Clear any existing data in buffer (like enable_gps_at_command)
            ser.reset_input_buffer()
            ser.reset_output_buffer()
            
            # Prepare command (add carriage return like minicom)
            at_command = command if command.endswith('\r') else command + '\r'
            command_bytes = at_command.encode('utf-8')
            
            # Send command
            logger.debug(f"Sending command: {command} to {port}")
            ser.write(command_bytes)
            logger.debug(f"✓ Command sent to {port}: {command_bytes}")
            
            # Wait for GPS to initialize
            if wait_time > 0:
                logger.debug(f"Waiting {wait_time} seconds for GPS to initialize...")
                time.sleep(wait_time)
            
            # Read response (optional, but helpful for debugging)
            response_lines = []
            start_time = time.time()
            timeout = 1.0  # 1 second timeout for reading (shorter than enable_gps_at_command)
            
            while (time.time() - start_time) < timeout:
                if ser.in_waiting > 0:
                    line = ser.readline().decode('utf-8', errors='ignore').strip()
                    if line:
                        response_lines.append(line)
                        # logger.debug(f"  Response from {port}: {line}")
                else:
                    time.sleep(0.1)
            
            if response_lines:
                logger.debug(f"✓ Received {len(response_lines)} response line(s) from {port}")
            else:
                logger.debug(f"No response from {port} (this may be normal)")
            
            logger.info(f"✓ Successfully sent AT+QGPS=1 to {port}")
            
            return try_rate
            
        except serial.SerialException as e:
            logger.debug(f"Port {port} serial error: {e}")
            pass
        except PermissionError as e:
            logger.debug(f"Permission denied accessing {port}: {e}")
            pass
        except (OSError, Exception) as e:
            logger.debug(f"Port {port} error: {e}")
            pass
        finally:
            # Always close the port, even if an exception occurred
            if ser is not None and ser.is_open:
                try:
                    ser.close()
                    logger.debug(f"✓ Connection closed for {port}")
                    time.sleep(0.1)  # Small delay to ensure port is fully released
                except Exception as e:
                    logger.debug(f"Error closing port {port}: {e}")
    
    logger.debug("No port responded to AT command, using default baud rate")
    return settings.GPS_CONFIG.get('baud_rate', settings.BAUD_RATE_DON) or settings.BAUD_RATE_DON


def find_gps_port(baud_rate):
    serial_ports = [port.device for port in serial.tools.list_ports.comports()]
    logger.debug(f"Available ports:{serial_ports}")
    
    # Try each port multiple times to ensure we catch GPS data
    for port in serial_ports:
        # Check if port is available before trying to open it
        if not _is_port_available(port):
            logger.debug(f"Port {port} is busy, skipping...")
            continue
            
        try:
            with serial.Serial(port, baudrate=baud_rate, timeout=1, rtscts=True, dsrdtr=True) as ser:
                # Try multiple reads to catch GPS data
                for attempt in range(5):
                    buffer = ser.in_waiting
                    if buffer < 80:
                        time.sleep(0.2)  # Wait a bit longer for data
                    line = ser.readline().decode('utf-8', errors='ignore').strip()
                    logger.debug(f"Port {port} attempt {attempt + 1}: {line[:50]}...")  # Log first 50 chars
                    if line.startswith('$G'):
                        logger.info(f"GPS found on port: {port}")
                        return port
                logger.debug(f"No GPS data found on port {port} after 5 attempts")
        except (OSError, serial.SerialException) as e:
            logger.debug(f"Port {port} error: {e}")
            pass
        finally:
            # Small delay to ensure port is fully released
            time.sleep(0.1)
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


