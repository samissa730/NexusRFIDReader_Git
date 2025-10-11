import time
import uuid
import json
from datetime import datetime

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from settings import API_CONFIG
from utils.logger import logger
from utils.crypto import decrypt_text


class ApiClient:

    def __init__(self):
        self.token = None
        self.token_expires_at = 0
        self.auth0_url = API_CONFIG.get('auth0_url')
        
        # Decrypt credentials when needed
        encrypted_client_id = API_CONFIG.get('client_id')
        encrypted_client_secret = API_CONFIG.get('client_secret')
        
        try:
            self.client_id = decrypt_text(encrypted_client_id) if encrypted_client_id else ""
            self.client_secret = decrypt_text(encrypted_client_secret) if encrypted_client_secret else ""
        except Exception as e:
            logger.error(f"Failed to decrypt credentials: {e}")
            self.client_id = ""
            self.client_secret = ""
        
        self.audience = API_CONFIG.get('audience')
        self.health_url = API_CONFIG.get('health_url')
        self.record_url = API_CONFIG.get('record_url')
        self.user_name = API_CONFIG.get('user_name', 'Unknown')

    def _session(self):
        retry_strategy = Retry(total=1, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["HEAD", "GET", "OPTIONS", "POST"])  # type: ignore
        adapter = HTTPAdapter(max_retries=retry_strategy)
        http = requests.Session()
        http.mount("https://", adapter)
        http.mount("http://", adapter)
        return http

    def refresh_token(self):
        """Get Auth0 access token using client credentials flow"""
        payload = json.dumps({
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "audience": self.audience,
            "grant_type": "client_credentials",
            "scope": "create:scans"
        })
        headers = {
            'content-type': 'application/json'
        }
        
        http = self._session()
        try:
            response = http.post(self.auth0_url, headers=headers, data=payload, timeout=10)
            response.raise_for_status()
            if response.status_code == 200:
                data = response.json()
                if 'access_token' in data:
                    self.token = data['access_token']
                    # Set expiration time (default to 1 hour if not provided)
                    expires_in = data.get('expires_in', 3600)
                    self.token_expires_at = time.time() + expires_in - 60  # Refresh 1 minute early
                    logger.debug('Received Auth0 token successfully!')
                    return True
        except Exception as e:
            logger.error(f"Auth0 token refresh failed: {e}")
        finally:
            http.close()
        return False

    def _headers(self):
        # Check if token needs refresh
        if not self.token or time.time() >= self.token_expires_at:
            if not self.refresh_token():
                logger.warning("Failed to refresh token, proceeding without authentication")
        
        headers = {
            "Content-Type": "application/json",
            "accept": "application/json",
            "idempotency-Key": "1"
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def upload_health(self, rfid_status: bool, gps_status_text: str, lat: float, lon: float):
        if not self.health_url:
            return False
        payload = {
            "userName": self.user_name,
            "rfidStatus": "Connected" if rfid_status else "Disconnected",
            "gpsStatus": gps_status_text,
            "macAddress": '-'.join(('%012X' % uuid.getnode())[i:i + 2] for i in range(0, 12, 2)),
            "lat": lat,
            "lng": lon,
            "dateTime": datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        }
        http = self._session()
        try:
            response = http.post(self.health_url, headers=self._headers(), json=payload, timeout=4)
            response.raise_for_status()
            data = response.json()
            # Check for new API response format
            if data.get('isSuccess') == True and data.get('status') == 'Ok':
                return True
            # Fallback to old format
            return data.get('metadata', {}).get('code') == '200'
        except Exception:
            logger.error("Uploading health data failed")
        finally:
            http.close()
        return False

    def upload_records(self, payload):
        if not self.record_url:
            return False
        http = self._session()
        try:
            response = http.post(self.record_url, headers=self._headers(), json=payload, timeout=4)
            response.raise_for_status()
            data = response.json()
            # Check for new API response format
            if data.get('isSuccess') == True and data.get('status') == 'Ok':
                return True
            # Fallback to old format
            return data.get('metadata', {}).get('code') == '200'
        except Exception:
            logger.error("Uploading records failed")
        finally:
            http.close()
        return False


