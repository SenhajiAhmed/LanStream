"""
Stream Extractor Service
"""
import os
import re
from typing import Optional
import requests

from config import DEFAULT_HEADERS, DEFAULT_TIMEOUT
from models.video import Video


class ExtractorService:
    """Extracts direct HLS / video stream URLs from video detail pages and embeds."""

    def __init__(self, logger=None):
        self.logger = logger
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self.output_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output"
        )
        os.makedirs(self.output_dir, exist_ok=True)

    def extract_stream(self, video: Video) -> Optional[str]:
        """Resolves the direct playable stream URL for a given Video."""
        if self.logger:
            self.logger.info(f"Resolving video stream for ID: {video.id} ({video.title})")

        # Provider: Cineby / Cinejoy uses headless Chrome sniffer with early-exit
        if getattr(video, "provider", None) in ["cineby", "cinejoy"] or "cinejoy.to" in (video.page_url or ""):
            return self._extract_cinejoy_stream(video)

        # Step 1: Fetch the watch page
        try:
            resp = self.session.get(video.page_url, timeout=DEFAULT_TIMEOUT)
            resp.raise_for_status()
            html = resp.text
        except requests.RequestException as e:
            if self.logger:
                self.logger.error(f"Failed to fetch video page {video.page_url}: {e}")
            return None

        # Step 2: Find embed iframes (e.g. 1vid.xyz, dood, etc.)
        iframe_pattern = r'<iframe[^>]+src=["\']([^"\']+)["\']'
        iframes = re.findall(iframe_pattern, html, re.IGNORECASE)

        # Also check for direct m3u8 in page
        direct_m3u8 = self._find_m3u8(html)
        if direct_m3u8:
            video.stream_url = direct_m3u8
            return direct_m3u8

        if not iframes:
            if self.logger:
                self.logger.warning("No embedded players or iframes found on page")
            return None

        # Step 3: Resolve the primary embed
        embed_url = iframes[0]
        if embed_url.startswith("//"):
            embed_url = "https:" + embed_url
        video.embed_url = embed_url

        if self.logger:
            self.logger.info(f"Found player embed: {embed_url}")

        stream_url = self._extract_from_embed(embed_url, referer=video.page_url)
        if stream_url:
            video.stream_url = stream_url
            if self.logger:
                self.logger.info("Successfully extracted stream URL!")
            return stream_url

        if self.logger:
            self.logger.warning("Could not extract direct stream URL from embed")
        return None

    def _extract_from_embed(self, embed_url: str, referer: str) -> Optional[str]:
        """Extracts stream from an embed page (unpacking obfuscated JS if necessary)."""
        headers = {
            "User-Agent": DEFAULT_HEADERS["User-Agent"],
            "Referer": referer,
        }

        try:
            resp = self.session.get(embed_url, headers=headers, timeout=DEFAULT_TIMEOUT)
            resp.raise_for_status()
            embed_html = resp.text
        except requests.RequestException as e:
            if self.logger:
                self.logger.error(f"Failed to load embed {embed_url}: {e}")
            return None

        # 1. Direct search in embed HTML
        m3u8 = self._find_m3u8(embed_html)
        if m3u8:
            return m3u8

        # 2. Check for Dean Edwards packed JavaScript: eval(function(p,a,c,k,e,d)...)
        packed_match = re.search(
            r'eval\(function\(p,a,c,k,e,d\)\{.*?\}\s*\(\s*[\'\"](.*?)[\'\"]\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*[\'\"](.*?)[\'\"]\.split\([\'\"]\s*\|\s*[\'\"]\)',
            embed_html,
            re.DOTALL
        )
        if packed_match:
            try:
                p = packed_match.group(1)
                a = int(packed_match.group(2))
                c = int(packed_match.group(3))
                k = packed_match.group(4).split('|')
                unpacked_js = self._unpack_dean_edwards(p, a, c, k)
                
                m3u8_unpacked = self._find_m3u8(unpacked_js)
                if m3u8_unpacked:
                    return m3u8_unpacked
            except Exception as e:
                if self.logger:
                    self.logger.debug(f"Dean Edwards unpacking error: {e}")

        return None

    @staticmethod
    def _find_m3u8(text: str) -> Optional[str]:
        """Finds any .m3u8 stream URL in text."""
        matches = re.findall(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', text, re.IGNORECASE)
        if matches:
            # Prefer master.m3u8 if available
            for m in matches:
                if "master" in m.lower():
                    return m
            return matches[0]
        return None

    @staticmethod
    def _unpack_dean_edwards(p: str, a: int, c: int, k: list) -> str:
        """Unpacks JavaScript encoded with Dean Edwards Packer."""
        def base_n(num, b):
            digits = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
            return digits[num] if num < b else base_n(num // b, b) + digits[num % b]

        k_dict = {}
        for i in range(c):
            key = base_n(i, a)
            k_dict[key] = k[i] if i < len(k) and k[i] else key

        pattern = re.compile(r'\b\w+\b')
        return pattern.sub(lambda m: k_dict.get(m.group(0), m.group(0)), p)

    def _extract_cinejoy_stream(self, video: Video) -> Optional[str]:
        """Extracts stream from Cinejoy via headless Chrome sniffer."""
        if self.logger:
            self.logger.info(f"Extracting Cinejoy/Cineby stream for: {video.page_url}")

        from tests.test_sniff import run_with_undetected_chrome
        try:
            streams = run_with_undetected_chrome(
                url=video.page_url,
                output_dir=self.output_dir,
                duration=25,
                headless=True,
                early_exit=True,
                quiet=True
            )
        except Exception as e:
            if self.logger:
                self.logger.error(f"Cinejoy sniffer error: {e}")
            return None

        if not streams:
            streams_file = os.path.join(self.output_dir, "detected_streams.txt")
            if os.path.exists(streams_file):
                with open(streams_file, "r", encoding="utf-8") as f:
                    lines = [line.strip() for line in f if line.strip() and not line.startswith("#")]
                    streams = [{"url": line.split(" ", 1)[-1]} for line in lines]

        if not streams:
            return None

        master = None
        for s in streams:
            u = s.get("url", "")
            if "playlist/" in u and u.endswith(".m3u8"):
                master = u
                break
        if not master:
            for s in streams:
                u = s.get("url", "")
                if ".m3u8" in u:
                    master = u
                    break
        if not master and streams:
            master = streams[0].get("url")

        if master:
            video.stream_url = master
            video.embed_url = "https://cinejoy.to/"
            return master

        return None
