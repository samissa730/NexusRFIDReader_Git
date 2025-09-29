import threading
import time
from typing import Dict, Any, List, Optional

from PySide6.QtCore import QThread, Signal
from sllurp.llrp import LLRP_DEFAULT_PORT, LLRPReaderConfig, LLRPReaderClient
from argparse import ArgumentParser

from settings import RFID_CONFIG
from ping3 import ping
from utils.logger import logger


def convert_to_unicode(obj):
    """
    Convert objects to unicode strings for JSON serialization.
    """
    if isinstance(obj, dict):
        return {
            convert_to_unicode(key): convert_to_unicode(value) 
            for key, value in obj.items()
        }
    elif isinstance(obj, list):
        return [convert_to_unicode(element) for element in obj]
    elif isinstance(obj, bytes):
        return obj.decode('utf-8')
    else:
        return obj


def _bytes_to_hex_string(value: Any) -> str:
    """
    Safely convert bytes-like EPC values to a hex string; otherwise str().
    """
    try:
        if isinstance(value, (bytes, bytearray)):
            return value.hex()
        return str(value)
    except Exception:
        return str(value)


def normalize_tag_fields(raw_tag: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize tag dictionary keys/values to the app's expected schema.
    Standard keys produced:
      - 'EPC-96': hex string EPC
      - 'AntennaID': int
      - 'PeakRSSI': int
      - 'LastSeenTimestampUTC': int (microseconds)
    Other original fields are preserved.
    """
    normalized: Dict[str, Any] = dict(raw_tag)

    # Normalize EPC
    epc_keys = ["EPC-96", "EPC", "epc", "TagID", "id"]
    epc_val = None
    for k in epc_keys:
        if k in raw_tag and raw_tag.get(k) not in (None, ""):
            epc_val = raw_tag.get(k)
            break
    if epc_val is not None:
        normalized["EPC-96"] = _bytes_to_hex_string(epc_val)

    # Normalize AntennaID
    ant_keys = ["AntennaID", "antenna", "antenna_id"]
    ant_val = None
    for k in ant_keys:
        if k in raw_tag:
            ant_val = raw_tag.get(k)
            break
    try:
        if ant_val is not None:
            normalized["AntennaID"] = int(ant_val)
    except Exception:
        pass

    # Normalize RSSI
    rssi_keys = ["PeakRSSI", "RSSI", "rssi", "peak_rssi"]
    rssi_val = None
    for k in rssi_keys:
        if k in raw_tag:
            rssi_val = raw_tag.get(k)
            break
    try:
        if rssi_val is not None:
            normalized["PeakRSSI"] = int(float(rssi_val))
    except Exception:
        pass

    # Normalize timestamp
    ts_keys = [
        "LastSeenTimestampUTC",
        "LastSeenTimestamp",
        "lastSeenTimestamp",
        "Timestamp",
        "timestamp",
    ]
    ts_val = None
    for k in ts_keys:
        if k in raw_tag:
            ts_val = raw_tag.get(k)
            break
    try:
        if ts_val is None:
            normalized["LastSeenTimestampUTC"] = int(time.time() * 1_000_000)
        else:
            normalized["LastSeenTimestampUTC"] = int(ts_val)
    except Exception:
        normalized["LastSeenTimestampUTC"] = int(time.time() * 1_000_000)

    return normalized


def parse_args(rfid_host: str) -> ArgumentParser:
    """Parse RFID reader arguments."""
    parser = ArgumentParser(description='Simple RFID Reader Inventory')
    parser.add_argument('host', help='hostname or IP address of RFID reader', 
                       default=[rfid_host], nargs='*')
    parser.add_argument('-p', '--port', default=RFID_CONFIG["port"], type=int,
                       help=f'port to connect to (default {RFID_CONFIG["port"]})')
    parser.add_argument('-n', '--report-every-n-tags', 
                       default=RFID_CONFIG["report_every_n_tags"], type=int,
                       dest='every_n', metavar='N',
                       help='issue a TagReport every N tags')
    parser.add_argument('-a', '--antennas', 
                       default=','.join(map(str, RFID_CONFIG["antennas"])),
                       help='comma-separated list of antennas to enable')
    parser.add_argument('-X', '--tx-power', default=RFID_CONFIG["tx_power"], type=int,
                       dest='tx_power',
                       help='Transmit power (default 0=max power)')
    parser.add_argument('-M', '--modulation', default=RFID_CONFIG["modulation"],
                       help=f'modulation (default {RFID_CONFIG["modulation"]})')
    parser.add_argument('-T', '--tari', default=RFID_CONFIG["tari"], type=int,
                       help='Tari value (default 0=auto)')
    parser.add_argument('-s', '--session', type=int, default=RFID_CONFIG["session"],
                       help=f'Gen2 session (default {RFID_CONFIG["session"]})')
    parser.add_argument('--mode-identifier', type=int,
                       help='ModeIdentifier value')
    parser.add_argument('-P', '--tag-population', type=int, 
                       default=RFID_CONFIG["tag_population"],
                       help=f"Tag Population value (default {RFID_CONFIG['tag_population']})")
    parser.add_argument('--impinj-search-mode', 
                       choices=['1', '2'],
                       default=RFID_CONFIG["impinj_search_mode"],
                       help=('Impinj extension: inventory search mode '
                             '(1=single, 2=dual)'))
    parser.add_argument('--impinj-reports', type=bool, 
                       default=RFID_CONFIG["impinj_reports"],
                       help='Enable Impinj tag report content (Phase angle, '
                            'RSSI, Doppler)')
    return parser.parse_args()


class RFID(QThread):
    """RFID Reader Thread for handling LLRP communication."""
    
    sig_msg = Signal(int)  # Signal for RFID status changes
    sig_tag_detected = Signal(dict)  # Signal for tag detection
    
    def __init__(self):
        super().__init__()
        self._b_stop = threading.Event()
        self.tag_data: Optional[List[Dict[str, Any]]] = None
        self.connectivity: Optional[bool] = None
        self.reader: Optional[LLRPReaderClient] = None
        self.host = RFID_CONFIG["reader_ip"]
        self.set_reader(RFID_CONFIG["reader_ip"], False)

    def set_reader(self, host: str, status: bool):
        """Configure RFID reader with specified host and status."""
        self.connectivity = status
        self.host = host
        
        try:
            args = parse_args(host)
            enabled_antennas = [int(x.strip()) for x in args.antennas.split(',')]
            
            factory_args = dict(
                report_every_n_tags=args.every_n,
                antennas=enabled_antennas,
                tx_power=args.tx_power,
                tari=args.tari,
                session=args.session,
                mode_identifier=args.mode_identifier,
                tag_population=args.tag_population,
                start_inventory=True,
                tag_content_selector=RFID_CONFIG["tag_content_selector"],
                impinj_search_mode=args.impinj_search_mode,
                impinj_tag_content_selector=None,
            )

            # Parse host and port
            if ':' in host:
                host, port = host.split(':', 1)
                port = int(port)
            else:
                port = args.port
                
            config = LLRPReaderConfig(factory_args)
            self.reader = LLRPReaderClient(host, port, config)
            self.reader.add_tag_report_callback(self.tag_seen_callback)
            logger.debug(f"RFID reader configured for {host}:{port}")
            
        except Exception as e:
            logger.error(f"Error configuring RFID reader: {e}")
            self.reader = None

    def tag_seen_callback(self, reader, tags):
        """Callback function for when tags are detected."""
        if tags:
            # Convert and normalize each tag for UI/storage compatibility
            converted = convert_to_unicode(tags)
            self.tag_data = [normalize_tag_fields(tag) for tag in converted]
            logger.debug(f"Tags detected: {len(tags)} tags")
            
            # Emit signal for each tag
            for tag in self.tag_data:
                self.sig_tag_detected.emit(tag)
            
            # Emit general status signal
            self.sig_msg.emit(3)  # Tag detected status

    def run(self):
        """Main RFID thread loop."""
        logger.info("Starting RFID reader thread")

        # Single non-blocking initial connection attempt
        try:
            if self.reader:
                self.reader.connect()
                self.connectivity = True
                self.sig_msg.emit(1)  # Connected
                logger.info("RFID reader connected successfully")
        except Exception as e:
            logger.error(f"RFID connection failed: {e}")
            self.connectivity = False
            self.sig_msg.emit(2)  # Disconnected

        # Main monitoring loop
        while not self._b_stop.is_set():
            try:
                # Ping the RFID reader to check connectivity
                response_time = ping(self.host, timeout=3)
                if response_time is not None:
                    if self.connectivity is False:
                        # Reconnect if we were disconnected
                        LLRPReaderClient.disconnect_all_readers()
                        self.reader = None
                        self.set_reader(self.host, True)
                        try:
                            if self.reader:
                                self.reader.connect()
                                self.connectivity = True
                                self.sig_msg.emit(1)  # Connected status
                        except Exception as e:
                            logger.error(f"RFID reconnect failed: {e}")
                else:
                    if self.connectivity is True:
                        self.connectivity = False
                        self.sig_msg.emit(2)  # Disconnected status
                        
            except Exception as e:
                logger.error(f"RFID monitoring error: {e}")
                if self.connectivity is True:
                    self.connectivity = False
                    self.sig_msg.emit(2)  # Disconnected status
                    
            time.sleep(0.1)

    def stop(self):
        """Stop the RFID reader thread."""
        logger.info("Stopping RFID reader thread")
        self._b_stop.set()
        self.wait()
        LLRPReaderClient.disconnect_all_readers()
        logger.info("RFID reader thread stopped")

    def get_connectivity_status(self) -> bool:
        """Get current connectivity status."""
        return self.connectivity if self.connectivity is not None else False

    def get_last_tag_data(self) -> Optional[List[Dict[str, Any]]]:
        """Get the last detected tag data."""
        return self.tag_data

    def is_connected(self) -> bool:
        """Check if RFID reader is connected."""
        return self.connectivity is True
