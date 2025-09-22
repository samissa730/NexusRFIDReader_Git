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
from settings import GPS_CONFIG
from utils.common import send_at_command, find_gps_port, pre_config_gps, convert_to_decimal, calculate_speed_bearing
from utils.logger import logger


class GPS(QThread):

    # Signals for UI updates
    sig_status_changed = Signal(str)  # GPS connection status text
    sig_data_updated = Signal(dict)    # New GPS data available
    sig_error_occurred = Signal(str)  # Error message

    def __init__(self, gps_type: str = None, current_status: str = None):
        super().__init__()
        self._ser = None
        self._gps_type = gps_type or GPS_CONFIG["type"]
        self._b_stop = threading.Event()
        self._data = {}
        self._sdata = [0, 0]  # [speed, bearing]
        self._current_status = current_status or "Disconnected"
        self._external_connected = False
        self._internal_connected = False
        self._last_update_time = 0
        self._cache_data = {}
        self._cache_timestamp = 0
        
        # Configuration from settings
        self._config = GPS_CONFIG
        self._internet_config = self._config["internet"]
        self._external_config = self._config["external"]
        self._processing_config = self._config["processing"]
        
        # Initialize based on GPS type (only if no explicit status provided)
        if current_status is None:
            if self._gps_type == "external":
                self._baud_rate = pre_config_gps()
                self._port = find_gps_port(self._baud_rate)
                if self._port:
                    self._external_connected = True
                    self._current_status = "External(Connected)"
                else:
                    self._external_connected = False
                    self._current_status = "Disconnected"
            else:
                # Start disconnected; will switch to Internal(Connected) when data arrives
                self._current_status = "Disconnected"

    def run(self):
        """Background task: continuous GPS data processing based on type."""
        logger.info(f"Starting GPS thread for type: {self._gps_type}")
        
        if self._gps_type in ("internet", "internal"):
            self._run_internet_gps()
        elif self._gps_type == "external":
            self._run_external_gps()
        else:
            logger.error(f"Unsupported GPS type: {self._gps_type}")
            self.sig_error_occurred.emit(f"Unsupported GPS type: {self._gps_type}")

    def _run_internet_gps(self):
        """IP-based geolocation service with caching."""
        while not self._b_stop.is_set():
            try:
                # Check cache first
                current_time = time.time()
                if (self._cache_data and 
                    current_time - self._cache_timestamp < self._internet_config["cache_ttl"]):
                    self._data = self._cache_data.copy()
                    self.sig_data_updated.emit(self._data)
                    self._last_update_time = current_time
                else:
                    # Fetch new data
                    success = self._fetch_internet_gps()
                    if success:
                        self._cache_data = self._data.copy()
                        self._cache_timestamp = current_time
                        self.sig_data_updated.emit(self._data)
                        self._last_update_time = current_time
                        if self._current_status != "Internal(Connected)":
                            self._internal_connected = True
                            self._current_status = "Internal(Connected)"
                            self.sig_status_changed.emit(self._current_status)
                    else:
                        if self._current_status != "Disconnected":
                            self._internal_connected = False
                            self._current_status = "Disconnected"
                            self.sig_status_changed.emit(self._current_status)
                
                # Wait for next update
                time.sleep(self._processing_config["update_interval"])
                
            except Exception as e:
                logger.error(f"Internet GPS error: {e}")
                self.sig_error_occurred.emit(f"Internet GPS error: {e}")
                time.sleep(5)  # Wait before retry

    def _run_external_gps(self):
        """External GPS with fallback to internal (IP-based) when unavailable."""
        next_external_retry_time = 0
        external_retry_interval = 3
        while not self._b_stop.is_set():
            try:
                now = time.time()
                if (self._ser is None) and (now >= next_external_retry_time):
                    self._ser = self._connect_serial()
                    next_external_retry_time = now + external_retry_interval

                if self._ser is not None:
                    # External path
                    self._read_serial_data()
                    if self._data:
                        self.sig_data_updated.emit(self._data)
                        self._last_update_time = time.time()
                        if self._current_status != "External(Connected)":
                            self._external_connected = True
                            self._internal_connected = False
                            self._current_status = "External(Connected)"
                            self.sig_status_changed.emit(self._current_status)
                else:
                    # Fallback to internal (internet geolocation)
                    current_time = time.time()
                    if (self._cache_data and 
                        current_time - self._cache_timestamp < self._internet_config["cache_ttl"]):
                        # Use cached data
                        self._data = self._cache_data.copy()
                        self.sig_data_updated.emit(self._data)
                        self._last_update_time = current_time
                        status = "Internal(Connected), External(Disconnected)"
                        if self._current_status != status:
                            self._external_connected = False
                            self._internal_connected = True
                            self._current_status = status
                            self.sig_status_changed.emit(self._current_status)
                    else:
                        success = self._fetch_internet_gps()
                        if success:
                            self._cache_data = self._data.copy()
                            self._cache_timestamp = current_time
                            self.sig_data_updated.emit(self._data)
                            self._last_update_time = time.time()
                            status = "Internal(Connected), External(Disconnected)"
                            if self._current_status != status:
                                self._external_connected = False
                                self._internal_connected = True
                                self._current_status = status
                                self.sig_status_changed.emit(self._current_status)
                        else:
                            # Both unavailable
                            status = "Disconnected"
                            if self._current_status != status:
                                self._external_connected = False
                                self._internal_connected = False
                                self._current_status = status
                                self.sig_status_changed.emit(self._current_status)

                time.sleep(self._processing_config["update_interval"])            

            except Exception as e:
                logger.error(f"External GPS error: {e}")
                self._data = {}
                self._sdata = [0, 0]
                self._ser = None
                time.sleep(1)
                # status updates handled by outer loop
                time.sleep(1)

    def _connect_serial(self) -> Optional[serial.Serial]:
        """Connect to external GPS device."""
        if not self._port:
            return None
            
        try:
            ser = serial.Serial(
                port=self._port,
                baudrate=self._baud_rate,
                timeout=self._external_config["timeout"],
                write_timeout=self._external_config["write_timeout"],
                bytesize=self._external_config["data_bits"],
                stopbits=self._external_config["stop_bits"],
                parity=self._external_config["parity"]
            )
            logger.info(f"Connected to GPS on port: {self._port}")
            return ser
        except serial.SerialException as e:
            logger.error(f"Failed to connect to GPS port {self._port}: {e}")
            return None

    def _read_serial_data(self):
        """Parse incoming GPS data from serial port."""
        if not self._ser or not self._ser.is_open:
            return
            
        try:
            buffer = self._ser.in_waiting
            if buffer < 80:
                time.sleep(0.2)
            
            line = self._ser.readline().decode('utf-8', errors='ignore').strip()
            
            # Check for supported NMEA sentences
            nmea_sentences = self._processing_config["nmea_sentences"]
            if any(line.startswith(sentence) for sentence in nmea_sentences):
                self._parse_nmea_data(line)
                
        except Exception as e:
            logger.error(f"Error reading serial data: {e}")
            raise

    def _parse_nmea_data(self, line: str):
        """Parse NMEA sentence and extract GPS data."""
        try:
            msg = pynmea2.parse(line)
            
            # Extract all fields
            for field in msg.fields:
                label, attr = field[:2]
                value = getattr(msg, attr)
                self._data[attr] = value
            
            # Extract speed and course
            if hasattr(msg, 'spd_over_grnd') and hasattr(msg, 'true_course'):
                speed_knots = msg.spd_over_grnd if msg.spd_over_grnd is not None else 0
                course_degrees = msg.true_course if msg.true_course is not None else 0
                
                # Convert speed based on configured unit (m/s as requested)
                speed_unit = self._processing_config["speed_unit"]
                if speed_unit == "mph":
                    speed = speed_knots * 1.15078
                elif speed_unit == "kmh":
                    speed = speed_knots * 1.852
                else:  # mps
                    speed = speed_knots * 0.514444
                
                self._sdata = [speed, course_degrees]
                
        except pynmea2.ParseError as e:
            logger.error(f"NMEA parse error: {e}")
            self._data = {}
            self._sdata = [0, 0]

    def _fetch_internet_gps(self) -> bool:
        """Fetch coarse location from IP-based service."""
        retry_strategy = Retry(
            total=self._internet_config["retry_count"],
            backoff_factor=self._internet_config["retry_backoff"],
            status_forcelist=self._internet_config["retry_status_codes"],
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST"],
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session = requests.Session()
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        # Set user agent
        headers = {"User-Agent": self._internet_config["user_agent"]}

        try:
            response = session.get(
                self._internet_config["url"], 
                timeout=self._internet_config["timeout"],
                headers=headers
            )
            response.raise_for_status()
            data = response.json()
            
            if isinstance(data, dict) and data.get("status") == "success":
                self._data = data
                return True
                
        except Exception as e:
            logger.error(f"Internet GPS fetch error: {e}")

        self._data = {}
        return False

    def set_GPS_port(self):
        """Configure GPS port for external GPS."""
        if self._gps_type == "external" and self._current_status == "N/A":
            try:
                response = send_at_command("AT+QGPS=1")
                logger.debug(f"GPS Port Response: {response}")
                
                # Check GPS status
                status = send_at_command("AT+QGPS?")
                logger.debug(f"GPS Port Status: {status}")
                self._current_status = "External(Connected)"

            except Exception as e:
                logger.error(f"GPS Port Error: {e}")
                self._current_status = "Disconnected"

    def stop(self):
        """Stop GPS thread and cleanup resources."""
        logger.info("Stopping GPS thread")
        self._b_stop.set()
        self.wait(1)
        self._close_serial()

    def _close_serial(self):
        """Close serial connection."""
        if self._ser and self._ser.is_open:
            self._ser.close()
            logger.info("Serial connection closed.")
        self._ser = None

    def get_data(self) -> Dict[str, Any]:
        """Get latest GPS data."""
        return self._data.copy()

    def get_sdata(self) -> list:
        """Get speed and bearing data."""
        return self._sdata.copy()

    def get_status(self) -> str:
        """Get current GPS status."""
        return self._current_status

    def get_coordinates(self) -> Tuple[float, float]:
        """Get current latitude and longitude."""
        if self._gps_type == "external" and self._data:
            try:
                lat = convert_to_decimal(self._data.get('lat', ''), 
                                       self._data.get('lat_dir', 'N'), 
                                       is_latitude=True)
                lon = convert_to_decimal(self._data.get('lon', ''), 
                                       self._data.get('lon_dir', 'E'), 
                                       is_latitude=False)
                return lat, lon
            except Exception:
                pass
        elif self._gps_type in ("internet", "internal") and self._data:
            return self._data.get('lat', 0), self._data.get('lon', 0)
        
        return 0, 0

    def get_speed_bearing(self) -> Tuple[float, float]:
        """Get current speed and bearing."""
        if self._sdata:
            return self._sdata[0], self._sdata[1]
        return 0, 0

    def is_data_stale(self) -> bool:
        """Check if GPS data is stale based on configured threshold."""
        if not self._last_update_time:
            return True
        
        stale_threshold = self._config["dashboard"]["stale_data_threshold"]
        return (time.time() - self._last_update_time) > stale_threshold

    def get_signal_quality(self) -> Dict[str, Any]:
        """Get GPS signal quality information."""
        quality = {
            "satellites": 0,
            "accuracy": 0,
            "fix_quality": 0,
            "status": "No Fix"
        }
        
        if self._gps_type == "external" and self._data:
            quality["satellites"] = self._data.get('num_sats', 0)
            quality["fix_quality"] = self._data.get('fix_quality', 0)
            quality["accuracy"] = self._data.get('horizontal_dil', 0)
            
            if quality["fix_quality"] > 0:
                quality["status"] = "Fix"
            else:
                quality["status"] = "No Fix"
                
        elif self._gps_type == "internet" and self._data:
            quality["status"] = "Internet Fix"
            quality["accuracy"] = 1000  # Internet GPS is less accurate
            
        return quality