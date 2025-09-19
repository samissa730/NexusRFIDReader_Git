import threading
import time
import serial
import pynmea2
from datetime import datetime
from typing import Dict, Optional, Tuple, Any

from PySide6.QtCore import Signal, QThread
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from settings import GPS_CONFIG, GPS_DATA_CONFIG
from utils.common import send_at_command, convert_to_decimal, calculate_speed_bearing
from utils.logger import logger


class GPS(QThread):
    """
    Production-ready GPS handler supporting both internet and external GPS sources.
    Implements all user story requirements for GPS functionality.
    """

    # Signals for UI updates
    sig_status_changed = Signal(bool)  # GPS connection status
    sig_data_updated = Signal(dict)    # New GPS data available
    sig_error_occurred = Signal(str)   # Error message

    def __init__(self, gps_type: str = None, current_status: str = "N/A"):
        super().__init__()
        self._gps_type = gps_type or GPS_CONFIG["type"]
        self._current_status = current_status
        self._b_stop = threading.Event()
        
        # GPS data storage
        self._data = {}
        self._last_update_time = None
        self._connection_status = False
        
        # Serial connection for external GPS
        self._ser = None
        
        # Configuration from settings
        self._config = GPS_CONFIG
        self._data_config = GPS_DATA_CONFIG
        
        # Performance tracking
        self._success_count = 0
        self._error_count = 0
        self._last_error = None

    def run(self):
        """
        Main GPS processing loop - User Story 13170: GPS Data Listener Initialization
        """
        logger.info(f"Starting GPS listener for type: {self._gps_type}")
        
        if self._gps_type == "internet":
            self._run_internet_gps()
        elif self._gps_type == "external":
            self._run_external_gps()
        else:
            logger.error(f"Unsupported GPS type: {self._gps_type}")
            self.sig_error_occurred.emit(f"Unsupported GPS type: {self._gps_type}")

    def _run_internet_gps(self):
        """
        Internet GPS processing loop - User Story 13047: IP-based Geolocation
        """
        while not self._b_stop.is_set():
            try:
                success = self._fetch_internet_gps()
                if success:
                    self._success_count += 1
                    self._update_connection_status(True)
                    self.sig_data_updated.emit(self._data.copy())
                else:
                    self._error_count += 1
                    self._update_connection_status(False)
                
                # Wait before next update
                time.sleep(self._config["update_interval_seconds"])
                
            except Exception as e:
                logger.error(f"Internet GPS error: {e}")
                self._error_count += 1
                self._last_error = str(e)
                self.sig_error_occurred.emit(str(e))
                self._update_connection_status(False)
                time.sleep(self._config["update_interval_seconds"])

    def _run_external_gps(self):
        """
        External GPS processing loop - User Story 13048: External GPS Support
        """
        # Initialize external GPS connection
        self._ser = self._connect_external_gps()
        
        while not self._b_stop.is_set():
            try:
                if self._ser is None:
                    # Attempt reconnection
                    self._ser = self._connect_external_gps()
                    if self._ser is None:
                        time.sleep(1)
                        continue
                
                # Read and process GPS data
                success = self._read_external_gps_data()
                if success:
                    self._success_count += 1
                    self._update_connection_status(True)
                    self.sig_data_updated.emit(self._data.copy())
                else:
                    self._error_count += 1
                    self._update_connection_status(False)
                
                time.sleep(0.1)  # Small delay for external GPS
                
            except Exception as e:
                logger.error(f"External GPS error: {e}")
                self._error_count += 1
                self._last_error = str(e)
                self.sig_error_occurred.emit(str(e))
                self._ser = None
                self._update_connection_status(False)
                time.sleep(1)

    def _connect_external_gps(self) -> Optional[serial.Serial]:
        """
        Connect to external GPS device - User Story 13048: Device Detection
        """
        try:
            config = self._config["external"]
            ser = serial.Serial(
                port=config["port"],
                baudrate=config["baud_rate"],
                timeout=config["timeout"],
                write_timeout=config["write_timeout"]
            )
            logger.info(f"Connected to external GPS on {config['port']}")
            return ser
        except serial.SerialException as e:
            logger.warning(f"Failed to connect to external GPS: {e}")
            return None

    def _read_external_gps_data(self) -> bool:
        """
        Read and parse external GPS data - User Story 13171: Parse GPS Data
        """
        try:
            if not self._ser or not self._ser.is_open:
                return False
            
            # Wait for sufficient data
            buffer = self._ser.in_waiting
            if buffer < 80:
                time.sleep(0.2)
            
            # Read NMEA sentence
            line = self._ser.readline().decode('utf-8', errors='ignore').strip()
            
            # Parse supported NMEA sentences
            if any(line.startswith(sentence) for sentence in self._data_config["nmea_sentences"]):
                return self._parse_nmea_sentence(line)
            
            return False
            
        except Exception as e:
            logger.error(f"Error reading external GPS data: {e}")
            return False

    def _parse_nmea_sentence(self, line: str) -> bool:
        """
        Parse NMEA sentence - User Story 13171: Parse GPS Data
        """
        try:
            msg = pynmea2.parse(line)
            
            # Extract GPS data based on sentence type
            if line.startswith(('$GPRMC', '$GNRMC')):
                # Recommended Minimum sentence
                self._data = {
                    'timestamp': msg.timestamp,
                    'lat': msg.lat,
                    'lat_dir': msg.lat_dir,
                    'lon': msg.lon,
                    'lon_dir': msg.lon_dir,
                    'speed_knots': msg.spd_over_grnd or 0,
                    'course': msg.true_course or 0,
                    'fix_valid': msg.data_valid,
                    'sentence_type': 'RMC'
                }
            elif line.startswith(('$GPGGA', '$GNGGA')):
                # Global Positioning System Fix Data
                self._data = {
                    'timestamp': msg.timestamp,
                    'lat': msg.lat,
                    'lat_dir': msg.lat_dir,
                    'lon': msg.lon,
                    'lon_dir': msg.lon_dir,
                    'altitude': msg.altitude or 0,
                    'satellites': msg.num_sats or 0,
                    'hdop': msg.horizontal_dil or 0,
                    'fix_quality': msg.gps_qual or 0,
                    'sentence_type': 'GGA'
                }
            
            # Convert coordinates to decimal degrees - User Story 13172: Convert Coordinates
            if 'lat' in self._data and 'lat_dir' in self._data:
                self._data['latitude'] = convert_to_decimal(
                    self._data['lat'], 
                    self._data['lat_dir'], 
                    is_latitude=True
                )
            if 'lon' in self._data and 'lon_dir' in self._data:
                self._data['longitude'] = convert_to_decimal(
                    self._data['lon'], 
                    self._data['lon_dir'], 
                    is_latitude=False
                )
            
            # Convert speed - User Story 13172: Convert Speed
            if 'speed_knots' in self._data:
                self._data['speed_mph'] = self._data['speed_knots'] * 1.15078
            
            self._last_update_time = datetime.now()
            return True
            
        except pynmea2.ParseError as e:
            logger.warning(f"NMEA parse error: {e}")
            return False
        except Exception as e:
            logger.error(f"Error parsing NMEA sentence: {e}")
            return False

    def _fetch_internet_gps(self) -> bool:
        """
        Fetch GPS data from internet service - User Story 13047: IP Geolocation
        """
        config = self._config["internet"]
        
        # Configure retry strategy
        retry_strategy = Retry(
            total=self._config["retry_count"],
            backoff_factor=self._config["retry_backoff_factor"],
            status_forcelist=self._config["retry_status_codes"],
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST"],
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session = requests.Session()
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        try:
            headers = {
                'User-Agent': config["user_agent"]
            }
            
            response = session.get(
                config["url"], 
                timeout=config["timeout"],
                headers=headers
            )
            response.raise_for_status()
            
            data = response.json()
            
            if isinstance(data, dict) and data.get("status") == "success":
                # Store raw data
                self._data = data.copy()
                
                # Add processed fields
                self._data['latitude'] = data.get('lat', 0)
                self._data['longitude'] = data.get('lon', 0)
                self._data['country'] = data.get('country', 'Unknown')
                self._data['city'] = data.get('city', 'Unknown')
                self._data['sentence_type'] = 'INTERNET'
                
                self._last_update_time = datetime.now()
                return True
            else:
                logger.warning(f"Internet GPS API returned status: {data.get('status', 'unknown')}")
                return False
                
        except requests.exceptions.Timeout:
            logger.warning("Internet GPS request timed out")
            return False
        except requests.exceptions.RequestException as e:
            logger.warning(f"Internet GPS request failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error in internet GPS: {e}")
            return False
        finally:
            session.close()

    def _update_connection_status(self, connected: bool):
        """
        Update connection status and emit signal - User Story 13173: Dashboard Updates
        """
        if self._connection_status != connected:
            self._connection_status = connected
            self.sig_status_changed.emit(connected)
            logger.info(f"GPS connection status changed: {'Connected' if connected else 'Disconnected'}")

    def stop(self):
        """Stop GPS processing gracefully"""
        logger.info("Stopping GPS processing")
        self._b_stop.set()
        self.wait(1)
        self._close_serial()

    def _close_serial(self):
        """Close serial connection for external GPS"""
        if self._ser and self._ser.is_open:
            self._ser.close()
            logger.info("Serial connection closed")
        self._ser = None

    def get_data(self) -> Dict[str, Any]:
        """
        Get latest GPS data - User Story 13173: Dashboard Updates
        """
        return self._data.copy()

    def get_status(self) -> Dict[str, Any]:
        """
        Get GPS status information for dashboard
        """
        return {
            'connected': self._connection_status,
            'type': self._gps_type,
            'last_update': self._last_update_time,
            'success_count': self._success_count,
            'error_count': self._error_count,
            'last_error': self._last_error,
            'data_age_seconds': (datetime.now() - self._last_update_time).total_seconds() 
                if self._last_update_time else None
        }

    def set_GPS_port(self):
        """
        Configure external GPS port - User Story 13048: External GPS Configuration
        """
        if self._gps_type == "external" and self._current_status == "N/A":
            try:
                config = self._config["external"]
                
                # Enable GPS
                response = send_at_command(config["at_commands"]["enable"])
                logger.debug(f"GPS Enable Response: {response}")
                
                # Check GPS status
                status = send_at_command(config["at_commands"]["status"])
                logger.debug(f"GPS Status Response: {status}")
                
                self._current_status = "Connected"
                logger.info("External GPS port configured successfully")
                
            except Exception as e:
                logger.error(f"GPS port configuration error: {e}")
                self._current_status = "Error"
                self.sig_error_occurred.emit(f"GPS port error: {e}")

    def is_data_fresh(self, max_age_seconds: int = None) -> bool:
        """
        Check if GPS data is fresh enough to use
        """
        if not self._last_update_time:
            return False
        
        max_age = max_age_seconds or self._data_config["max_age_seconds"]
        age = (datetime.now() - self._last_update_time).total_seconds()
        return age <= max_age

    def get_coordinates(self) -> Tuple[float, float]:
        """
        Get current coordinates as (latitude, longitude)
        """
        return (
            self._data.get('latitude', 0),
            self._data.get('longitude', 0)
        )

    def get_speed_bearing(self) -> Tuple[float, float]:
        """
        Get current speed and bearing
        """
        return (
            self._data.get('speed_mph', 0),
            self._data.get('course', 0)
        )