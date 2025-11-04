import threading
import time

from PySide6.QtCore import QThread, Signal
from sllurp.llrp import LLRP_DEFAULT_PORT, LLRPReaderConfig, LLRPReaderClient
from ping3 import ping

from settings import RFID_CONFIG, update_rfid_host, reload_config
from utils.logger import logger
from utils.rfid_discovery import discover_rfid_readers


def _parse_args_from_settings(rfid_cfg):
    cfg = {
        'every_n': rfid_cfg.get('report_every_n_tags', 1),
        'antennas': rfid_cfg.get('antennas', '1'),
        'tx_power': rfid_cfg.get('tx_power', 0),
        'tari': rfid_cfg.get('tari', 0),
        'session': rfid_cfg.get('session', 1),
        'mode_identifier': rfid_cfg.get('mode_identifier', None),
        'tag_population': rfid_cfg.get('tag_population', 4),
        'impinj_search_mode': rfid_cfg.get('impinj_search_mode', None),
        'impinj_reports': rfid_cfg.get('impinj_reports', False),
        'port': rfid_cfg.get('port', LLRP_DEFAULT_PORT),
        'host': rfid_cfg.get('host', '127.0.0.1')
    }
    return cfg


def _convert_to_unicode(obj):
    if isinstance(obj, dict):
        return { _convert_to_unicode(k): _convert_to_unicode(v) for k, v in obj.items() }
    elif isinstance(obj, list):
        return [_convert_to_unicode(e) for e in obj]
    elif isinstance(obj, bytes):
        return obj.decode('utf-8')
    else:
        return obj


