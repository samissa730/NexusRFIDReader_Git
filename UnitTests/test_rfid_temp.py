import unittest
from unittest import mock
import sys
import os

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestRFIDConfig(unittest.TestCase):
    def setUp(self):
        from utils import rfid_temp as r
        self.r = r

    def test_parse_args_from_settings_defaults(self):
        """Test configuration parsing with default values"""
        args = self.r._parse_args_from_settings({})
        self.assertEqual(args['every_n'], 1)
        self.assertEqual(args['antennas'], '1')
        self.assertEqual(args['tx_power'], 0)
        self.assertEqual(args['tari'], 0)
        self.assertEqual(args['session'], 1)
        self.assertIsNone(args['mode_identifier'])
        self.assertEqual(args['tag_population'], 4)
        self.assertIsNone(args['impinj_search_mode'])
        self.assertFalse(args['impinj_reports'])
        self.assertEqual(args['port'], self.r.LLRP_DEFAULT_PORT)
        self.assertEqual(args['host'], '127.0.0.1')

    def test_parse_args_from_settings_custom(self):
        """Test configuration parsing with custom values"""
        custom_config = {
            'report_every_n_tags': 5,
            'antennas': '1,2,3',
            'tx_power': 20,
            'tari': 1,
            'session': 2,
            'mode_identifier': 'test_mode',
            'tag_population': 10,
            'impinj_search_mode': 'search_mode',
            'impinj_reports': True,
            'port': 8080,
            'host': '192.168.1.100'
        }
        args = self.r._parse_args_from_settings(custom_config)
        self.assertEqual(args['every_n'], 5)
        self.assertEqual(args['antennas'], '1,2,3')
        self.assertEqual(args['tx_power'], 20)
        self.assertEqual(args['tari'], 1)
        self.assertEqual(args['session'], 2)
        self.assertEqual(args['mode_identifier'], 'test_mode')
        self.assertEqual(args['tag_population'], 10)
        self.assertEqual(args['impinj_search_mode'], 'search_mode')
        self.assertTrue(args['impinj_reports'])
        self.assertEqual(args['port'], 8080)
        self.assertEqual(args['host'], '192.168.1.100')

    def test_create_rfid_config(self):
        """Test RFID configuration creation"""
        with mock.patch('utils.rfid_temp.LLRPReaderConfig') as mock_config:
            config, host, port = self.r.create_rfid_config()
            
            # Verify the configuration was created
            mock_config.assert_called_once()
            
            # Check that factory_args were passed correctly
            call_args = mock_config.call_args[0][0]
            self.assertIn('report_every_n_tags', call_args)
            self.assertIn('antennas', call_args)
            self.assertIn('tx_power', call_args)
            self.assertIn('tari', call_args)
            self.assertIn('session', call_args)
            self.assertIn('tag_population', call_args)
            self.assertIn('start_inventory', call_args)
            self.assertIn('tag_content_selector', call_args)
            self.assertIn('impinj_search_mode', call_args)
            self.assertIn('impinj_tag_content_selector', call_args)
            
            # Verify tag_content_selector structure
            tag_selector = call_args['tag_content_selector']
            self.assertTrue(tag_selector['EnableROSpecID'])
            self.assertTrue(tag_selector['EnableSpecIndex'])
            self.assertTrue(tag_selector['EnableInventoryParameterSpecID'])
            self.assertTrue(tag_selector['EnableAntennaID'])
            self.assertTrue(tag_selector['EnableChannelIndex'])
            self.assertTrue(tag_selector['EnablePeakRSSI'])
            self.assertTrue(tag_selector['EnableFirstSeenTimestamp'])
            self.assertTrue(tag_selector['EnableLastSeenTimestamp'])
            self.assertTrue(tag_selector['EnableTagSeenCount'])
            self.assertTrue(tag_selector['EnableAccessSpecID'])
            
            # Verify C1G2EPCMemorySelector
            c1g2_selector = tag_selector['C1G2EPCMemorySelector']
            self.assertTrue(c1g2_selector['EnableCRC'])
            self.assertTrue(c1g2_selector['EnablePCBits'])

    def test_antenna_parsing(self):
        """Test antenna string parsing"""
        # Test single antenna
        args = self.r._parse_args_from_settings({'antennas': '1'})
        self.assertEqual(args['antennas'], '1')
        
        # Test multiple antennas
        args = self.r._parse_args_from_settings({'antennas': '1,2,3,4'})
        self.assertEqual(args['antennas'], '1,2,3,4')
        
        # Test antennas with spaces
        args = self.r._parse_args_from_settings({'antennas': '1, 2, 3'})
        self.assertEqual(args['antennas'], '1, 2, 3')


if __name__ == '__main__':
    unittest.main()
