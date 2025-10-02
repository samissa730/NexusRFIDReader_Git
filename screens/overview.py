from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QWidget, QTableWidgetItem

from screens.base import BaseScreen
from ui.screens.ui_overview import Ui_OverviewScreen
from utils.logger import logger
from utils.rfid import RFID
from utils.gps import GPS
from utils.common import extract_from_gps, get_date_from_utc, pre_config_gps, find_gps_port, calculate_speed_bearing, get_processor_id
from utils.data_storage import DataStorage
from utils.api_client import ApiClient
from settings import API_CONFIG, FILTER_CONFIG, DATABASE_CONFIG
import time
import requests
from ping3 import ping


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

        # Init helpers and modules
        self.api = ApiClient()
        self.storage = DataStorage(DATABASE_CONFIG.get('use_db', False))
        
        # Set device ID using processor ID
        device_id = get_processor_id()
        self.ui.device_id.setText(device_id)

        # GPS init
        self.last_lat = None
        self.last_lon = None
        self.last_utctime = None
        self.cur_lat = 0
        self.cur_lon = 0
        self.bearing = 0
        self.speed = 0

        self.gps = None
        self.internet_gps_timer = QTimer(self)
        self.internet_gps_timer.timeout.connect(self._poll_internet_gps)
        self.external_retry_timer = QTimer(self)
        self.external_retry_timer.timeout.connect(self._try_external_gps)
        self.external_retry_timer.setInterval(30000)

        # Always attempt external first; fall back to internal and retry external every 30s
        self._try_external_gps(initial=True)

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
            if self.internet_gps_timer.isActive():
                self.internet_gps_timer.stop()
        else:
            # External disconnected: enable internal and start external retry timer
            self._start_internal_gps()
            if not self.external_retry_timer.isActive():
                self.external_retry_timer.start()

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
                lat, lon, speed, bearing = self.cur_lat, self.cur_lon, self.speed, self.bearing

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
            self.ui.last_gps_time.setText(get_date_from_utc(tag['LastSeenTimestampUTC']))

    def _refresh_table(self, new_data):
        for row in range(self.ui.tableWidget.rowCount() - 2, -1, -1):
            for column in range(self.ui.tableWidget.columnCount()):
                item = self.ui.tableWidget.item(row, column).text()
                self.ui.tableWidget.setItem(row + 1, column, QTableWidgetItem(item))
        for column in range(self.ui.tableWidget.columnCount()):
            self.ui.tableWidget.setItem(0, column, QTableWidgetItem(new_data[column]))

    def _poll_internet_gps(self):
        try:
            r = requests.get('http://ip-api.com/json/', timeout=3)
            r.raise_for_status()
            data = r.json()
            if data.get('status') == 'success':
                cur_lat = float(data.get('lat', 0) or 0)
                cur_lon = float(data.get('lon', 0) or 0)
                milliseconds_time = int(time.time() * 1_000_000)
                if self.last_lat is not None:
                    self.speed, self.bearing = calculate_speed_bearing(
                        self.last_lat, self.last_lon, self.last_utctime, cur_lat, cur_lon, milliseconds_time
                    )
                self.last_lat = cur_lat
                self.last_lon = cur_lon
                self.last_utctime = milliseconds_time
                self.cur_lat, self.cur_lon = cur_lat, cur_lon
                
                # Update GPS display fields with internal GPS data
                self.ui.last_gps_read.setText(f"{cur_lat:.7f}, {cur_lon:.7f}")
                self.ui.last_gps_time.setText(get_date_from_utc(milliseconds_time))
                
                if self.ui.gps_connection_status.text() != "External GPS Connected":
                    self._set_gps_status("Internal GPS Connected", True)
        except Exception:
            if self.ui.gps_connection_status.text() != "External GPS Connected":
                self._set_gps_status("Disconnected", False)

    def _try_external_gps(self, initial=False):
        baud = pre_config_gps()
        port = find_gps_port(baud)
        if port is not None:
            self._start_external_gps(port, baud)
            self.external_retry_timer.stop()
        else:
            if initial or self.ui.gps_connection_status.text() != "External GPS Connected":
                self._start_internal_gps()
            if not self.external_retry_timer.isActive():
                self.external_retry_timer.start()

    def _start_external_gps(self, port, baud):
        if self.internet_gps_timer.isActive():
            self.internet_gps_timer.stop()
        if self.gps and self.gps.isRunning():
            self.gps.stop()
        self.gps = GPS(port=port, baud_rate=baud)
        self.gps.sig_msg.connect(self._on_gps_status)
        self.gps.start()
        self._set_gps_status("External GPS Connected", True)

    def _start_internal_gps(self):
        if self.gps and self.gps.isRunning():
            try:
                self.gps.stop()
            except Exception:
                pass
            self.gps = None
        if not self.internet_gps_timer.isActive():
            self.internet_gps_timer.start(4000)
        if self.ui.gps_connection_status.text() != "External GPS Connected":
            self._set_gps_status("Disconnected", False)

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
                current_time = int(time.time() * 1_000_000)
                self.ui.last_gps_read.setText(f"{lat:.7f}, {lon:.7f}")
                self.ui.last_gps_time.setText(get_date_from_utc(current_time))
        elif self.cur_lat != 0 and self.cur_lon != 0:
            # Internal GPS (internet-based)
            self.ui.last_gps_read.setText(f"{self.cur_lat:.7f}, {self.cur_lon:.7f}")
            if self.last_utctime:
                self.ui.last_gps_time.setText(get_date_from_utc(self.last_utctime))

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
        payload = {"spotterId": API_CONFIG.get('spotter_id', '0'), "data": []}
        for row in data:
            # adapt to default payload (minimal)
            payload["data"].append({
                "tag": row[1],
                "ant": row[2],
                "lat": row[4],
                "lng": row[5],
                "speed": row[6],
                "heading": row[7],
                "locationCode": row[8]
            })
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