class RFID(QThread):

    sig_msg = Signal(int)

    def __init__(self):
        super().__init__()
        self._b_stop = threading.Event()
        self.tag_data = None
        self.connectivity = None
        self.reader = None
        self._cfg = _parse_args_from_settings(RFID_CONFIG if isinstance(RFID_CONFIG, dict) else {})
        self.host = self._cfg['host']
        self._set_reader(self.host, False)
        self._discovery_in_progress = False

    def set_reader(self, host, status):
        self._set_reader(host, status)

    def _set_reader(self, host, status):
        self.connectivity = status
        self.host = host
        args = _parse_args_from_settings(RFID_CONFIG if isinstance(RFID_CONFIG, dict) else {})
        enabled_antennas = [int(x.strip()) for x in str(args['antennas']).split(',')]
        factory_args = dict(
            report_every_n_tags=args['every_n'],
            antennas=enabled_antennas,
            tx_power=args['tx_power'],
            tari=args['tari'],
            session=args['session'],
            mode_identifier=args['mode_identifier'],
            tag_population=args['tag_population'],
            start_inventory=True,
            tag_content_selector={
                'EnableROSpecID': True,
                'EnableSpecIndex': True,
                'EnableInventoryParameterSpecID': True,
                'EnableAntennaID': True,
                'EnableChannelIndex': True,
                'EnablePeakRSSI': True,
                'EnableFirstSeenTimestamp': True,
                'EnableLastSeenTimestamp': True,
                'EnableTagSeenCount': True,
                'EnableAccessSpecID': True,
                'C1G2EPCMemorySelector': {
                    'EnableCRC': True,
                    'EnablePCBits': True,
                }
            },
            impinj_search_mode=args['impinj_search_mode'],
            impinj_tag_content_selector=None,
        )

        port = args['port']
        config = LLRPReaderConfig(factory_args)
        self.reader = LLRPReaderClient(host, port, config)
        self.reader.add_tag_report_callback(self.tag_seen_callback)
        logger.debug("RFID initialized.")

    def tag_seen_callback(self, reader, tags):
        if tags:
            # logger.debug(f"RFID tags detected: {len(tags)} tags")
            self.tag_data = _convert_to_unicode(tags)
            # logger.debug(f"Tag data: {self.tag_data}")
            self.sig_msg.emit(3)
        else:
            logger.debug("RFID callback called but no tags found")

    def run(self):
        logger.debug(f"RFID thread starting, attempting to connect to {self.host}:{self._cfg['port']}")
        # Emit initial "Disconnected" status if connectivity is False or None
        if self.connectivity is not True:
            self.connectivity = False
            self.sig_msg.emit(2)
        
        while not self._b_stop.is_set():
            try:
                logger.debug("Attempting RFID reader connection...")
                self.reader.connect()
                logger.info("RFID reader connected successfully")
                break
            except Exception as e:
                logger.debug(f"RFID connection attempt failed: {e}")
                if self.connectivity is True:
                    self.connectivity = False
                    self.sig_msg.emit(2)
                elif self.connectivity is not False:
                    # Handle None case - ensure it's set to False and emit Disconnected
                    self.connectivity = False
                    self.sig_msg.emit(2)
            time.sleep(.1)

        if self.connectivity is False:
            self.connectivity = True
            self.sig_msg.emit(1)
            logger.info("RFID reader status changed to connected")

        while not self._b_stop.is_set():
            try:
                response_time = ping(self.host, timeout=3)
                if response_time is not None:
                    if self.connectivity is False:
                        LLRPReaderClient.disconnect_all_readers()
                        self.reader = None
                        self._set_reader(self.host, True)
                        self.reader.connect()
                        self.sig_msg.emit(1)
                        # Reset discovery tracking when connection is restored
                        self._discovery_in_progress = False
                else:
                    if self.connectivity is True:
                        self.connectivity = False
                        self.sig_msg.emit(2)
                    # Check if we should trigger discovery: disconnected and ping failed
                    elif self.connectivity is False:
                        # Continuously attempt discovery if not already in progress
                        if not self._discovery_in_progress:
                            self._attempt_discovery()
            except Exception:
                if self.connectivity is True:
                    self.connectivity = False
                    self.sig_msg.emit(2)
                # Also check for discovery on ping exceptions
                elif self.connectivity is False:
                    # Continuously attempt discovery if not already in progress
                    if not self._discovery_in_progress:
                        self._attempt_discovery()
            time.sleep(.1)

    def _attempt_discovery(self):
        """Attempt to discover a new RFID reader when disconnected. Runs continuously until a reader is found."""
        if self._discovery_in_progress:
            return
        
        self._discovery_in_progress = True
        logger.info("RFID disconnected and ping failed - starting continuous discovery for RFID reader")
        
        # Keep trying until we find a reader or connection is restored
        while not self._b_stop.is_set() and self.connectivity is False:
            try:
                # Discover RFID readers on the network
                new_host = discover_rfid_readers(interface="eth0", subnet="169.254.0.0/16")
                
                if new_host:
                    if new_host != self.host:
                        logger.info(f"Found new RFID reader at {new_host}, updating settings and reconnecting")
                        
                        # Update settings with the new host
                        if update_rfid_host(new_host):
                            # Reload config to get updated host
                            reload_config()
                            # Update local config
                            self._cfg = _parse_args_from_settings(RFID_CONFIG if isinstance(RFID_CONFIG, dict) else {})
                            
                            # Disconnect current reader and set up new one
                            try:
                                LLRPReaderClient.disconnect_all_readers()
                            except Exception:
                                pass
                            
                            self.reader = None
                            self.host = new_host
                            self._set_reader(self.host, False)
                            
                            # Attempt to connect to the new reader
                            try:
                                logger.info(f"Attempting to connect to newly discovered reader at {self.host}")
                                self.reader.connect()
                                self.connectivity = True
                                self.sig_msg.emit(1)
                                logger.info(f"Successfully connected to newly discovered RFID reader at {self.host}")
                                break  # Exit discovery loop on successful connection
                            except Exception as e:
                                logger.warning(f"Failed to connect to newly discovered reader at {self.host}: {e}")
                                self.connectivity = False
                                self.sig_msg.emit(2)
                                # Continue discovery loop to retry
                        else:
                            logger.error("Failed to update RFID host in settings")
                            # Continue discovery loop to retry
                    else:
                        # Same host discovered - try to reconnect (network issue may be resolved)
                        logger.info(f"Discovered reader is the same as current host: {self.host}, attempting to reconnect")
                        try:
                            LLRPReaderClient.disconnect_all_readers()
                        except Exception:
                            pass
                        
                        self.reader = None
                        self._set_reader(self.host, False)
                        
                        try:
                            logger.info(f"Attempting to reconnect to reader at {self.host}")
                            self.reader.connect()
                            self.connectivity = True
                            self.sig_msg.emit(1)
                            logger.info(f"Successfully reconnected to RFID reader at {self.host}")
                            break  # Exit discovery loop on successful connection
                        except Exception as e:
                            logger.warning(f"Failed to reconnect to reader at {self.host}: {e}")
                            self.connectivity = False
                            self.sig_msg.emit(2)
                            # Continue discovery loop to retry
                else:
                    logger.debug("No RFID reader found during discovery, retrying...")
                    # Small delay before retry to avoid tight loop (but still continuous)
                    time.sleep(1)
                    
            except Exception as e:
                logger.error(f"Error during RFID discovery: {e}")
                # Small delay before retry on error
                time.sleep(1)
        
        self._discovery_in_progress = False
        if self.connectivity is True:
            logger.info("RFID discovery completed - reader connected")
        else:
            logger.debug("RFID discovery stopped (thread stopping or connection restored)")

    def stop(self):
        self._b_stop.set()
        self.wait()
        LLRPReaderClient.disconnect_all_readers()


