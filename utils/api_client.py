import time
import uuid
from datetime import datetime

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from settings import API_CONFIG
from utils.logger import logger


class ApiClient:

    def __init__(self):
        self.token = API_CONFIG.get('token')
        self.email = API_CONFIG.get('email')
        self.password = API_CONFIG.get('password')
        self.login_url = API_CONFIG.get('login_url')
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
        if not self.login_url or not self.email or not self.password:
            return False
        payload = { 'email': self.email, 'password': self.password }
        http = self._session()
        try:
            response = http.post(self.login_url, json=payload, timeout=4)
            response.raise_for_status()
            if response.status_code == 200:
                data = response.json()
                if data.get('metadata', {}).get('code') == '200':
                    self.token = data['result'].get('acessToken')
                    self.user_name = data['result'].get('userNameId', self.user_name)
                    logger.debug('Received token successfully!')
                    return True
        except Exception:
            logger.error("Token refresh failed")
        finally:
            http.close()
        return False

    def _headers(self):
        headers = {"Content-Type": "application/json"}
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
            return data.get('metadata', {}).get('code') == '200'
        except Exception:
            logger.error("Uploading records failed")
        finally:
            http.close()
        return False


