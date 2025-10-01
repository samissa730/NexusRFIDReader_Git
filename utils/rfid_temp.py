from sllurp.llrp import LLRP_DEFAULT_PORT, LLRPReaderConfig, LLRPReaderClient
from settings import RFID_CONFIG


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


def create_rfid_config():
    """Create RFID configuration from settings"""
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
    return config, args['host'], port
