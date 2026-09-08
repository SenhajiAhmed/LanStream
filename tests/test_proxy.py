"""
Unit test for Local HLS Stream Proxy
"""
import http.server
import os
os.environ["no_proxy"] = "*"
os.environ["NO_PROXY"] = "*"
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

    def test_m3u8_rewrite_fmp4_and_media_tags(self):
        """Tests that #EXT-X-MAP and #EXT-X-MEDIA URIs are properly rewritten through proxy."""
        from services.stream_proxy_service import StreamProxyHandler
        master = (
            "#EXTM3U\n"
            "#EXT-X-VERSION:7\n"
            "#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID=\"audio-1\",NAME=\"English\",URI=\"audio_1.m3u8\"\n"
            "#EXT-X-STREAM-INF:BANDWIDTH=800000,RESOLUTION=640x360,AUDIO=\"audio-1\"\n"
            "video_360p.m3u8\n"
        )
        rewritten = StreamProxyHandler._rewrite_m3u8_content(
            master, "https://cdn.example.com/playlist/master.m3u8", proxy_base="http://127.0.0.1:8080"
        )
        self.assertIn("URI=\"http://127.0.0.1:8080/proxy?url=https%3A%2F%2Fcdn.example.com%2Fplaylist%2Faudio_1.m3u8\"", rewritten)
        self.assertIn("http://127.0.0.1:8080/proxy?url=https%3A%2F%2Fcdn.example.com%2Fplaylist%2Fvideo_360p.m3u8", rewritten)

        media = (
            "#EXTM3U\n"
            "#EXT-X-VERSION:7\n"
            "#EXT-X-MAP:URI=\"video_360p_init.html\"\n"
            "#EXTINF:6.000,\n"
            "video_360p_000.html\n"
        )
        rewritten_media = StreamProxyHandler._rewrite_m3u8_content(
            media, "https://cdn.example.com/playlist/video_360p.m3u8", proxy_base="http://127.0.0.1:8080"
        )
        self.assertIn("URI=\"http://127.0.0.1:8080/proxy?url=https%3A%2F%2Fcdn.example.com%2Fplaylist%2Fvideo_360p_init.html\"", rewritten_media)
        self.assertIn("http://127.0.0.1:8080/proxy?url=https%3A%2F%2Fcdn.example.com%2Fplaylist%2Fvideo_360p_000.html", rewritten_media)
        print("[Test] fMP4 map and media tags rewrite verified successfully")

    def test_m3u8_rewrite_variant_filtering(self):
        """Tests that when selected_vid is provided, only that variant is kept in master playlist."""
        from services.stream_proxy_service import StreamProxyHandler
        master = (
            "#EXTM3U\n"
            "#EXT-X-VERSION:7\n"
            "#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID=\"audio-1\",NAME=\"English\",URI=\"audio_1.m3u8\"\n"
            "#EXT-X-STREAM-INF:BANDWIDTH=5000000,RESOLUTION=3840x2160,AUDIO=\"audio-1\"\n"
            "video_4k.m3u8\n"
            "#EXT-X-STREAM-INF:BANDWIDTH=2500000,RESOLUTION=1920x1080,AUDIO=\"audio-1\"\n"
            "video_1080p.m3u8\n"
            "#EXT-X-STREAM-INF:BANDWIDTH=800000,RESOLUTION=640x360,AUDIO=\"audio-1\"\n"
            "video_360p.m3u8\n"
        )
        # Select 360p (variant 3)
        rewritten = StreamProxyHandler._rewrite_m3u8_content(
            master, "https://cdn.example.com/master.m3u8", proxy_base="http://127.0.0.1:8080", selected_vid=3
        )
        self.assertIn("video_360p.m3u8", rewritten)
        self.assertNotIn("video_4k.m3u8", rewritten)
        self.assertNotIn("video_1080p.m3u8", rewritten)
        # Audio track must be preserved
        self.assertIn("audio_1.m3u8", rewritten)
        print("[Test] Master playlist variant filtering verified successfully")

    def test_segment_cache_resilience(self):
        """Tests that segments are cached in memory so interruptions in connectivity are absorbed."""
        from services.stream_proxy_service import StreamProxyHandler
        test_url = "http://upstream.fake/segment_001.ts"
        fake_data = b"MPEGTS_PAYLOAD_CACHE_TEST"
        StreamProxyHandler.segment_cache[test_url] = (fake_data, "video/mp2t")
        StreamProxyHandler.segment_cache_keys.append(test_url)

        proxy_url = f"http://127.0.0.1:{self.proxy.port}/proxy?url={requests.utils.quote(test_url, safe='')}"
        r = requests.get(proxy_url, timeout=5)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.content, fake_data)
        self.assertEqual(r.headers.get("Content-Type"), "video/mp2t")
        print("[Test] In-memory segment cache resilience verified successfully")


if __name__ == "__main__":
    unittest.main()
