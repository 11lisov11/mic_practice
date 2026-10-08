"""Offline regression checks for JSON and authenticated text transport."""
import io
import unittest
import urllib.error
from unittest.mock import Mock, patch

from wifi_http_via_wsl import request_once


class TransportTests(unittest.TestCase):
    def run_request(self, raw, **overrides):
        response = Mock(status=200)
        response.read.return_value = raw
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        request = {"method": "GET", "url": "http://192.0.2.1/api/logs",
                   "headers": {"X-UNOQ-Control-Token": "test-token"}, **overrides}
        with patch("wifi_http_via_wsl.urllib.request.build_opener") as factory:
            factory.return_value.open.return_value = response
            result = request_once(request)
            sent = factory.return_value.open.call_args.args[0]
            self.assertEqual(sent.get_header("X-unoq-control-token"), "test-token")
        return result

    def test_json_default(self):
        self.assertEqual(self.run_request(b'{"ok": true}'),
                         {"code": 200, "payload": {"ok": True}})

    def test_text_response(self):
        self.assertEqual(self.run_request(b"CMD STOP\n", response_format="text"),
                         {"code": 200, "payload": "CMD STOP\n"})

    def test_text_http_error_preserves_status(self):
        error = urllib.error.HTTPError("http://192.0.2.1", 403, "Forbidden", {}, io.BytesIO(b"denied"))
        with patch("wifi_http_via_wsl.urllib.request.build_opener") as factory:
            factory.return_value.open.side_effect = error
            result = request_once({"method": "GET", "url": "http://192.0.2.1",
                                   "headers": {}, "response_format": "text"})
        self.assertEqual(result, {"code": 403, "payload": "denied"})

    def test_invalid_format_makes_no_request(self):
        with patch("wifi_http_via_wsl.urllib.request.build_opener") as factory:
            with self.assertRaises(ValueError):
                request_once({"response_format": "invalid"})
            factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
