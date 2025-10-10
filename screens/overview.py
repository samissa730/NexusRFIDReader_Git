from PySide6.QtCore import Qt, QTimer, QThread, Signal
from PySide6.QtWidgets import QTableWidgetItem

from screens.base import BaseScreen
from ui.screens.ui_overview import Ui_OverviewScreen
from utils.logger import logger
from utils.rfid import RFID
from utils.gps import GPS
from utils.common import extract_from_gps, get_date_from_utc, get_processor_id, calculate_speed_bearing
from settings import GPS_CONFIG, BAUD_RATE_DON
import serial
import serial.tools.list_ports
import requests
from utils.data_storage import DataStorage
from utils.api_client import ApiClient
from settings import API_CONFIG, FILTER_CONFIG, DATABASE_CONFIG
import time
from ping3 import ping


class GPSScanner(QThread):

    sig_found = Signal(str, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._b_stop = False
        self._ports = []
        self._port_idx = 0
        self._last_refresh_ms = 0
        # derive baud to try first
        self._baud = GPS_CONFIG.get('probe_baud_rate', GPS_CONFIG.get('baud_rate', BAUD_RATE_DON)) if isinstance(GPS_CONFIG, dict) else BAUD_RATE_DON

    def run(self):
        while not self._b_stop:
            try:
                # refresh port list every 10 seconds or when empty
                now = self.msecsSinceStartOfDay()
                if not self._ports or now - self._last_refresh_ms > 10000:
                    self._ports = [p.device for p in serial.tools.list_ports.comports()]
                    self._port_idx = 0
                    self._last_refresh_ms = now

                if not self._ports:
                    self.msleep(500)
                    continue

                # try one port per tick with very short timeouts
                port = self._ports[self._port_idx]
                self._port_idx = (self._port_idx + 1) % len(self._ports)
                try:
                    with serial.Serial(port, baudrate=self._baud, timeout=0.2, rtscts=True, dsrdtr=True) as ser:
                        # read a short line and check for NMEA prefix
                        line = ser.readline().decode('utf-8', errors='ignore').strip()
                        if line.startswith('$G'):
                            self.sig_found.emit(port, self._baud)
                            return
                except Exception:
                    # ignore and continue scanning next port
                    pass

                # small sleep to yield CPU/GIL
                self.msleep(100)
            except Exception:
                # unexpected error, avoid tight loop
                self.msleep(200)

    def stop(self):
        self._b_stop = True
        self.wait()


class InternetGPS(QThread):

    sig_msg = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._b_stop = False
        self._data = {}
        self._sdata = [0, 0]
        self._last_data_timestamp = None

    def run(self):
        while not self._b_stop:
            try:
                resp = requests.get('http://ip-api.com/json/', timeout=3)
                if resp.ok:
                    data = resp.json()
                    if data.get('status') == 'success':
                        cur_lat = data.get('lat') or 0
                        cur_lon = data.get('lon') or 0
                        if cur_lat and cur_lon:
                            if 'lat' in self._data and 'lon' in self._data:
                                speed, bearing = calculate_speed_bearing(
                                    self._data['lat'], self._data['lon'], self._last_data_timestamp or int(time.time()*1_000_000),
                                    cur_lat, cur_lon, int(time.time()*1_000_000)
                                )
                                self._sdata = [speed, bearing]
                            self._data = {'lat': cur_lat, 'lon': cur_lon}
                            self._last_data_timestamp = int(time.time()*1_000_000)
                            self.sig_msg.emit(True)
                        else:
                            self.sig_msg.emit(False)
                else:
                    self.sig_msg.emit(False)
            except Exception:
                self.sig_msg.emit(False)
            # poll every 4 seconds similar to POC
            for _ in range(40):
                if self._b_stop:
                    return
                self.msleep(100)

    def stop(self):
        self._b_stop = True
        self.wait()

    def isRunning(self):
        return not self._b_stop

    def get_data(self):
        lat = self._data.get('lat') or 0
        lon = self._data.get('lon') or 0
        return lat, lon

    def get_sdata(self):
        return self._sdata

    def get_data_timestamp(self):
        return self._last_data_timestamp

class OverviewScreen(BaseScreen):

    def __init__(self, app, **kwargs):
        super().__init__(app, **kwargs)
        self.ui = Ui_OverviewScreen()
        self.ui.setupUi(self)

        # Prepare table cells (non-editable)
        for row in range(self.ui.tableWidget.rowCount()):
            for column in range(self.ui.tableWidget.columnCount()):
                item = QTableWidgetItem("")
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable & ~Qt.ItemFlag.ItemIsEditable & ~Qt.ItemFlag.ItemIsEnabled)
                self.ui.tableWidget.setItem(row, column, item)

        # Set custom column widths
        # Columns: Time, Tag, Antenna, Position, Speed, Heading
        self.ui.tableWidget.setColumnWidth(0, 150)  # Time
        self.ui.tableWidget.setColumnWidth(1, 200)  # Tag
        self.ui.tableWidget.setColumnWidth(2, 80)   # Antenna
        self.ui.tableWidget.setColumnWidth(3, 190)  # Position
        self.ui.tableWidget.setColumnWidth(4, 70)   # Speed
        self.ui.tableWidget.setColumnWidth(5, 80)   # Heading

        # Init helpers and modules
        self.api = ApiClient()
        self.storage = DataStorage(DATABASE_CONFIG.get('use_db', False))
        
        # Set device ID using processor ID
        device_id = get_processor_id()
        self.ui.device_id.setText(device_id)
        self.ui.truck_number.setText(device_id)

        # GPS init
        self.last_lat = None
        self.last_lon = None
        self.last_utctime = None

        self.gps = None
        self.internet_gps = InternetGPS(self)
        self.internet_gps.sig_msg.connect(self._on_gps_status)
        self.internet_gps.start()
        self.gps_scanner = GPSScanner(self)
        self.gps_scanner.sig_found.connect(self._on_gps_port_found)
        self._start_gps_scanner()

        # RFID init
        self.rfid = RFID()
        self.rfid.sig_msg.connect(self._on_rfid_status)
        self.rfid.start()

        # Schedulers
        self.health_timer = QTimer(self)
        self.health_timer.timeout.connect(self._upload_health)
        self.health_timer.start(int(API_CONFIG.get('health_interval_ms', 15000)))

        self.upload_timer = QTimer(self)
        self.upload_timer.timeout.connect(self._upload_records)
        self.upload_timer.start(int(API_CONFIG.get('record_interval_ms', 7000)))

        # GPS display update timer
        self.gps_display_timer = QTimer(self)
        self.gps_display_timer.timeout.connect(self._update_gps_display)
        self.gps_display_timer.start(2000)  # Update every 2 seconds

        # Internet status check timer
        self.internet_timer = QTimer(self)
        self.internet_timer.timeout.connect(self._check_internet_status)
        self.internet_timer.start(5000)  # Check every 5 seconds
        self._check_internet_status()  # Initial check

    def on_leave(self):
        if self.gps and self.gps.isRunning():
            self.gps.stop()
        if hasattr(self, 'internet_gps') and self.internet_gps.isRunning():
            self.internet_gps.stop()
        if hasattr(self, 'gps_scanner') and self.gps_scanner.isRunning():
            self.gps_scanner.stop()
        if self.rfid and self.rfid.isRunning():
            self.rfid.stop()
        if hasattr(self, 'gps_display_timer'):
            self.gps_display_timer.stop()
        if hasattr(self, 'internet_timer'):
            self.internet_timer.stop()
        self.storage.close()

    def _set_gps_status(self, text, ok):
        self.ui.gps_connection_status.setStyleSheet("""color: #00ff00;""" if ok else """color: #ff0000;""")
        self.ui.gps_connection_status.setText(text)

    def _set_internet_status(self, text, ok):
        self.ui.internet_status.setStyleSheet("""color: #00ff00;""" if ok else """color: #ff0000;""")
        self.ui.internet_status.setText(text)

    def _on_gps_status(self, status):
        # Called by external GPS worker
        if status:
            self._set_gps_status("External GPS Connected", True)
        else:
            # External disconnected: update status and start external retry timer
            self._set_gps_status("External GPS Connected", True)
            self._start_gps_scanner()

    def _on_rfid_status(self, status):
        if status == 1:
            self.ui.rfid_connection_status.setStyleSheet("""color: #00ff00;""")
            self.ui.rfid_connection_status.setText("Connected")
        elif status == 2:
            self.ui.rfid_connection_status.setStyleSheet("""color: #ff0000;""")
            self.ui.rfid_connection_status.setText("Disconnected")
        elif status == 3:
            tag = self.rfid.tag_data[0]
            lat, lon, speed, bearing = 0, 0, 0, 0
            if self.gps:
                lat, lon = extract_from_gps(self.gps.get_data())
                if lat != 0 and lon != 0:
                    self.last_lat = lat
                    self.last_lon = lon
                    self.last_utctime = int(time.time() * 1_000_000)
                speed, bearing = self.gps.get_sdata()
            else:
                lat, lon, speed, bearing = 0, 0, 0, 0

            # round to 7 decimals for storage and display
            lat = round(lat, 7)
            lon = round(lon, 7)

            upload_flag = True
            # Apply filters from settings
            sp = FILTER_CONFIG.get('speed', {})
            if sp.get('enabled'):
                min_s = sp.get('min')
                max_s = sp.get('max')
                if min_s is not None and max_s is not None and (speed < min_s or speed > max_s):
                    upload_flag = False

            if upload_flag:
                rs = FILTER_CONFIG.get('rssi', {})
                if rs.get('enabled'):
                    min_r = rs.get('min')
                    max_r = rs.get('max')
                    if min_r is not None and max_r is not None and (tag['PeakRSSI'] < min_r or tag['PeakRSSI'] > max_r):
                        upload_flag = False

            if upload_flag:
                tr = FILTER_CONFIG.get('tag_range', {})
                if tr.get('enabled'):
                    min_t = tr.get('min')
                    max_t = tr.get('max')
                    try:
                        epc = int(tag['EPC-96'])
                        if min_t is not None and max_t is not None and (epc < min_t or epc > max_t):
                            upload_flag = False
                    except Exception:
                        upload_flag = False

            if upload_flag:
                if self.storage.use_db:
                    # Prevent duplicates within 10 seconds
                    assert self.storage.db_cursor
                    self.storage.db_cursor.execute('''
                        SELECT * FROM records
                        WHERE rfidTag = ?
                        AND ABS(timestamp - ?) < 10000000
                    ''', (tag['EPC-96'], tag['LastSeenTimestampUTC']))
                    rows = self.storage.db_cursor.fetchall()
                    if not rows:
                        # Prepare record list with explicit id
                        assert self.storage.db_cursor
                        self.storage.db_cursor.execute('SELECT id FROM records ORDER BY id ASC')
                        used_ids = self.storage.db_cursor.fetchall()
                        rec = [
                            calculate_next_id(used_ids), tag['EPC-96'], f"{tag['AntennaID']}", f"{tag['PeakRSSI']}",
                            lat, lon, speed, bearing, "-", self.api.user_name, tag['LastSeenTimestampUTC'],
                            "", "", "", "", "", "", "", ""
                        ]
                        self.storage.add_record(rec)
                else:
                    new_data = [True, tag['EPC-96'], f"{tag['AntennaID']}", f"{tag['PeakRSSI']}",
                                lat, lon, speed, bearing, "-", self.api.user_name, tag['LastSeenTimestampUTC'],
                                "", "", "", "", "", "", "", ""]
                    self.storage.add_record(new_data)

            # one-line debug for real-time processing
            logger.debug(f"TAG {tag['EPC-96']} ant={tag['AntennaID']} rssi={tag['PeakRSSI']} pos=({lat:.7f},{lon:.7f}) speed={speed} heading={bearing}")

            # UI updates
            self._refresh_table([get_date_from_utc(tag['LastSeenTimestampUTC']), tag['EPC-96'], f"{tag['AntennaID']}",
                                 f"{lat:.7f}".rstrip('0').rstrip('.') + ", " + f"{lon:.7f}".rstrip('0').rstrip('.'),
                                 f"{speed:.4f}".rstrip('0').rstrip('.'), f"{bearing}"])
            self.ui.last_rfid_read.setText(tag['EPC-96'])
            self.ui.last_rfid_time.setText(get_date_from_utc(tag['LastSeenTimestampUTC']))
            self.ui.last_gps_read.setText(f"{lat:.7f}, {lon:.7f}")
            # Use actual GPS timestamp when available; otherwise use RFID timestamp
            if self.gps and self.gps.isRunning():
                gps_timestamp = self.gps.get_data_timestamp()
                if gps_timestamp:
                    self.ui.last_gps_time.setText(get_date_from_utc(gps_timestamp))
                else:
                    self.ui.last_gps_time.setText(get_date_from_utc(tag['LastSeenTimestampUTC']))
            else:
                self.ui.last_gps_time.setText(get_date_from_utc(tag['LastSeenTimestampUTC']))

    def _refresh_table(self, new_data):
        for row in range(self.ui.tableWidget.rowCount() - 2, -1, -1):
            for column in range(self.ui.tableWidget.columnCount()):
                item = self.ui.tableWidget.item(row, column).text()
                self.ui.tableWidget.setItem(row + 1, column, QTableWidgetItem(item))
        for column in range(self.ui.tableWidget.columnCount()):
            self.ui.tableWidget.setItem(0, column, QTableWidgetItem(new_data[column]))

    def _start_gps_scanner(self):
        if hasattr(self, 'gps_scanner'):
            if self.gps_scanner.isRunning():
                return
            # Show that internal GPS (internet) is available while scanning external
            self._set_gps_status("External GPS Connected", True)
            self.gps_scanner = GPSScanner(self)
            self.gps_scanner.sig_found.connect(self._on_gps_port_found)
            self.gps_scanner.start()

    def _on_gps_port_found(self, port, baud):
        self._start_external_gps(port, baud)

    def _start_external_gps(self, port, baud):
        if self.gps and self.gps.isRunning():
            self.gps.stop()
        self.gps = GPS(port=port, baud_rate=baud)
        self.gps.sig_msg.connect(self._on_gps_status)
        self.gps.start()
        self._set_gps_status("External GPS Connected", True)

    def _upload_health(self):
        lat, lon = (0, 0)
        if self.gps:
            lat, lon = extract_from_gps(self.gps.get_data())
        gps_text = self.ui.gps_connection_status.text()
        self.api.upload_health(bool(self.rfid.connectivity), gps_text, lat, lon)

    def _update_gps_display(self):
        """Update GPS display fields with current GPS data"""
        if self.gps and self.gps.isRunning():
            # External GPS
            lat, lon = extract_from_gps(self.gps.get_data())
            if lat != 0 and lon != 0:
                speed, bearing = self.gps.get_sdata()
                # Use actual GPS data timestamp instead of current time
                gps_timestamp = self.gps.get_data_timestamp()
                if gps_timestamp:
                    self.ui.last_gps_read.setText(f"{lat:.7f}, {lon:.7f}")
                    self.ui.last_gps_time.setText(get_date_from_utc(gps_timestamp))
        elif hasattr(self, 'internet_gps') and self.internet_gps.isRunning():
            lat, lon = self.internet_gps.get_data()
            if lat != 0 and lon != 0:
                speed, bearing = self.internet_gps.get_sdata()
                gps_timestamp = self.internet_gps.get_data_timestamp()
                if gps_timestamp:
                    self.ui.last_gps_read.setText(f"{lat:.7f}, {lon:.7f}")
                    self.ui.last_gps_time.setText(get_date_from_utc(gps_timestamp))

    def _check_internet_status(self):
        """Check internet connectivity by pinging Google DNS"""
        try:
            response_time = ping("8.8.8.8", timeout=3)
            if response_time is not None:
                self._set_internet_status("Connected", True)
                logger.debug(f"Internet ping successful: {response_time:.2f}ms")
            else:
                self._set_internet_status("Disconnected", False)
                logger.debug("Internet ping failed: no response")
        except Exception as e:
            self._set_internet_status("Disconnected", False)
            logger.debug(f"Internet ping error: {e}")

    def _upload_records(self):
        data = self.storage.fetch_all_records()
        if not data:
            return
        payload = []
        device_id = get_processor_id()
        site_id = API_CONFIG.get('site_id', '')
        
        for row in data:
            # adapt to new API format
            record = {
                "rfidTag": row[1],  # rfidTag
                "latitude": row[4],  # latitude
                "longitude": row[5],  # longitude
                "speed": row[6],  # speed
                "deviceId": device_id,  # deviceId from get_processor_id()
                "barrier": "50",  # default barrier value
                "siteId": site_id,  # siteId from settings
                "isProcessed": False,  # default to False
                "antenna": int(row[2]) if row[2] else 1  # antenna number
            }
            payload.append(record)
        
        if self.api.upload_records(payload):
            # best-effort pruning, rely on DB cleanup intervals otherwise
            self.storage.prune_old()


def calculate_next_id(used_ids):
    smallest_available_id = 1
    for record in used_ids:
        current_id = record[0]
        if current_id == smallest_available_id:
            smallest_available_id += 1
        else:
            break
    return smallest_available_id