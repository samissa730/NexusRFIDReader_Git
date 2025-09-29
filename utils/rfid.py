import threading
import time

from PySide6.QtCore import QThread, Signal
from sllurp.llrp import LLRP_DEFAULT_PORT, LLRPReaderConfig, LLRPReaderClient
from ping3 import ping

from settings import RFID_CONFIG
from utils.logger import logger


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
            self.tag_data = _convert_to_unicode(tags)
            self.sig_msg.emit(3)

    def run(self):
        while not self._b_stop.is_set():
            try:
                self.reader.connect()
                break
            except Exception:
                if self.connectivity is True:
                    self.connectivity = False
                    self.sig_msg.emit(2)
            time.sleep(.1)

        if self.connectivity is False:
            self.connectivity = True
            self.sig_msg.emit(1)

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
                else:
                    if self.connectivity is True:
                        self.connectivity = False
                        self.sig_msg.emit(2)
            except Exception:
                if self.connectivity is True:
                    self.connectivity = False
                    self.sig_msg.emit(2)
            time.sleep(.1)

    def stop(self):
        self._b_stop.set()
        self.wait()
        LLRPReaderClient.disconnect_all_readers()


