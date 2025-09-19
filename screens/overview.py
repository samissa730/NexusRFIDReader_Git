import threading
import time
from datetime import datetime
from functools import partial

from PySide6.QtCore import Signal, QTimer
from PySide6.QtWidgets import QWidget, QLineEdit

from utils.common import get_serial, format_coordinates, is_gps_data_valid
from utils.gps import GPS
from screens.base import BaseScreen
from ui.screens.ui_overview import Ui_OverviewScreen
from utils.logger import logger
from settings import GPS_CONFIG


class OverviewScreen(BaseScreen):
    """
    Overview screen with GPS functionality implementation.
    Implements User Story 13173: Update dashboard with latest GPS data
    """
    
    sig_data = Signal(list)

    def __init__(self, app, **kwargs):
        super().__init__(app, **kwargs)
        self.ui = Ui_OverviewScreen()
        self.ui.setupUi(self)
        
        # Initialize GPS system
        self._init_gps_system()
        
        # Initialize UI
        self._init_ui()
        
        # Setup timers for periodic updates
        self._setup_timers()
        
        logger.info("Overview screen initialized successfully")

    def _init_gps_system(self):
        """
        Initialize GPS system based on configuration.
        User Story 13047 & 13048: GPS Connectivity and Configuration
        """
        try:
            # Create GPS instance based on configuration
            self.gps = GPS(
                gps_type=GPS_CONFIG["type"],
                current_status="N/A"
            )
            
            # Connect GPS signals
            self.gps.sig_status_changed.connect(self._on_gps_status_changed)
            self.gps.sig_data_updated.connect(self._on_gps_data_updated)
            self.gps.sig_error_occurred.connect(self._on_gps_error)
            
            # Start GPS processing if enabled
            if GPS_CONFIG["enabled"]:
                self.gps.start()
                logger.info(f"GPS system started with type: {GPS_CONFIG['type']}")
            else:
                logger.info("GPS system disabled in configuration")
                
        except Exception as e:
            logger.error(f"Failed to initialize GPS system: {e}")
            self.gps = None

    def _init_ui(self):
        """Initialize UI elements"""
        # Set device ID
        self.ui.device_id.setText(get_serial())
        
        # Initialize GPS status display
        self._update_gps_status_display("N/A", False)
        self._update_gps_data_display("N/A", "N/A")
        
        # Initialize other status displays
        self._update_rfid_status_display("N/A", False)
        self._update_network_status_display("N/A", "N/A")

    def _setup_timers(self):
        """
        Setup periodic timers for UI updates.
        User Story 13173: Update dashboard with latest GPS data
        """
        # GPS status update timer (every 1 second)
        self.gps_status_timer = QTimer()
        self.gps_status_timer.timeout.connect(self._update_gps_status_periodic)
        self.gps_status_timer.start(1000)
        
        # GPS data update timer (every 2 seconds)
        self.gps_data_timer = QTimer()
        self.gps_data_timer.timeout.connect(self._update_gps_data_periodic)
        self.gps_data_timer.start(2000)

    def _on_gps_status_changed(self, connected: bool):
        """
        Handle GPS connection status changes.
        User Story 13173: Update dashboard with latest GPS data
        """
        status_text = "Connected" if connected else "Disconnected"
        self._update_gps_status_display(status_text, connected)
        logger.info(f"GPS status changed: {status_text}")

    def _on_gps_data_updated(self, gps_data: dict):
        """
        Handle new GPS data updates.
        User Story 13173: Update dashboard with latest GPS data
        """
        try:
            if is_gps_data_valid(gps_data):
                # Extract coordinates
                lat = gps_data.get('latitude', 0)
                lon = gps_data.get('longitude', 0)
                
                # Format coordinates for display
                coordinates = format_coordinates(lat, lon, precision=4)
                
                # Get speed and bearing if available
                speed = gps_data.get('speed_mph', 0)
                bearing = gps_data.get('course', 0)
                
                # Update display
                self._update_gps_data_display(coordinates, f"{speed:.1f} mph, {bearing:.0f}°")
                
                # Emit data signal for other components
                self.sig_data.emit([lat, lon, speed, bearing])
                
                logger.debug(f"GPS data updated: {coordinates}")
            else:
                logger.warning("Received invalid GPS data")
                
        except Exception as e:
            logger.error(f"Error processing GPS data update: {e}")

    def _on_gps_error(self, error_message: str):
        """
        Handle GPS errors.
        User Story 13173: Update dashboard with latest GPS data
        """
        logger.error(f"GPS error: {error_message}")
        self._update_gps_status_display("Error", False)

    def _update_gps_status_display(self, status: str, connected: bool):
        """
        Update GPS connection status display.
        User Story 13173: Update dashboard with latest GPS data
        """
        try:
            self.ui.gps_connection_status.setText(status)
            
            # Set color based on status
            if connected:
                color = "green"
            elif status == "Error":
                color = "red"
            else:
                color = "orange"
            
            # Apply styling
            self.ui.gps_connection_status.setStyleSheet(f"color: {color};")
            
        except Exception as e:
            logger.error(f"Error updating GPS status display: {e}")

    def _update_gps_data_display(self, coordinates: str, speed_bearing: str):
        """
        Update GPS data display.
        User Story 13173: Update dashboard with latest GPS data
        """
        try:
            self.ui.last_gps_read.setText(coordinates)
            self.ui.last_gps_time.setText(datetime.now().strftime("%H:%M:%S"))
            
            # Update table if it exists (for speed/bearing display)
            # This would be implemented based on specific UI requirements
            
        except Exception as e:
            logger.error(f"Error updating GPS data display: {e}")

    def _update_gps_status_periodic(self):
        """
        Periodic GPS status update.
        User Story 13173: Update dashboard with latest GPS data
        """
        try:
            if self.gps:
                status = self.gps.get_status()
                
                # Check if GPS data is fresh
                if status.get('data_age_seconds', 0) > GPS_CONFIG.get('max_age_seconds', 300):
                    self._update_gps_status_display("Stale", False)
                elif not status.get('connected', False):
                    self._update_gps_status_display("Disconnected", False)
                    
        except Exception as e:
            logger.error(f"Error in periodic GPS status update: {e}")

    def _update_gps_data_periodic(self):
        """
        Periodic GPS data update.
        User Story 13173: Update dashboard with latest GPS data
        """
        try:
            if self.gps:
                gps_data = self.gps.get_data()
                if gps_data and is_gps_data_valid(gps_data):
                    # Update coordinates display
                    lat = gps_data.get('latitude', 0)
                    lon = gps_data.get('longitude', 0)
                    coordinates = format_coordinates(lat, lon, precision=4)
                    self.ui.last_gps_read.setText(coordinates)
                    
                    # Update timestamp
                    self.ui.last_gps_time.setText(datetime.now().strftime("%H:%M:%S"))
                    
        except Exception as e:
            logger.error(f"Error in periodic GPS data update: {e}")

    def _update_rfid_status_display(self, status: str, connected: bool):
        """Update RFID status display"""
        try:
            self.ui.rfid_connection_status.setText(status)
            color = "green" if connected else "red"
            self.ui.rfid_connection_status.setStyleSheet(f"color: {color};")
        except Exception as e:
            logger.error(f"Error updating RFID status display: {e}")

    def _update_network_status_display(self, wifi_status: str, cellular_status: str):
        """Update network status display"""
        try:
            self.ui.wifi_status.setText(wifi_status)
            self.ui.cellular_status.setText(cellular_status)
        except Exception as e:
            logger.error(f"Error updating network status display: {e}")

    def get_current_gps_data(self):
        """
        Get current GPS data for external use.
        User Story 13173: Update dashboard with latest GPS data
        """
        try:
            if self.gps:
                return self.gps.get_data()
            return {}
        except Exception as e:
            logger.error(f"Error getting current GPS data: {e}")
            return {}

    def get_gps_coordinates(self):
        """
        Get current GPS coordinates.
        User Story 13173: Update dashboard with latest GPS data
        """
        try:
            if self.gps:
                return self.gps.get_coordinates()
            return (0, 0)
        except Exception as e:
            logger.error(f"Error getting GPS coordinates: {e}")
            return (0, 0)

    def is_gps_connected(self):
        """
        Check if GPS is currently connected.
        User Story 13173: Update dashboard with latest GPS data
        """
        try:
            if self.gps:
                status = self.gps.get_status()
                return status.get('connected', False)
            return False
        except Exception as e:
            logger.error(f"Error checking GPS connection: {e}")
            return False

    def on_enter(self):
        """
        Called when entering the overview screen.
        User Story 13173: Update dashboard with latest GPS data
        """
        super().on_enter()
        logger.info("Entered overview screen")
        
        # Start GPS if not already running
        if self.gps and GPS_CONFIG["enabled"] and not self.gps.isRunning():
            self.gps.start()
            logger.info("Started GPS processing")

    def on_leave(self):
        """
        Called when leaving the overview screen.
        """
        super().on_leave()
        logger.info("Left overview screen")
        
        # Stop GPS processing
        if self.gps and self.gps.isRunning():
            self.gps.stop()
            logger.info("Stopped GPS processing")
