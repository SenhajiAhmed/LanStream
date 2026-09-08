"""
Unit tests for DeviceLoggerService and client diagnostic telemetry
"""
import os
os.environ["no_proxy"] = "*"
os.environ["NO_PROXY"] = "*"
import unittest
import requests

from services.device_logger_service import DeviceLoggerService
from services.stream_proxy_service import StreamProxyService
from models.video import Video


class TestDeviceLogger(unittest.TestCase):
    def setUp(self):
        self.logger = DeviceLoggerService(
            log_file="output/test_devices.log",
            json_file="output/test_devices.json"
        )

    def tearDown(self):
        for f in ["output/test_devices.log", "output/test_devices.json"]:
            if os.path.exists(f):
                os.remove(f)

    def test_parse_device_type(self):
        # Samsung Orsay / Series 3
        samsung_orsay_ua = "Mozilla/5.0 (SmartHub; SMART-TV; U; Linux/SmartTV; Maple2012) AppleWebKit/534.7"
        self.assertIn("Samsung Smart TV", self.logger.parse_device_type(samsung_orsay_ua))
        self.assertIn("Orsay", self.logger.parse_device_type(samsung_orsay_ua))

        # Samsung Tizen
        tizen_ua = "Mozilla/5.0 (SMART-TV; LINUX; Tizen 5.0) AppleWebKit/537.36"
        self.assertIn("Samsung Smart TV (Tizen 5.0)", self.logger.parse_device_type(tizen_ua))

        # VLC Player
        vlc_ua = "VLC/3.0.18 LibVLC/3.0.18"
        self.assertEqual(self.logger.parse_device_type(vlc_ua), "VLC Media Player")

        # iPhone
        iphone_ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148"
        self.assertIn("Apple iPhone", self.logger.parse_device_type(iphone_ua))

    def test_device_lifecycle_and_error_logging(self):
        ip = "192.168.1.102"
        ua = "Mozilla/5.0 (SmartHub; SMART-TV; Maple2012)"

        # 1. Incoming request
        self.logger.on_request(ip, 45410, ua, "GET", "/stream.mp4")
        self.assertIn(ip, self.logger.devices)
        self.assertEqual(self.logger.devices[ip]["total_requests"], 1)
        self.assertIn("Samsung Smart TV", self.logger.devices[ip]["device_type"])

        # 2. Response logging
        self.logger.on_response(ip, "/stream.mp4", 200, bytes_sent=1048576)
        self.assertEqual(self.logger.devices[ip]["bytes_sent"], 1048576)

        # 3. Server-side error logging
        self.logger.on_error(ip, "/stream.mp4", "ConnectionResetError", "Connection reset by peer")
        self.assertEqual(self.logger.devices[ip]["errors_count"], 1)
        self.assertEqual(len(self.logger.devices[ip]["errors"]), 1)
        self.assertEqual(self.logger.devices[ip]["errors"][0]["error_type"], "ConnectionResetError")

        # 4. Client-side telemetry reporting
        self.logger.on_client_telemetry(ip, {
            "event": "video_tag_error",
            "message": "MEDIA_ERR_SRC_NOT_SUPPORTED",
            "details": {"code": 4}
        })
        self.assertEqual(self.logger.devices[ip]["errors_count"], 2)

        # 5. File persistence checks
        self.assertTrue(os.path.exists("output/test_devices.log"))
        self.assertTrue(os.path.exists("output/test_devices.json"))


class TestProxyTelemetryEndpoint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        video = Video(id="f8ba4b0ce", title="Test Video", page_url="https://yam.ahwaktv.net/see.php?vid=f8ba4b0ce")
        video.stream_url = "https://1vid.online/fake.m3u8"
        cls.proxy = StreamProxyService(video=video, port=8911)
        cls.proxy.start(background=True)

    @classmethod
    def tearDownClass(cls):
        cls.proxy.stop()

    def test_api_log_endpoint(self):
        url = f"http://127.0.0.1:{self.proxy.port}/api/log"
        payload = {
            "event": "hls_error",
            "message": "bufferStalledError",
            "details": {"fatal": True}
        }
        headers = {"User-Agent": "Mozilla/5.0 (SmartHub; SMART-TV; Maple2012)"}
        r = requests.post(url, json=payload, headers=headers, timeout=5)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json().get("status"), "ok")


if __name__ == "__main__":
    unittest.main()
