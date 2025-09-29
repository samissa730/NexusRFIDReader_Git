import threading
import time
from functools import partial
from typing import Dict, Any

from PySide6.QtCore import Signal, QTimer
from PySide6.QtWidgets import QWidget, QLineEdit, QTableWidgetItem
from utils.common import (get_serial, format_coordinates, format_speed, 
                         format_bearing, get_date_from_utc, validate_gps_coordinates)
from screens.base import BaseScreen
from ui.screens.ui_overview import Ui_OverviewScreen
from utils.gps import GPS
from utils.rfid import RFID
from utils.data_storage import DataStorage
from utils.api_client import APIClient, UploadManager
from utils.sound_manager import sound_manager
from utils.logger import logger
from settings import GPS_CONFIG, RFID_CONFIG, FILTER_CONFIG, API_CREDENTIALS


class OverviewScreen(BaseScreen):
    sig_data = Signal(list)

    def __init__(self, app, **kwargs):
        super().__init__(app, **kwargs)
        self.ui = Ui_OverviewScreen()
        self.ui.setupUi(self)
        self.ui.device_id.setText(get_serial())
        
        # GPS initialization
        self.gps = None
        self.gps_data = {}
        self.last_gps_update = 0
        self.gps_timer = None
        
        # RFID initialization
        self.rfid = None
        self.rfid_data = {}
        self.last_rfid_update = 0
        
        # Data storage and API
        self.data_storage = DataStorage()
        self.api_client = APIClient()
        self.upload_manager = None
        
        # Current position data
        self.current_lat = 0.0
        self.current_lon = 0.0
        self.current_speed = 0.0
        self.current_bearing = 0.0
        
        # Initialize components
        self._initialize_gps()
        self._initialize_rfid()
        # Start API initialization in background so UI shows immediately
        threading.Thread(target=self._initialize_api, daemon=True).start()
        
        # Setup UI update timer
        self._setup_update_timer()
        
        logger.info("Overview initialized successfully")

    def _initialize_gps(self):
        """Initialize GPS system based on configuration."""
        try:
            gps_type = GPS_CONFIG["type"]
            self.gps = GPS(gps_type=gps_type)
            
            # Connect GPS signals
            self.gps.sig_status_changed.connect(self._on_gps_status_changed)
            self.gps.sig_data_updated.connect(self._on_gps_data_updated)
            self.gps.sig_error_occurred.connect(self._on_gps_error)
            
            # Set initial status based on GPS type
            initial_status = self.gps.get_status()
            logger.info(f"Setting initial GPS status: {initial_status}")
            self._update_gps_status(initial_status)
            
            # Start GPS thread
            self.gps.start()
            
            logger.info(f"GPS initialized with type: {gps_type}")
            
        except Exception as e:
            logger.error(f"Failed to initialize GPS: {e}")
            self._update_gps_status("Disconnected")

    def _initialize_rfid(self):
        """Initialize RFID reader system."""
        try:
            self.rfid = RFID()
            
            # Connect RFID signals
            self.rfid.sig_msg.connect(self._on_rfid_status_changed)
            self.rfid.sig_tag_detected.connect(self._on_rfid_tag_detected)
            
            # Start RFID thread
            self.rfid.start()
            
            logger.info("RFID reader initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize RFID: {e}")
            self.rfid = None

    def _initialize_api(self):
        """Initialize API client and upload manager."""
        try:
            # Prefer token if provided, otherwise fall back to username/password
            token = (API_CREDENTIALS.get("token") or "").strip()
            username = (API_CREDENTIALS.get("username") or "").strip()
            password = (API_CREDENTIALS.get("password") or "").strip()

            if token:
                self.api_client.token = token
                logger.info("Using pre-configured API token from settings")
                self.upload_manager = UploadManager(self.api_client, self.data_storage)
                self.upload_manager.start()
            elif username and password:
                if self.api_client.authenticate(username, password):
                    self.upload_manager = UploadManager(self.api_client, self.data_storage)
                    self.upload_manager.start()
                    logger.info("API client authenticated using username/password")
                else:
                    logger.warning("API authentication failed - running in offline mode")
            else:
                logger.info("No API credentials provided - running in offline mode")
                
        except Exception as e:
            logger.error(f"Failed to initialize API client: {e}")

    def _setup_update_timer(self):
        """Setup timer for periodic UI updates."""
        update_rate = GPS_CONFIG["dashboard"]["update_rate"]
        self.gps_timer = QTimer()
        self.gps_timer.timeout.connect(self._update_dashboard)
        self.gps_timer.start(update_rate * 1000)  # Convert to milliseconds

    def _on_gps_status_changed(self, status: str):
        """Handle GPS connection status changes."""
        self._update_gps_status(status)
        logger.info(f"GPS status changed: {status}")

    def _on_gps_data_updated(self, data: Dict[str, Any]):
        """Handle new GPS data updates."""
        self.gps_data = data
        self.last_gps_update = time.time()
        self._update_gps_display()

    def _on_gps_error(self, error_message: str):
        """Handle GPS errors."""
        logger.error(f"GPS error: {error_message}")
        self._update_gps_status("Disconnected")

    def _on_rfid_status_changed(self, status: int):
        """Handle RFID status changes."""
        if status == 1:  # Connected
            logger.info("RFID reader connected")
            self._update_rfid_status("Connected")
        elif status == 2:  # Disconnected
            logger.warning("RFID reader disconnected")
            self._update_rfid_status("Disconnected")
        elif status == 3:  # Tag detected
            logger.debug("RFID tag detected")

    def _on_rfid_tag_detected(self, tag_data: Dict[str, Any]):
        """Handle RFID tag detection."""
        try:
            self.rfid_data = tag_data
            self.last_rfid_update = time.time()
            
            # Get current GPS coordinates
            lat, lon = self.current_lat, self.current_lon
            speed, bearing = self.current_speed, self.current_bearing
            
            # Check if we should store this record
            if self._should_store_record(tag_data, lat, lon, speed):
                # Store the record
                timestamp = int(time.time() * 1_000_000)
                success = self.data_storage.store_record(
                    rfid_tag=tag_data.get('EPC-96', ''),
                    antenna=tag_data.get('AntennaID', 0),
                    rssi=tag_data.get('PeakRSSI', 0),
                    latitude=lat,
                    longitude=lon,
                    speed=speed,
                    heading=bearing,
                    location_code="-",  # Default location code
                    username=self.api_client.get_user_id() or "unknown",
                    timestamp=timestamp
                )
                
                if success:
                    logger.info(f"Stored RFID record: {tag_data.get('EPC-96', '')}")
                    
                    # Play sound notification
                    sound_manager.play_notification("tag_detected")
                    
                    # Update UI
                    self._update_rfid_display(tag_data, lat, lon, speed, bearing)
                else:
                    logger.error("Failed to store RFID record")
            
        except Exception as e:
            logger.error(f"Error handling RFID tag detection: {e}")

    def _should_store_record(self, tag_data: Dict[str, Any], lat: float, lon: float, speed: float) -> bool:
        """Check if record should be stored based on filters."""
        try:
            # Check speed filter
            if FILTER_CONFIG["speed"]["enabled"]:
                min_speed = FILTER_CONFIG["speed"]["min"]
                max_speed = FILTER_CONFIG["speed"]["max"]
                if speed < min_speed or speed > max_speed:
                    return False
            
            # Check RSSI filter
            if FILTER_CONFIG["rssi"]["enabled"]:
                rssi = tag_data.get('PeakRSSI', 0)
                min_rssi = FILTER_CONFIG["rssi"]["min"]
                max_rssi = FILTER_CONFIG["rssi"]["max"]
                if rssi < min_rssi or rssi > max_rssi:
                    return False
            
            # Check tag range filter
            if FILTER_CONFIG["tag_range"]["enabled"]:
                tag_id = int(tag_data.get('EPC-96', '0'))
                min_tag = FILTER_CONFIG["tag_range"]["min"]
                max_tag = FILTER_CONFIG["tag_range"]["max"]
                if tag_id < min_tag or tag_id > max_tag:
                    return False
            
            # Check for duplicates
            rfid_tag = tag_data.get('EPC-96', '')
            timestamp = int(time.time() * 1_000_000)
            if self.data_storage.check_duplicate(rfid_tag, timestamp):
                logger.debug(f"Duplicate RFID tag detected: {rfid_tag}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking record filters: {e}")
            return True  # Default to storing if filter check fails

    def _update_gps_status(self, status: str):
        """Update GPS connection status in UI."""
        logger.info(f"Updating GPS status to: {status}")
        # Check if the UI has the GPS status label
        if hasattr(self.ui, 'gps_connection_status'):
            self.ui.gps_connection_status.setText(status)
            logger.info(f"GPS status label updated to: {status}")
            
            # Update status color based on connection state
            if status == "External(Connected)":
                self.ui.gps_connection_status.setStyleSheet("color: #00ff00;")  # Green
            elif status == "Internal(Connected)":
                self.ui.gps_connection_status.setStyleSheet("color: #00bfff;")  # Blue
            elif status == "Disconnected":
                self.ui.gps_connection_status.setStyleSheet("color: #ff0000;")  # Red
            else:
                # Handle other statuses like "Internal(Connected), External(Disconnected)"
                if "Internal(Connected)" in status:
                    self.ui.gps_connection_status.setStyleSheet("color: #00bfff;")  # Blue
                elif "External(Connected)" in status:
                    self.ui.gps_connection_status.setStyleSheet("color: #00ff00;")  # Green
                else:
                    # All other statuses should show as Disconnected
                    self.ui.gps_connection_status.setText("Disconnected")
                    self.ui.gps_connection_status.setStyleSheet("color: #ff0000;")  # Red
        else:
            logger.warning("GPS connection status label not found in UI")

    def _update_rfid_status(self, status: str):
        """Update RFID connection status in UI."""
        logger.info(f"Updating RFID status to: {status}")
        # Check if the UI has the RFID status label
        if hasattr(self.ui, 'rfid_connection_status'):
            self.ui.rfid_connection_status.setText(status)
            logger.info(f"RFID status label updated to: {status}")
            
            # Update status color based on connection state
            if status == "Connected":
                self.ui.rfid_connection_status.setStyleSheet("color: #00ff00;")  # Green
            elif status == "Disconnected":
                self.ui.rfid_connection_status.setStyleSheet("color: #ff0000;")  # Red
        else:
            logger.warning("RFID connection status label not found in UI")

    def _update_rfid_display(self, tag_data: Dict[str, Any], lat: float, lon: float, speed: float, bearing: float):
        """Update RFID data display in UI."""
        try:
            rfid_tag = tag_data.get('EPC-96', 'N/A')
            antenna = tag_data.get('AntennaID', 0)
            rssi = tag_data.get('PeakRSSI', 0)
            
            # Update RFID fields if they exist in UI
            if hasattr(self.ui, 'last_rfid_read'):
                self.ui.last_rfid_read.setText(rfid_tag)
            
            if hasattr(self.ui, 'last_rfid_time'):
                current_time = int(time.time() * 1_000_000)
                time_text = get_date_from_utc(current_time)
                self.ui.last_rfid_time.setText(time_text)
            
            # Update table with RFID data if available
            self._update_rfid_table_row(tag_data, lat, lon, speed, bearing)
            
        except Exception as e:
            logger.error(f"Error updating RFID display: {e}")

    def _update_rfid_table_row(self, tag_data: Dict[str, Any], lat: float, lon: float, speed: float, bearing: float):
        """Update RFID data in the main table."""
        try:
            rfid_tag = tag_data.get('EPC-96', 'N/A')
            antenna = tag_data.get('AntennaID', 0)
            rssi = tag_data.get('PeakRSSI', 0)
            
            # Format data for table
            coord_text = format_coordinates(lat, lon, precision=6)
            speed_text = format_speed(speed, GPS_CONFIG["processing"]["speed_unit"])
            bearing_text = format_bearing(bearing)
            time_text = get_date_from_utc(int(time.time() * 1_000_000))
            
            # Update first row with RFID data if table exists
            if hasattr(self.ui, 'tableWidget'):
                self.ui.tableWidget.setItem(0, 0, QTableWidgetItem(time_text))
                self.ui.tableWidget.setItem(0, 1, QTableWidgetItem(rfid_tag))
                self.ui.tableWidget.setItem(0, 2, QTableWidgetItem(f"Ant:{antenna}, RSSI:{rssi}"))
                self.ui.tableWidget.setItem(0, 3, QTableWidgetItem(coord_text))
                self.ui.tableWidget.setItem(0, 4, QTableWidgetItem(speed_text))
                self.ui.tableWidget.setItem(0, 5, QTableWidgetItem(bearing_text))
            
        except Exception as e:
            logger.error(f"Error updating RFID table: {e}")

    def _update_gps_display(self):
        """Update GPS data display in UI."""
        if not self.gps_data:
            if hasattr(self.ui, 'last_gps_read'):
                self.ui.last_gps_read.setText("N/A")
            if hasattr(self.ui, 'last_gps_time'):
                self.ui.last_gps_time.setText("N/A")
            return

        try:
            # Get coordinates
            lat, lon = self.gps.get_coordinates()
            
            if validate_gps_coordinates(lat, lon):
                # Update current position data
                self.current_lat = lat
                self.current_lon = lon
                
                # Get speed and bearing
                speed, bearing = self.gps.get_speed_bearing()
                self.current_speed = speed
                self.current_bearing = bearing
                
                # Format coordinates for display with full precision
                coord_text = format_coordinates(lat, lon, precision=6)
                if hasattr(self.ui, 'last_gps_read'):
                    self.ui.last_gps_read.setText(coord_text)
                
                # Update timestamp
                current_time = int(time.time() * 1_000_000)
                time_text = get_date_from_utc(current_time)
                if hasattr(self.ui, 'last_gps_time'):
                    self.ui.last_gps_time.setText(time_text)
                
                # Update table with GPS data if available
                self._update_gps_table_row(lat, lon)
                
            else:
                if hasattr(self.ui, 'last_gps_read'):
                    self.ui.last_gps_read.setText("Invalid Coordinates")
                if hasattr(self.ui, 'last_gps_time'):
                    self.ui.last_gps_time.setText("N/A")
                
        except Exception as e:
            logger.error(f"Error updating GPS display: {e}")
            if hasattr(self.ui, 'last_gps_read'):
                self.ui.last_gps_read.setText("Error")
            if hasattr(self.ui, 'last_gps_time'):
                self.ui.last_gps_time.setText("N/A")

    def _update_gps_table_row(self, lat: float, lon: float):
        """Update GPS data in the main table."""
        try:
            # Get speed and bearing
            speed, bearing = self.gps.get_speed_bearing()
            
            # Format data for table
            coord_text = format_coordinates(lat, lon, precision=6)  # Show full precision
            speed_text = format_speed(speed, GPS_CONFIG["processing"]["speed_unit"])
            bearing_text = format_bearing(bearing)
            time_text = get_date_from_utc(int(time.time() * 1_000_000))
            
            # Update first row with GPS data if table exists
            if hasattr(self.ui, 'tableWidget'):
                self.ui.tableWidget.setItem(0, 0, QTableWidgetItem(time_text))
                self.ui.tableWidget.setItem(0, 1, QTableWidgetItem("GPS"))
                self.ui.tableWidget.setItem(0, 2, QTableWidgetItem("N/A"))
                self.ui.tableWidget.setItem(0, 3, QTableWidgetItem(coord_text))
                self.ui.tableWidget.setItem(0, 4, QTableWidgetItem(speed_text))
                self.ui.tableWidget.setItem(0, 5, QTableWidgetItem(bearing_text))
            
        except Exception as e:
            logger.error(f"Error updating GPS table: {e}")

    def _update_dashboard(self):
        """Periodic dashboard update."""
        try:
            # Check if GPS data is stale - but don't override if GPS is actively working
            if self.gps and self.gps.is_data_stale():
                # Only set to Disconnected if GPS is truly not working
                current_status = self.gps.get_status()
                if current_status not in ["External(Connected)", "Internal(Connected)"]:
                    self._update_gps_status("Disconnected")
            
            # Update signal quality if enabled
            if GPS_CONFIG["dashboard"]["show_signal_quality"]:
                self._update_signal_quality()
                
        except Exception as e:
            logger.error(f"Error in dashboard update: {e}")

    def _update_signal_quality(self):
        """Update GPS signal quality information."""
        try:
            if self.gps:
                quality = self.gps.get_signal_quality()
                
                # Add signal quality info to GPS display
                if quality["status"] != "No Fix" and hasattr(self.ui, 'last_gps_read'):
                    satellites = quality.get("satellites", 0)
                    accuracy = quality.get("accuracy", 0)
                    
                    # Append signal info to coordinates
                    current_text = self.ui.last_gps_read.text()
                    if current_text != "N/A" and current_text != "Error":
                        signal_info = f" ({satellites} sats, {accuracy:.0f}m)"
                        if signal_info not in current_text:
                            self.ui.last_gps_read.setText(current_text + signal_info)
                            
        except Exception as e:
            logger.error(f"Error updating signal quality: {e}")

    def on_leave(self):
        """Cleanup when leaving the screen."""
        try:
            # Stop timers
            if self.gps_timer:
                self.gps_timer.stop()
            
            # Stop GPS
            if self.gps:
                self.gps.stop()
            
            # Stop RFID
            if self.rfid:
                self.rfid.stop()
            
            # Stop upload manager
            if self.upload_manager:
                self.upload_manager.stop()
            
            # Close data storage
            if self.data_storage:
                self.data_storage.close()
            
            # Close API client
            if self.api_client:
                self.api_client.close()
            
            # Cleanup sound manager
            sound_manager.cleanup()
                
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
        
        super().on_leave()
