import threading
import time
import serial
import pynmea2

from PySide6.QtCore import Signal, QThread
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from settings import GPS_CONFIG
from utils.common import (
    send_at_command, extract_gps_from_internet_data, validate_gps_data,
    format_coordinates, format_speed, format_bearing, get_gps_age_seconds,
    is_gps_data_stale, convert_speed_units, get_date_from_utc
)
from utils.logger import logger


class GPS(QThread):
    """Enhanced GPS class supporting both internet and external GPS sources."""

    sig_msg = Signal(bool)  # Connection status signal
    sig_data = Signal(dict)  # GPS data signal

    def __init__(self, gps_type=None, current_status="N/A"):
        super().__init__()
        self._ser = None
        self._gps_type = gps_type or GPS_CONFIG["gps_type"]
        self._b_stop = threading.Event()
        self._data = {}
        self._sdata = [0, 0]  # [speed, bearing]
        self._current_status = current_status
        self._last_update_time = 0
        self._connectivity = False
        
        # Load configuration based on GPS type
        if self._gps_type == "internet":
            self._config = GPS_CONFIG["internet_gps"]
        elif self._gps_type == "external":
            self._config = GPS_CONFIG["external_gps"]
        elif self._gps_type == "cellular":
            self._config = GPS_CONFIG["cellular_gps"]
        else:
            logger.error(f"Unsupported GPS type: {self._gps_type}")
            self._gps_type = "internet"
            self._config = GPS_CONFIG["internet_gps"]

    def run(self):
        """Main GPS processing loop."""
        logger.info(f"Starting GPS thread with type: {self._gps_type}")
        
        if self._gps_type == "internet":
            self._run_internet_gps()
        elif self._gps_type == "external":
            self._run_external_gps()
        elif self._gps_type == "cellular":
            self._run_cellular_gps()
        else:
            logger.error(f"Unsupported GPS type: {self._gps_type}")

    def stop(self):
        """Stop GPS processing."""
        logger.info("Stopping GPS thread")
        self._b_stop.set()
        self.wait(1)
        self._close_serial()

    def _close_serial(self):
        """Close serial connection if open."""
        if self._ser and self._ser.is_open:
            self._ser.close()
            logger.info("Serial connection closed.")
        self._ser = None

    def get_data(self):
        """Get latest GPS data."""
        return self._data

    def get_sdata(self):
        """Get latest speed and bearing data."""
        return self._sdata

    def get_status(self):
        """Get current GPS status."""
        return self._current_status

    def is_connected(self):
        """Check if GPS is connected."""
        return self._connectivity

    def _run_internet_gps(self):
        """Run internet GPS processing loop."""
        logger.info("Starting internet GPS processing")
        
        while not self._b_stop.is_set():
            success = self._fetch_internet_gps()
            self.sig_msg.emit(success)
            
            if success:
                self._last_update_time = int(time.time() * 1_000_000)
                self.sig_data.emit(self._data)
            
            # Wait for next update
            time.sleep(self._config["update_interval"])

    def _run_external_gps(self):
        """Run external GPS processing loop."""
        logger.info("Starting external GPS processing")
        
        # Try to connect to GPS device
        self._ser = self._connect_external_gps()
        
        while not self._b_stop.is_set():
            if self._ser is None:
                # Try to reconnect
                self._ser = self._connect_external_gps()
                if self._ser is None:
                    time.sleep(self._config["reconnect_delay"])
                    continue
            
            try:
                self._read_external_gps_data()
                if not self._connectivity:
                    self._connectivity = True
                    self.sig_msg.emit(True)
            except Exception as e:
                logger.error(f"External GPS error: {e}")
                self._data = {}
                self._sdata = [0, 0]
                self._ser = None
                if self._connectivity:
                    self._connectivity = False
                    self.sig_msg.emit(False)

    def _run_cellular_gps(self):
        """Run cellular GPS processing loop."""
        logger.info("Starting cellular GPS processing")
        
        # Enable cellular GPS
        self._enable_cellular_gps()
        
        while not self._b_stop.is_set():
            try:
                # Check cellular GPS status
                status = self._check_cellular_gps_status()
                if status:
                    self._current_status = "Connected"
                    if not self._connectivity:
                        self._connectivity = True
                        self.sig_msg.emit(True)
                else:
                    self._current_status = "Disconnected"
                    if self._connectivity:
                        self._connectivity = False
                        self.sig_msg.emit(False)
                
                time.sleep(5)  # Check every 5 seconds
            except Exception as e:
                logger.error(f"Cellular GPS error: {e}")
                self._current_status = "Error"

    def _connect_external_gps(self):
        """Connect to external GPS device."""
        try:
            ser = serial.Serial(
                port=self._config["port"],
                baudrate=self._config["baud_rate"],
                timeout=self._config["timeout"],
                write_timeout=self._config["write_timeout"]
            )
            logger.info(f"Connected to external GPS on {self._config['port']}")
            return ser
        except serial.SerialException as e:
            logger.error(f"Failed to connect to external GPS: {e}")
            return None

    def _read_external_gps_data(self):
        """Read and parse external GPS data."""
        buffer = self._ser.in_waiting
        if buffer < self._config["buffer_size"]:
            time.sleep(self._config["read_delay"])
        
        line = self._ser.readline().decode('utf-8', errors='ignore').strip()
        
        # Check if it's a supported NMEA sentence
        nmea_sentences = self._config["nmea_sentences"]
        if any(line.startswith(sentence) for sentence in nmea_sentences):
            try:
                msg = pynmea2.parse(line)
                
                # Extract GPS data
                gps_data = {}
                for field in msg.fields:
                    label, attr = field[:2]
                    value = getattr(msg, attr)
                    gps_data[attr] = value
                
                # Validate and store data
                if validate_gps_data(gps_data):
                    self._data = gps_data
                    self._last_update_time = int(time.time() * 1_000_000)
                    
                    # Extract speed and bearing
                    speed_knots = getattr(msg, 'spd_over_grnd', 0) or 0
                    course_degrees = getattr(msg, 'true_course', 0) or 0
                    
                    # Convert speed to mph
                    speed_mph = convert_speed_units(speed_knots, "knots", "mph")
                    self._sdata = [speed_mph, course_degrees]
                    
                    # Emit data signal
                    self.sig_data.emit(self._data)
                    
            except pynmea2.ParseError as e:
                logger.debug(f"NMEA parse error: {e}")
                self._data = {}
                self._sdata = [0, 0]

    def _fetch_internet_gps(self) -> bool:
        """Fetch GPS data from internet geolocation service."""
        retry_strategy = Retry(
            total=self._config["retry_count"],
            backoff_factor=self._config["retry_delay"],
            status_forcelist=self._config["retry_status_codes"],
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST"],
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session = requests.Session()
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        try:
            response = session.get(
                self._config["url"], 
                timeout=self._config["timeout"]
            )
            response.raise_for_status()
            data = response.json()
            
            if isinstance(data, dict) and data.get("status") == "success":
                self._data = data
                self._last_update_time = int(time.time() * 1_000_000)
                return True
                
        except Exception as e:
            logger.debug(f"Internet GPS fetch error: {e}")

        self._data = {}
        return False

    def _enable_cellular_gps(self):
        """Enable cellular GPS using AT commands."""
        try:
            response = send_at_command(
                GPS_CONFIG["cellular_gps"]["at_commands"]["enable"],
                GPS_CONFIG["cellular_gps"]["command_delay"]
            )
            logger.debug(f"Cellular GPS enable response: {response}")
        except Exception as e:
            logger.error(f"Failed to enable cellular GPS: {e}")

    def _check_cellular_gps_status(self):
        """Check cellular GPS status."""
        try:
            status = send_at_command(
                GPS_CONFIG["cellular_gps"]["at_commands"]["status"],
                GPS_CONFIG["cellular_gps"]["command_delay"]
            )
            logger.debug(f"Cellular GPS status: {status}")
            return "OK" in status or "1" in status
        except Exception as e:
            logger.error(f"Failed to check cellular GPS status: {e}")
            return False

    def get_formatted_data(self):
        """Get formatted GPS data for display."""
        if not self._data:
            return {
                "coordinates": "N/A",
                "speed": "0.0 mph",
                "bearing": "0°",
                "status": self._current_status,
                "last_update": "N/A"
            }
        
        # Extract coordinates
        if self._gps_type == "internet":
            lat, lon = extract_gps_from_internet_data(self._data)
        else:
            lat, lon = self._extract_coordinates_from_nmea()
        
        # Format data
        coordinates = format_coordinates(lat, lon)
        speed = format_speed(self._sdata[0], "mph") + " mph"
        bearing = format_bearing(self._sdata[1])
        
        # Format last update time
        if self._last_update_time > 0:
            last_update = get_date_from_utc(self._last_update_time)
        else:
            last_update = "N/A"
        
        return {
            "coordinates": coordinates,
            "speed": speed,
            "bearing": bearing,
            "status": self._current_status,
            "last_update": last_update
        }

    def _extract_coordinates_from_nmea(self):
        """Extract coordinates from NMEA data."""
        try:
            if 'lat' in self._data and 'lon' in self._data:
                lat = float(self._data['lat'])
                lon = float(self._data['lon'])
                return lat, lon
        except (ValueError, TypeError):
            pass
        return 0, 0