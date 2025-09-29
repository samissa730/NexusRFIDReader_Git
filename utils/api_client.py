import requests
import threading
import time
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from settings import API_CONFIG, FILTER_CONFIG
from utils.logger import logger
from utils.common import get_serial


class APIClient:
    """Handles API communication for RFID data upload and authentication."""
    
    def __init__(self):
        self.login_url = API_CONFIG["login_url"]
        self.record_upload_url = API_CONFIG["record_upload_url"]
        self.health_upload_url = API_CONFIG["health_upload_url"]
        self.timeout = API_CONFIG["timeout"]
        self.retry_count = API_CONFIG["retry_count"]
        self.retry_backoff = API_CONFIG["retry_backoff"]
        self.retry_status_codes = API_CONFIG["retry_status_codes"]
        
        # Authentication
        self.username: Optional[str] = None
        self.password: Optional[str] = None
        self.token: Optional[str] = None
        self.user_id: Optional[str] = None
        
        # Session for connection pooling
        self.session = self._create_session()
        
        # Device identification
        self.device_id = get_serial()
        self.mac_address = self._get_mac_address()
    
    def _create_session(self) -> requests.Session:
        """Create a requests session with retry strategy."""
        session = requests.Session()
        
        retry_strategy = Retry(
            total=self.retry_count,
            backoff_factor=self.retry_backoff,
            status_forcelist=self.retry_status_codes,
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST"]
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        return session
    
    def _get_mac_address(self) -> str:
        """Get MAC address for device identification."""
        try:
            mac = uuid.getnode()
            return '-'.join(('%012X' % mac)[i:i + 2] for i in range(0, 12, 2))
        except Exception as e:
            logger.error(f"Error getting MAC address: {e}")
            return "UNKNOWN"
    
    def authenticate(self, username: str, password: str) -> bool:
        """
        Authenticate with the API and get access token.
        
        Args:
            username: Username or email
            password: Password
            
        Returns:
            True if authentication successful, False otherwise
        """
        try:
            self.username = username
            self.password = password
            
            payload = {
                'email': username,
                'password': password
            }
            
            logger.info(f"Attempting authentication for user: {username}")
            
            response = self.session.post(
                self.login_url, 
                json=payload, 
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get('metadata', {}).get('code') == '200':
                    self.token = data['result']['acessToken']
                    self.user_id = data['result']['userNameId']
                    
                    logger.info("Authentication successful")
                    return True
                else:
                    logger.error(f"Authentication failed: {data.get('metadata', {}).get('message', 'Unknown error')}")
                    return False
            else:
                logger.error(f"Authentication failed with status code: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            return False
    
    def refresh_token(self) -> bool:
        """Refresh the authentication token."""
        if not self.username or not self.password:
            logger.error("Cannot refresh token: credentials not set")
            return False
        
        return self.authenticate(self.username, self.password)
    
    def upload_records(self, payload: Dict[str, Any]) -> bool:
        """
        Upload RFID scan records to the API.
        
        Args:
            payload: Record data payload
            
        Returns:
            True if upload successful, False otherwise
        """
        if not self.token:
            logger.error("Cannot upload records: not authenticated")
            return False
        
        try:
            headers = {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json"
            }
            
            logger.debug(f"Uploading {len(payload.get('data', []))} records")
            
            response = self.session.post(
                self.record_upload_url,
                headers=headers,
                json=payload,
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get('metadata', {}).get('code') == '200':
                    logger.info(f"Successfully uploaded {len(payload.get('data', []))} records")
                    return True
                else:
                    logger.error(f"Record upload failed: {data.get('metadata', {}).get('message', 'Unknown error')}")
                    return False
            else:
                logger.error(f"Record upload failed with status code: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Record upload error: {e}")
            return False
    
    def upload_health_data(self, rfid_status: str, gps_status: str, 
                          latitude: float, longitude: float) -> bool:
        """
        Upload device health data to the API.
        
        Args:
            rfid_status: RFID reader status
            gps_status: GPS status
            latitude: Current latitude
            longitude: Current longitude
            
        Returns:
            True if upload successful, False otherwise
        """
        if not self.token:
            logger.error("Cannot upload health data: not authenticated")
            return False
        
        try:
            headers = {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "userName": self.user_id,
                "rfidStatus": rfid_status,
                "gpsStatus": gps_status,
                "macAddress": self.mac_address,
                "lat": latitude,
                "lng": longitude,
                "dateTime": datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            }
            
            logger.debug("Uploading health data")
            
            response = self.session.post(
                self.health_upload_url,
                headers=headers,
                json=payload,
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get('metadata', {}).get('code') == '200':
                    logger.info("Health data uploaded successfully")
                    return True
                else:
                    logger.error(f"Health data upload failed: {data.get('metadata', {}).get('message', 'Unknown error')}")
                    return False
            else:
                logger.error(f"Health data upload failed with status code: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Health data upload error: {e}")
            return False
    
    def is_authenticated(self) -> bool:
        """Check if client is authenticated."""
        return self.token is not None
    
    def get_user_id(self) -> Optional[str]:
        """Get current user ID."""
        return self.user_id
    
    def get_token(self) -> Optional[str]:
        """Get current access token."""
        return self.token
    
    def close(self):
        """Close the session."""
        try:
            self.session.close()
            logger.info("API client session closed")
        except Exception as e:
            logger.error(f"Error closing API client: {e}")


class UploadManager:
    """Manages periodic data uploads and health reporting."""
    
    def __init__(self, api_client: APIClient, data_storage):
        self.api_client = api_client
        self.data_storage = data_storage
        self._stop_event = threading.Event()
        self._upload_thread: Optional[threading.Thread] = None
        self._health_thread: Optional[threading.Thread] = None
        
        # Upload intervals
        self.upload_interval = API_CONFIG["upload_interval"]
        self.health_interval = API_CONFIG["health_interval"]
        self.token_refresh_interval = API_CONFIG["token_refresh_interval"]
        
        # Last upload times
        self.last_upload_time = 0
        self.last_health_time = 0
        self.last_token_refresh = 0
    
    def start(self):
        """Start the upload manager threads."""
        if not self.api_client.is_authenticated():
            logger.error("Cannot start upload manager: API client not authenticated")
            return
        
        logger.info("Starting upload manager")
        
        # Start upload thread
        self._upload_thread = threading.Thread(target=self._upload_loop, daemon=True)
        self._upload_thread.start()
        
        # Start health reporting thread
        self._health_thread = threading.Thread(target=self._health_loop, daemon=True)
        self._health_thread.start()
    
    def stop(self):
        """Stop the upload manager threads."""
        logger.info("Stopping upload manager")
        self._stop_event.set()
        
        if self._upload_thread and self._upload_thread.is_alive():
            self._upload_thread.join(timeout=5)
        
        if self._health_thread and self._health_thread.is_alive():
            self._health_thread.join(timeout=5)
    
    def _upload_loop(self):
        """Main upload loop."""
        while not self._stop_event.is_set():
            try:
                current_time = time.time()
                
                # Check if it's time to upload
                if current_time - self.last_upload_time >= self.upload_interval:
                    self._upload_pending_records()
                    self.last_upload_time = current_time
                
                # Check if it's time to refresh token
                if current_time - self.last_token_refresh >= self.token_refresh_interval:
                    self.api_client.refresh_token()
                    self.last_token_refresh = current_time
                
                time.sleep(1)  # Check every second
                
            except Exception as e:
                logger.error(f"Error in upload loop: {e}")
                time.sleep(5)  # Wait before retrying
    
    def _health_loop(self):
        """Health reporting loop."""
        while not self._stop_event.is_set():
            try:
                current_time = time.time()
                
                # Check if it's time to report health
                if current_time - self.last_health_time >= self.health_interval:
                    self._upload_health_data()
                    self.last_health_time = current_time
                
                time.sleep(1)  # Check every second
                
            except Exception as e:
                logger.error(f"Error in health loop: {e}")
                time.sleep(5)  # Wait before retrying
    
    def _upload_pending_records(self):
        """Upload pending records from storage."""
        try:
            chunk_size = API_CONFIG["chunk_size"]
            records = self.data_storage.get_pending_records(chunk_size)
            
            if not records:
                return
            
            # Convert to payload format
            from utils.data_storage import convert_formatted_payload
            default_payload, custom_payload = convert_formatted_payload(records)
            
            # Upload default payload
            success = self.api_client.upload_records(default_payload)
            
            if success:
                # Mark records as uploaded
                record_ids = [record[0] for record in records]  # First column is ID
                self.data_storage.mark_records_uploaded(record_ids)
                
                logger.info(f"Successfully uploaded {len(records)} records")
            else:
                logger.warning(f"Failed to upload {len(records)} records")
                
        except Exception as e:
            logger.error(f"Error uploading pending records: {e}")
    
    def _upload_health_data(self):
        """Upload device health data."""
        try:
            # Get current device status
            rfid_status = "Connected"  # This should come from RFID reader
            gps_status = "Connected"   # This should come from GPS
            
            # Get current coordinates (this should come from GPS)
            latitude, longitude = 0.0, 0.0
            
            success = self.api_client.upload_health_data(
                rfid_status, gps_status, latitude, longitude
            )
            
            if success:
                logger.debug("Health data uploaded successfully")
            else:
                logger.warning("Failed to upload health data")
                
        except Exception as e:
            logger.error(f"Error uploading health data: {e}")
    
    def force_upload(self):
        """Force immediate upload of pending records."""
        self._upload_pending_records()
    
    def force_health_report(self):
        """Force immediate health data upload."""
        self._upload_health_data()
