from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QWidget, QTableWidgetItem

from screens.base import BaseScreen
from ui.screens.ui_overview import Ui_OverviewScreen
from utils.logger import logger
from utils.rfid import RFID
from utils.gps import GPS
from utils.common import extract_from_gps, get_date_from_utc, pre_config_gps, find_gps_port
from utils.data_storage import DataStorage
from utils.api_client import ApiClient
from settings import GPS_CONFIG, API_CONFIG, RFID_CONFIG, FILTER_CONFIG, DATABASE_CONFIG
import time


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

        # GPS init
        self.last_lat = None
        self.last_lon = None
        self.last_utctime = None
        self.cur_lat = 0
        self.cur_lon = 0
        self.bearing = 0
        self.speed = 0

        baud = pre_config_gps()
        port = find_gps_port(baud)
        self.gps = None
        if GPS_CONFIG.get('use_external', False) and port is not None:
            self.gps = GPS(port=port, baud_rate=baud)
            self.gps.sig_msg.connect(self._on_gps_status)
            self.gps.start()
        self.internet_gps_timer = QTimer(self)
        self.internet_gps_timer.timeout.connect(self._poll_internet_gps)
        if not GPS_CONFIG.get('use_external', False):
            self.internet_gps_timer.start(4000)

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

    def on_leave(self):
        if self.gps and self.gps.isRunning():
            self.gps.stop()
        if self.rfid and self.rfid.isRunning():
            self.rfid.stop()
        self.storage.close()

    def _on_gps_status(self, status):
        if status:
            self.ui.gps_connection_status.setStyleSheet("""
                padding: 5px;
                border: 1px solid black;
                color: green;
                """)
            self.ui.gps_connection_status.setText("Connected")
        else:
            self.ui.gps_connection_status.setStyleSheet("""
                padding: 5px;
                border: 1px solid black;
                color: red;
                """)
            self.ui.gps_connection_status.setText("Disconnected")

    def _on_rfid_status(self, status):
        if status == 1:
            self.ui.rfid_connection_status.setStyleSheet("""
                padding: 5px;
                border: 1px solid black;
                color: green;
                """)
            self.ui.rfid_connection_status.setText("Connected")
        elif status == 2:
            self.ui.rfid_connection_status.setStyleSheet("""
                padding: 5px;
                border: 1px solid black;
                color: red;
                """)
            self.ui.rfid_connection_status.setText("Disconnected")
        elif status == 3:
            tag = self.rfid.tag_data[0]
            lat, lon, speed, bearing = 0, 0, 0, 0
            if GPS_CONFIG.get('use_external', False) and self.gps:
                lat, lon = extract_from_gps(self.gps.get_data())
                if lat != 0 and lon != 0:
                    self.last_lat = lat
                    self.last_lon = lon
                    self.last_utctime = int(time.time() * 1_000_000)
                speed, bearing = self.gps.get_sdata()
            else:
                lat, lon, speed, bearing = self.cur_lat, self.cur_lon, self.speed, self.bearing

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
                            None, None, None, None, None, None, None, None
                        ]
                        self.storage.add_record(rec)
                else:
                    new_data = [True, tag['EPC-96'], f"{tag['AntennaID']}", f"{tag['PeakRSSI']}",
                                lat, lon, speed, bearing, "-", self.api.user_name, tag['LastSeenTimestampUTC'],
                                None, None, None, None, None, None, None, None]
                    self.storage.add_record(new_data)

            # UI updates
            self._refresh_table([get_date_from_utc(tag['LastSeenTimestampUTC']), tag['EPC-96'], f"{tag['AntennaID']}",
                                 f"{lat:.4f}".rstrip('0').rstrip('.') + ", " + f"{lon:.4f}".rstrip('0').rstrip('.'),
                                 f"{speed:.4f}".rstrip('0').rstrip('.'), f"{bearing}"])
            self.ui.last_rfid_read.setText(tag['EPC-96'])
            self.ui.last_rfid_time.setText(get_date_from_utc(tag['LastSeenTimestampUTC']))
            self.ui.last_gps_read.setText(f"{lat}, {lon}")
            self.ui.last_gps_time.setText(get_date_from_utc(tag['LastSeenTimestampUTC']))

    def _refresh_table(self, new_data):
        for row in range(self.ui.tableWidget.rowCount() - 2, -1, -1):
            for column in range(self.ui.tableWidget.columnCount()):
                item = self.ui.tableWidget.item(row, column).text()
                self.ui.tableWidget.setItem(row + 1, column, QTableWidgetItem(item))
        for column in range(self.ui.tableWidget.columnCount()):
            self.ui.tableWidget.setItem(0, column, QTableWidgetItem(new_data[column]))

    def _poll_internet_gps(self):
        # Optional: implement an IP-based location provider if configured
        # noop placeholder; user can add later if needed
        pass

    def _upload_health(self):
        lat, lon = (0, 0)
        if self.gps:
            lat, lon = extract_from_gps(self.gps.get_data())
        gps_text = self.ui.gps_connection_status.text()
        self.api.upload_health(bool(self.rfid.connectivity), gps_text, lat, lon)

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


