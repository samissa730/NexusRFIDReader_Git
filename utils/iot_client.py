"""
IoT Client - Sends scan data to Azure IoT service via Unix socket
This module provides a client for the main RFID application to send scan data
to the Azure IoT service running as a separate process.
"""

import socket
import json
from pathlib import Path
from utils.logger import logger

SOCKET_PATH = '/var/run/nexus-iot.sock'


class IoTClient:
    """Client for sending scan data to Azure IoT service via Unix socket"""
    
    def __init__(self, socket_path=SOCKET_PATH):
        self.socket_path = socket_path
        self.socket = None
        self._connected = False
        
    def connect(self):
        """Connect to Azure IoT service socket"""
        if self._connected and self.socket:
            return True
            
        try:
            # Check if socket file exists
            if not Path(self.socket_path).exists():
                logger.debug(f"IoT service socket not found: {self.socket_path}")
                return False
            
            self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.socket.settimeout(2.0)  # 2 second timeout
            self.socket.connect(self.socket_path)
            self._connected = True
            logger.debug(f"Connected to IoT service at {self.socket_path}")
            return True
        except FileNotFoundError:
            logger.debug(f"IoT service socket not found: {self.socket_path}")
            self._connected = False
            return False
        except ConnectionRefusedError:
            logger.debug(f"Connection refused to {self.socket_path}")
            self._connected = False
            return False
        except Exception as e:
            logger.debug(f"Failed to connect to IoT service: {e}")
            self._connected = False
            return False
    
    def send_scan(self, scan_record):
        """
        Send scan data to Azure IoT service
        
        Args:
            scan_record (dict): Scan record with fields:
                - siteId: Site GUID
                - tagName: RFID tag EPC
                - latitude: GPS latitude
                - longitude: GPS longitude
                - speed: Vehicle speed
                - deviceId: Device identifier
                - antenna: Antenna number
                - barrier: Heading/bearing
                - Optional: rssi, comment, metadata
        
        Returns:
            bool: True if sent successfully, False otherwise
        """
        # Try to connect if not connected
        if not self._connected:
            if not self.connect():
                return False
        
        try:
            # Prepare message with type identifier
            message = {
                "type": "scan",
                "data": scan_record
            }
            
            # Send JSON message with newline delimiter
            json_data = json.dumps(message) + "\n"
            self.socket.sendall(json_data.encode('utf-8'))
            logger.debug(f"Sent scan to IoT service: {scan_record.get('tagName')}")
            return True
            
        except BrokenPipeError:
            logger.debug("IoT service connection broken, reconnecting...")
            self.socket = None
            self._connected = False
            # Try to reconnect and resend
            if self.connect():
                try:
                    message = {"type": "scan", "data": scan_record}
                    json_data = json.dumps(message) + "\n"
                    self.socket.sendall(json_data.encode('utf-8'))
                    logger.debug(f"Resent scan to IoT service: {scan_record.get('tagName')}")
                    return True
                except:
                    return False
            return False
        except ConnectionResetError:
            logger.debug("IoT service connection reset, reconnecting...")
            self.socket = None
            self._connected = False
            return False
        except Exception as e:
            logger.debug(f"Failed to send scan to IoT service: {e}")
            self._connected = False
            return False
    
    def close(self):
        """Close socket connection"""
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
            self._connected = False
    
    def is_available(self):
        """Check if IoT service socket is available"""
        return Path(self.socket_path).exists()
