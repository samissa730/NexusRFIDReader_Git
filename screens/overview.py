import threading
import time
from functools import partial

from PySide6.QtCore import Signal, QTimer
from PySide6.QtWidgets import QWidget, QLineEdit
from utils.common import get_serial, check_internet_connection
from screens.base import BaseScreen
from ui.screens.ui_overview import Ui_OverviewScreen
from utils.logger import logger
from utils.gps import GPS
from settings import GPS_CONFIG


class OverviewScreen(BaseScreen):
    sig_data = Signal(list)

    def __init__(self, app, **kwargs):
        super().__init__(app, **kwargs)
        self.ui = Ui_OverviewScreen()
        self.ui.setupUi(self)
        self.ui.device_id.setText(get_serial())
        
        # Initialize GPS
        self.gps = None
        self.gps_data = {}
        self.last_gps_update = 0
        
        # Initialize data storage for table
        self.scan_data = []  # Store RFID scan data with GPS
        self.max_table_rows = 8
        
        # Initialize timers
        self.gps_update_timer = QTimer()
        self.gps_update_timer.timeout.connect(self.update_gps_display)
        self.gps_update_timer.start(GPS_CONFIG["status_display"]["update_interval"] * 1000)
        
        # Initialize network status timer
        self.network_timer = QTimer()
        self.network_timer.timeout.connect(self.update_network_status)
        self.network_timer.start(5000)  # Update every 5 seconds
        
        # Initialize GPS
        self.initialize_gps()
        
        # Initialize table
        self.initialize_table()
        
        logger.info("Overview initialized successfully")

    def initialize_gps(self):
        """Initialize GPS based on configuration."""
        try:
            gps_type = GPS_CONFIG["gps_type"]
            logger.info(f"Initializing GPS with type: {gps_type}")
            
            self.gps = GPS(gps_type=gps_type)
            self.gps.sig_msg.connect(self.on_gps_status_changed)
            self.gps.sig_data.connect(self.on_gps_data_received)
            self.gps.start()
            
            # Set initial status
            self.ui.gps_connection_status.setText("Initializing...")
            self.ui.gps_connection_status.setStyleSheet("color: orange;")
            
        except Exception as e:
            logger.error(f"Failed to initialize GPS: {e}")
            self.ui.gps_connection_status.setText("Error")
            self.ui.gps_connection_status.setStyleSheet("color: red;")

    def on_gps_status_changed(self, connected):
        """Handle GPS connection status changes."""
        if connected:
            self.ui.gps_connection_status.setText("Connected")
            self.ui.gps_connection_status.setStyleSheet("color: green;")
            logger.info("GPS connected successfully")
        else:
            self.ui.gps_connection_status.setText("Disconnected")
            self.ui.gps_connection_status.setStyleSheet("color: red;")
            logger.warning("GPS disconnected")

    def on_gps_data_received(self, data):
        """Handle new GPS data."""
        self.gps_data = data
        self.last_gps_update = int(time.time() * 1_000_000)
        logger.debug(f"GPS data received: {data}")

    def update_gps_display(self):
        """Update GPS display with latest data."""
        if not self.gps:
            return
        
        try:
            # Get formatted GPS data
            formatted_data = self.gps.get_formatted_data()
            
            # Update GPS coordinates
            self.ui.last_gps_read.setText(formatted_data["coordinates"])
            
            # Update GPS timestamp
            self.ui.last_gps_time.setText(formatted_data["last_update"])
            
            # Check if data is stale
            if self.last_gps_update > 0:
                age_seconds = (int(time.time() * 1_000_000) - self.last_gps_update) / 1_000_000
                if age_seconds > GPS_CONFIG["status_display"]["stale_data_threshold"]:
                    # Data is stale, change color
                    self.ui.last_gps_read.setStyleSheet("color: orange;")
                    self.ui.last_gps_time.setStyleSheet("color: orange;")
                else:
                    # Data is fresh, normal color
                    self.ui.last_gps_read.setStyleSheet("color: white;")
                    self.ui.last_gps_time.setStyleSheet("color: white;")
            
        except Exception as e:
            logger.error(f"Error updating GPS display: {e}")

    def update_network_status(self):
        """Update network status display."""
        try:
            # Check internet connection
            internet_connected = check_internet_connection()
            
            if internet_connected:
                self.ui.wifi_status.setText("Connected")
                self.ui.wifi_status.setStyleSheet("color: green;")
            else:
                self.ui.wifi_status.setText("Disconnected")
                self.ui.wifi_status.setStyleSheet("color: red;")
            
            # For now, set cellular status to N/A
            # In a real implementation, you would check cellular modem status
            self.ui.cellular_status.setText("N/A")
            self.ui.cellular_status.setStyleSheet("color: orange;")
            
        except Exception as e:
            logger.error(f"Error updating network status: {e}")

    def on_enter(self):
        """Called when entering the screen."""
        super().on_enter()
        logger.info("Entered overview screen")

    def on_leave(self):
        """Called when leaving the screen."""
        super().on_leave()
        
        # Stop GPS if running
        if self.gps:
            self.gps.stop()
            logger.info("GPS stopped")
        
        # Stop timers
        if hasattr(self, 'gps_update_timer'):
            self.gps_update_timer.stop()
        if hasattr(self, 'network_timer'):
            self.network_timer.stop()
        
        logger.info("Left overview screen")

    def initialize_table(self):
        """Initialize the data table."""
        try:
            # Set table headers
            headers = ["Time", "Tag", "Antenna", "Position", "Speed", "Heading"]
            self.ui.tableWidget.setHorizontalHeaderLabels(headers)
            
            # Initialize empty rows
            for row in range(self.max_table_rows):
                for col in range(len(headers)):
                    item = self.ui.tableWidget.item(row, col)
                    if item is None:
                        item = self.ui.tableWidget.item(row, col)
                        if item is None:
                            from PySide6.QtWidgets import QTableWidgetItem
                            item = QTableWidgetItem("")
                            self.ui.tableWidget.setItem(row, col, item)
                    item.setText("")
            
            logger.info("Table initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing table: {e}")

    def add_scan_data(self, tag_data):
        """Add new RFID scan data with GPS information to the table."""
        try:
            if not self.gps:
                logger.warning("GPS not available for scan data")
                return
            
            # Get current GPS data
            formatted_gps = self.gps.get_formatted_data()
            sdata = self.gps.get_sdata()
            
            # Create scan record
            scan_record = {
                "timestamp": int(time.time() * 1_000_000),
                "tag": tag_data.get("tag", "N/A"),
                "antenna": tag_data.get("antenna", "N/A"),
                "position": formatted_gps["coordinates"],
                "speed": formatted_gps["speed"],
                "heading": formatted_gps["bearing"]
            }
            
            # Add to scan data list
            self.scan_data.insert(0, scan_record)  # Insert at beginning
            
            # Keep only the latest records
            if len(self.scan_data) > self.max_table_rows:
                self.scan_data = self.scan_data[:self.max_table_rows]
            
            # Update table display
            self.update_table_display()
            
            # Update last RFID read display
            self.ui.last_rfid_read.setText(scan_record["tag"])
            self.ui.last_rfid_time.setText(self.format_timestamp(scan_record["timestamp"]))
            
            logger.debug(f"Added scan data: {scan_record}")
            
        except Exception as e:
            logger.error(f"Error adding scan data: {e}")

    def update_table_display(self):
        """Update the table display with current scan data."""
        try:
            for row, record in enumerate(self.scan_data):
                if row >= self.max_table_rows:
                    break
                
                # Format timestamp
                time_str = self.format_timestamp(record["timestamp"])
                
                # Update table items
                self.ui.tableWidget.setItem(row, 0, self.create_table_item(time_str))
                self.ui.tableWidget.setItem(row, 1, self.create_table_item(record["tag"]))
                self.ui.tableWidget.setItem(row, 2, self.create_table_item(record["antenna"]))
                self.ui.tableWidget.setItem(row, 3, self.create_table_item(record["position"]))
                self.ui.tableWidget.setItem(row, 4, self.create_table_item(record["speed"]))
                self.ui.tableWidget.setItem(row, 5, self.create_table_item(record["heading"]))
            
            # Clear remaining rows
            for row in range(len(self.scan_data), self.max_table_rows):
                for col in range(6):
                    self.ui.tableWidget.setItem(row, col, self.create_table_item(""))
                    
        except Exception as e:
            logger.error(f"Error updating table display: {e}")

    def create_table_item(self, text):
        """Create a table widget item with the given text."""
        from PySide6.QtWidgets import QTableWidgetItem
        item = QTableWidgetItem(str(text))
        item.setTextAlignment(0x0004 | 0x0080)  # Center alignment
        return item

    def format_timestamp(self, timestamp_microseconds):
        """Format timestamp for display."""
        try:
            from utils.common import get_date_from_utc
            return get_date_from_utc(timestamp_microseconds)
        except Exception:
            return "N/A"

    def get_current_gps_data(self):
        """Get current GPS data for external use."""
        if not self.gps:
            return None
        
        try:
            formatted_data = self.gps.get_formatted_data()
            sdata = self.gps.get_sdata()
            
            return {
                "coordinates": formatted_data["coordinates"],
                "speed": sdata[0],
                "bearing": sdata[1],
                "status": formatted_data["status"],
                "last_update": formatted_data["last_update"],
                "raw_data": self.gps.get_data()
            }
        except Exception as e:
            logger.error(f"Error getting GPS data: {e}")
            return None

    def simulate_rfid_scan(self):
        """Simulate an RFID scan for testing purposes."""
        import random
        
        test_data = {
            "tag": f"TAG{random.randint(1000, 9999)}",
            "antenna": random.randint(1, 4)
        }
        
        self.add_scan_data(test_data)
        logger.info(f"Simulated RFID scan: {test_data}")
