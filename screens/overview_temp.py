from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QWidget, QTableWidgetItem

from screens.base import BaseScreen
from ui.screens.ui_overview import Ui_OverviewScreen
from utils.logger import logger
from utils.gps import GPS
from utils.common import extract_from_gps, get_date_from_utc, pre_config_gps, find_gps_port, calculate_speed_bearing, get_processor_id
from settings import GPS_CONFIG
import time
import requests
from utils.rfid_temp import RFIDTemp


class OverviewScreenTemp(BaseScreen):

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

        # GPS display update timer
        self.gps_display_timer = QTimer(self)
        self.gps_display_timer.timeout.connect(self._update_gps_display)
        self.gps_display_timer.start(2000)  # Update every 2 seconds

        # Initialize UI status displays
        self._initialize_status_displays()

        # RFID temp reader (for health and last tag display)
        self.rfid = RFIDTemp()
        self.rfid.sig_msg.connect(self._on_rfid_status)
        self.rfid.start()

    def _initialize_status_displays(self):
        """Initialize status displays with default values"""
        # RFID status
        self.ui.rfid_connection_status.setStyleSheet("color: #ff0000;")
        self.ui.rfid_connection_status.setText("Disconnected")
        self.ui.last_rfid_read.setText("N/A")
        self.ui.last_rfid_time.setText("N/A")
        
        # GPS status
        self.ui.gps_connection_status.setStyleSheet("color: #ff0000;")
        self.ui.gps_connection_status.setText("Disconnected")
        self.ui.last_gps_read.setText("N/A")
        self.ui.last_gps_time.setText("N/A")
        
        # Site details
        self.ui.truck_number.setText("N/A")
        self.ui.site_name.setText("N/A")
        

    def on_leave(self):
        if self.gps and self.gps.isRunning():
            self.gps.stop()
        if hasattr(self, 'gps_display_timer'):
            self.gps_display_timer.stop()
        if hasattr(self, 'rfid') and self.rfid:
            if self.rfid.isRunning():
                self.rfid.stop()

    def _set_gps_status(self, text, ok):
        self.ui.gps_connection_status.setStyleSheet("""color: #00ff00;""" if ok else """color: #ff0000;""")
        self.ui.gps_connection_status.setText(text)

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
        # 1: connected, 2: disconnected, 3: tag seen
        if status == 1:
            self.ui.rfid_connection_status.setStyleSheet("""color: #00ff00;""")
            self.ui.rfid_connection_status.setText("Connected")
        elif status == 2:
            self.ui.rfid_connection_status.setStyleSheet("""color: #ff0000;""")
            self.ui.rfid_connection_status.setText("Disconnected")
        elif status == 3 and self.rfid and self.rfid.tag_data:
            tag = self.rfid.tag_data[0]
            ts_us = tag.get('LastSeenTimestampUTC') or int(time.time() * 1_000_000)
            self.ui.last_rfid_read.setText(tag.get('EPC-96', 'N/A'))
            self.ui.last_rfid_time.setText(get_date_from_utc(ts_us))

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
        elif self.cur_lat != 0 and self.cur_lon != 0:
            # Internal GPS (internet-based)
            self.ui.last_gps_read.setText(f"{self.cur_lat:.7f}, {self.cur_lon:.7f}")
            if self.last_utctime:
                self.ui.last_gps_time.setText(get_date_from_utc(self.last_utctime))

    def add_test_data_to_table(self, test_data):
        """Add test data to the table for development purposes"""
        self._refresh_table(test_data)

    def set_site_info(self, truck_number="N/A", site_name="N/A"):
        """Set site information for development purposes"""
        self.ui.truck_number.setText(truck_number)
        self.ui.site_name.setText(site_name)

    def set_network_status(self, wifi_status="N/A", cellular_status="N/A"):
        """Set network status for development purposes"""
        self.ui.wifi_status.setText(wifi_status)
        self.ui.cellular_status.setText(cellular_status)
