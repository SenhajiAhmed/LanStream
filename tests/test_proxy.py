"""
Unit test for Local HLS Stream Proxy
"""
import http.server
import os
import subprocess
import time
import unittest
import requests

from models.video import Video
from services.stream_proxy_service import StreamProxyService

SAMPLE_TS_PATH = "output/test_sample.ts"


class MockUpstreamHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path.endswith(".m3u8"):
            content = (
                "#EXTM3U\n"
                "#EXT-X-VERSION:3\n"
                "#EXT-X-TARGETDURATION:2\n"
                "#EXT-X-MEDIA-SEQUENCE:0\n"
                "#EXTINF:1.0,\n"
                "test_sample.ts\n"
                "#EXT-X-ENDLIST\n"
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.apple.mpegurl")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        elif self.path.endswith(".ts"):
            if os.path.exists(SAMPLE_TS_PATH):
                with open(SAMPLE_TS_PATH, "rb") as f:
                    data = f.read()
            else:
                data = b"\x47\x1f\xff\x10" + (b"\xff" * 184)
            self.send_response(200)
            self.send_header("Content-Type", "video/mp2t")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_response(404)
            self.end_headers()


class TestStreamProxy(unittest.TestCase):
    mock_server = None
    mock_thread = None

    @classmethod
    def setUpClass(cls):
        # Generate sample TS if not present
        if not os.path.exists(SAMPLE_TS_PATH):
            subprocess.run([
                "ffmpeg", "-f", "lavfi", "-i", "testsrc=duration=1:size=160x120:rate=5",
                "-f", "lavfi", "-i", "sine=duration=1:frequency=440",
                "-c:v", "libx264", "-c:a", "aac", "-f", "mpegts", SAMPLE_TS_PATH, "-y"
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # Start mock upstream server on port 8898
        cls.mock_server = http.server.ThreadingHTTPServer(("127.0.0.1", 8898), MockUpstreamHandler)
        import threading
        cls.mock_thread = threading.Thread(target=cls.mock_server.serve_forever, daemon=True)
        cls.mock_thread.start()

        # Sample video pointing to local mock upstream
        video = Video(
            id="test_vid",
            title="حرامية في كي جي تو",
            page_url="http://127.0.0.1:8898/see",
            stream_url="http://127.0.0.1:8898/master.m3u8"
        )
        cls.video = video

        # Start proxy
        cls.proxy = StreamProxyService(video=video, port=8899)
        cls.proxy.start(background=True)
        time.sleep(0.5)

    @classmethod
    def tearDownClass(cls):
        cls.proxy.stop()
        if cls.mock_server:
            cls.mock_server.shutdown()
            cls.mock_server.server_close()
        if os.path.exists(SAMPLE_TS_PATH):
            try:
                os.remove(SAMPLE_TS_PATH)
            except OSError:
                pass

    def test_web_player(self):
        """Tests that GET / serves the HTML5 player page."""
        url = self.proxy.get_web_url()
        r = requests.get(url, timeout=5)
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/html", r.headers.get("Content-Type", ""))
        self.assertIn("Hls.isSupported", r.text)
        self.assertIn("حرامية في كي جي تو", r.text)
        print("\n[Test] Web player HTML verified at:", url)

    def test_playlist_rewrite(self):
        """Tests that GET /playlist.m3u8 serves the rewritten playlist with /proxy URLs."""
        url = self.proxy.get_stream_url()
        r = requests.get(url, timeout=10)
        self.assertEqual(r.status_code, 200)
        self.assertIn("#EXTM3U", r.text)
        self.assertIn("/proxy?url=", r.text)
        self.assertEqual(r.headers.get("Access-Control-Allow-Origin"), "*")
        print("[Test] Rewritten playlist verified at:", url)

    def test_segment_proxy(self):
        """Tests that the proxy forwards upstream segments and keys."""
        playlist_url = self.proxy.get_stream_url()
        r_pl = requests.get(playlist_url, timeout=10)
        lines = [line.strip() for line in r_pl.text.splitlines() if "/proxy?url=" in line]
        self.assertGreater(len(lines), 0, "Playlist should contain at least one /proxy line")

        first_proxy_url = lines[0]
        if not first_proxy_url.startswith("http"):
            first_proxy_url = f"http://127.0.0.1:{self.proxy.port}{first_proxy_url}"

        r_res = requests.get(first_proxy_url, timeout=15)
        self.assertEqual(r_res.status_code, 200)
        self.assertEqual(r_res.headers.get("Access-Control-Allow-Origin"), "*")
        print("[Test] Proxy resource fetched with status 200 from:", first_proxy_url[:80], "...\n")

    def test_direct_mp4_stream(self):
        """Tests that GET /stream.mp4 serves a live remuxed MP4 stream for Samsung Smart TVs."""
        mp4_url = self.proxy.get_mp4_url()
        r = requests.get(mp4_url, stream=True, timeout=15)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers.get("Content-Type"), "video/mp4")
        self.assertEqual(r.headers.get("Access-Control-Allow-Origin"), "*")

        # Read first 16KB to verify mp4 ftyp container
        chunk = next(r.iter_content(chunk_size=16384))
        self.assertGreater(len(chunk), 0, "Should receive MP4 bytes")
        self.assertIn(b"ftyp", chunk[:32], "MP4 stream header must contain 'ftyp' box")
        r.close()
        print("[Test] Direct MP4 stream verified successfully with ftyp box at:", mp4_url)


if __name__ == "__main__":
    unittest.main()
