import threading
import time

import serial
import pynmea2

from PySide6.QtCore import Signal, QThread

from settings import GPS_CONFIG
from utils.logger import logger


class GPS(QThread):

    sig_msg = Signal(bool)

    def __init__(self, port, baud_rate, current_status=False):
        super().__init__()
        self.port = port
        self.baud_rate = baud_rate
        self._ser = None
        self._b_stop = threading.Event()
        self._data = {}
        self._sdata = [0, 0]
        self._last_data_timestamp = None  # Track when GPS data was last received
        self.connectivity = current_status
        # Thread-safe GPS data storage with timestamp
        self._data_lock = threading.Lock()
        self._gps_data_with_timestamp = {
            'data': {},
            'sdata': [0, 0],
            'timestamp': None
        }

    def _connect(self):
        try:
            _ser = serial.Serial(port=self.port, baudrate=self.baud_rate, timeout=1, write_timeout=1)
            if self.connectivity is False:
                self.connectivity = True
                self.sig_msg.emit(True)
            return _ser
        except serial.SerialException:
            if self.connectivity is True:
                self.connectivity = False
                self.sig_msg.emit(False)
            return None

    def read_serial_data(self):
        buffer = self._ser.in_waiting
        if buffer < 80:
            time.sleep(.2)
        line = self._ser.readline().decode('utf-8', errors='ignore').strip()
        if line.startswith('$GPRMC') or line.startswith('$GNRMC'):
            try:
                msg = pynmea2.parse(line)
                # Capture timestamp at the exact moment GPS data is parsed
                current_timestamp = int(time.time() * 1_000_000)
                
                # Parse GPS data
                data = {}
                for field in msg.fields:
                    label, attr = field[:2]
                    value = getattr(msg, attr)
                    data[attr] = value
                speed_knots = msg.spd_over_grnd if msg.spd_over_grnd is not None else 0
                course_degrees = msg.true_course if msg.true_course is not None else 0
                sdata = [speed_knots * 1.15078, course_degrees]
                
                # Update data atomically with timestamp
                with self._data_lock:
                    self._data = data
                    self._sdata = sdata
                    self._last_data_timestamp = current_timestamp
                    # Store synchronized GPS data with timestamp
                    self._gps_data_with_timestamp = {
                        'data': data.copy(),
                        'sdata': sdata.copy(),
                        'timestamp': current_timestamp
                    }
                # logger.debug(f"GPS data parsed: lat={data.get('lat', 'N/A')}, lon={data.get('lon', 'N/A')}, speed={speed_knots}, timestamp={current_timestamp}")
                pass
            except pynmea2.ParseError as e:
                logger.debug(f"GPS parse error: {e}")
                with self._data_lock:
                    self._data = {}
                    self._sdata = [0, 0]
        elif line.startswith('$G'):
            # Log other GPS sentences for debugging
            # logger.debug(f"GPS sentence: {line[:50]}...")
            pass

    def run(self):
        self._ser = self._connect()
        while self._ser is None and not self._b_stop.is_set():
            self._ser = self._connect()

        while not self._b_stop.is_set():
            if self._ser is None:
                self._ser = self._connect()
                time.sleep(.1)
            else:
                try:
                    self.read_serial_data()
                    if self.connectivity is False:
                        self.connectivity = True
                        self.sig_msg.emit(True)
                except Exception:
                    self._data = {}
                    self._sdata = [0, 0]
                    self._ser = None
                    if self.connectivity is True:
                        self.connectivity = False
                        self.sig_msg.emit(False)

    def stop(self):
        self._b_stop.set()
        self.wait(1)
        self._close_serial()

    def _close_serial(self):
        if self._ser and self._ser.is_open:
            self._ser.close()
        self._ser = None

    def is_alive(self):
        return not self._b_stop.is_set()

    def get_data(self):
        with self._data_lock:
            return self._data.copy()

    def get_sdata(self):
        with self._data_lock:
            return self._sdata.copy()

    def get_data_timestamp(self):
        """Get the timestamp when GPS data was last received"""
        with self._data_lock:
            return self._last_data_timestamp

    def get_synchronized_data(self, tag_timestamp):
        """
        Get GPS data that matches the tag timestamp exactly.
        Returns (data, sdata, timestamp) tuple if GPS data timestamp matches tag timestamp,
        or None if timestamps don't match (within 100ms tolerance).
        """
        with self._data_lock:
            gps_timestamp = self._gps_data_with_timestamp['timestamp']
            if gps_timestamp is None:
                return None
            
            # Calculate time difference in microseconds
            time_diff = abs(gps_timestamp - tag_timestamp)
            # Allow maximum 100ms (100,000 microseconds) difference for synchronization
            max_time_diff = 100_000  # 100ms in microseconds
            
            if time_diff <= max_time_diff:
                # GPS data is synchronized with tag timestamp
                return (
                    self._gps_data_with_timestamp['data'].copy(),
                    self._gps_data_with_timestamp['sdata'].copy(),
                    gps_timestamp
                )
            else:
                # GPS data is too old or too new - not synchronized
                logger.debug(f"GPS-RFID timestamp mismatch: GPS={gps_timestamp}, RFID={tag_timestamp}, diff={time_diff/1000:.1f}ms")
                return None


