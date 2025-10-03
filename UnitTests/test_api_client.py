import unittest
from unittest import mock


class TestApiClient(unittest.TestCase):
    def setUp(self):
        from utils import api_client as api_module
        self.api = api_module

    def test_init_defaults(self):
        with mock.patch.object(self.api, 'API_CONFIG', {}):
            client = self.api.ApiClient()
            self.assertIsNone(client.token)
            self.assertIsNone(client.email)
            self.assertIsNone(client.password)
            self.assertIsNone(client.login_url)
            self.assertIsNone(client.health_url)
            self.assertIsNone(client.record_url)
            self.assertEqual(client.user_name, 'Unknown')

    def test_session_created_with_retry(self):
        client = self.api.ApiClient()
        with mock.patch('utils.api_client.requests.Session') as mock_sess, \
             mock.patch('utils.api_client.HTTPAdapter') as mock_adapter, \
             mock.patch('utils.api_client.Retry') as mock_retry:
            s = mock.MagicMock()
            mock_sess.return_value = s
            session = client._session()
            self.assertIs(session, s)
            mock_retry.assert_called()
            mock_adapter.assert_called()
            s.mount.assert_called()

    def test_headers_with_and_without_token(self):
        client = self.api.ApiClient()
        client.token = None
        h = client._headers()
        self.assertEqual(h['Content-Type'], 'application/json')
        self.assertEqual(h['accept'], 'application/json')
        self.assertEqual(h['idempotency-Key'], '1')
        self.assertNotIn('Authorization', h)
        client.token = 'abc'
        h2 = client._headers()
        self.assertEqual(h2['Authorization'], 'Bearer abc')

    def test_refresh_token_success(self):
        client = self.api.ApiClient()
        client.login_url = 'https://example/login'
        client.email = 'e'
        client.password = 'p'
        with mock.patch.object(client, '_session') as ms:
            sess = mock.MagicMock()
            ms.return_value = sess
            resp = mock.MagicMock()
            resp.status_code = 200
            resp.json.return_value = {
                'metadata': {'code': '200'},
                'result': {'acessToken': 'tok', 'userNameId': 'UserX'}
            }
            sess.post.return_value = resp
            ok = client.refresh_token()
            self.assertTrue(ok)
            self.assertEqual(client.token, 'tok')
            self.assertEqual(client.user_name, 'UserX')
            sess.close.assert_called()

    def test_refresh_token_failure_and_no_url(self):
        client = self.api.ApiClient()
        client.login_url = 'https://example/login'
        client.email = 'e'
        client.password = 'p'
        with mock.patch.object(client, '_session') as ms:
            sess = mock.MagicMock()
            ms.return_value = sess
            resp = mock.MagicMock()
            resp.status_code = 200
            resp.json.return_value = {'metadata': {'code': '400'}}
            sess.post.return_value = resp
            self.assertFalse(client.refresh_token())
        client.login_url = None
        self.assertFalse(client.refresh_token())

    def test_upload_health_success_and_failure(self):
        client = self.api.ApiClient()
        client.health_url = 'https://example/health'
        client.user_name = 'User'
        with mock.patch.object(client, '_session') as ms, \
             mock.patch.object(client, '_headers', return_value={'Authorization': 'x'}):
            sess = mock.MagicMock()
            ms.return_value = sess
            ok_resp = mock.MagicMock()
            ok_resp.json.return_value = {'metadata': {'code': '200'}}
            sess.post.return_value = ok_resp
            self.assertTrue(client.upload_health(True, 'Connected', 1.0, 2.0))
            bad_resp = mock.MagicMock()
            bad_resp.json.return_value = {'metadata': {'code': '400'}}
            sess.post.return_value = bad_resp
            self.assertFalse(client.upload_health(True, 'Connected', 1.0, 2.0))
        client.health_url = None
        self.assertFalse(client.upload_health(True, 'Connected', 1.0, 2.0))

    def test_upload_records_success_failure_exception(self):
        client = self.api.ApiClient()
        client.record_url = 'https://example/rec'
        # New API format - array of records instead of wrapped object
        payload = [
            {
                "rfidTag": "019817e3-daa8-76e0-a844-c639ed12ac32",
                "latitude": 33.00652,
                "longitude": -96.6927,
                "speed": 15,
                "deviceId": "1234-er45-65d5-86gh",
                "barrier": "50",
                "siteId": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                "isProcessed": False,
                "antenna": 1
            }
        ]
        with mock.patch.object(client, '_session') as ms, \
             mock.patch.object(client, '_headers', return_value={'Authorization': 'x'}):
            sess = mock.MagicMock()
            ms.return_value = sess
            ok_resp = mock.MagicMock()
            ok_resp.json.return_value = {'metadata': {'code': '200'}}
            sess.post.return_value = ok_resp
            self.assertTrue(client.upload_records(payload))
            bad_resp = mock.MagicMock()
            bad_resp.json.return_value = {'metadata': {'code': '400'}}
            sess.post.return_value = bad_resp
            self.assertFalse(client.upload_records(payload))
        with mock.patch.object(client, '_session') as ms:
            sess = mock.MagicMock()
            ms.return_value = sess
            sess.post.side_effect = Exception('net')
            self.assertFalse(client.upload_records(payload))
        client.record_url = None
        self.assertFalse(client.upload_records(payload))


if __name__ == '__main__':
    unittest.main()


