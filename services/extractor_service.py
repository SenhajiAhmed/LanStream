"""
Stream Extractor Service
"""
import os
import re
import urllib.parse
import base64
import json
import html
from typing import Optional, List, Dict, Any
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

        # Provider: WitAnime (pure requests)
        if getattr(video, "provider", None) == "witanime" or "witanime.you" in (video.page_url or ""):
            return self._extract_witanime_stream(video)

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

    def parse_hls_resolutions(self, master_url: str, referer: Optional[str] = None) -> List[Dict[str, Any]]:
        """Parses available video resolutions from an HLS master playlist."""
        if not master_url or ".m3u8" not in master_url.lower():
            return []

        headers = dict(DEFAULT_HEADERS)
        if referer:
            headers["Referer"] = referer
            if "cinejoy" in referer or "cineby" in referer:
                headers["Origin"] = referer.rstrip("/")
        if "ok.ru" in master_url or "odnoklassniki" in master_url:
            headers["Referer"] = "https://ok.ru/"

        try:
            resp = self.session.get(master_url, headers=headers, timeout=10)
            if resp.status_code != 200:
                return []
            text = resp.text
        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to fetch master playlist for resolutions: {e}")
            return []

        resolutions = []
        matches = list(re.finditer(r'#EXT-X-STREAM-INF:([^\n]+)\n([^\n]+)', text))
        for vid_idx, match in enumerate(matches, start=1):
            inf = match.group(1)
            sub_url = match.group(2).strip()
            if not sub_url.startswith("http"):
                sub_url = urllib.parse.urljoin(master_url, sub_url)

            res_m = re.search(r'RESOLUTION=(\d+)x(\d+)', inf)
            bw_m = re.search(r'BANDWIDTH=(\d+)', inf)

            width = int(res_m.group(1)) if res_m else 0
            height = int(res_m.group(2)) if res_m else 0
            bw = int(bw_m.group(1)) if bw_m else 0

            # Format friendly label
            hdr = "HDR " if "VIDEO-RANGE=PQ" in inf else ""
            codec = "HEVC" if "hvc" in inf else "H.264"
            if height >= 2160:
                name = f"4K Ultra HD ({width}x{height}, {hdr}{codec})"
            elif height >= 1080:
                name = f"1080p Full HD ({width}x{height}, {codec})"
            elif height >= 720:
                name = f"720p HD ({width}x{height}, {codec})"
            elif height >= 480:
                name = f"480p SD ({width}x{height}, {codec})"
            elif height > 0:
                name = f"{height}p ({width}x{height}, {codec})"
            else:
                name = f"Flux #{vid_idx} ({codec})"

            if bw > 0:
                mbps = round(bw / 1000000, 1)
                name += f" - {mbps} Mbps"

            resolutions.append({
                "index": vid_idx,
                "name": name,
                "width": width,
                "height": height,
                "bandwidth": bw,
                "codec": codec,
                "url": sub_url
            })

        return resolutions

    def get_anime_episodes(self, anime_url: str) -> List[Dict[str, Any]]:
        """Decrypts the list of episodes for a WitAnime series page via pure requests."""
        headers = dict(DEFAULT_HEADERS)
        headers["Referer"] = "https://witanime.you/"
        try:
            resp = self.session.get(anime_url, headers=headers, timeout=DEFAULT_TIMEOUT)
            if resp.status_code != 200:
                return []

            m = re.search(r'var\s+processedEpisodeData\s*=\s*["\']([^"\']+)["\']', resp.text)
            if not m:
                return []

            parts = m.group(1).split(".")
            if len(parts) != 2:
                return []

            part0 = base64.b64decode(parts[0]).decode("latin1")
            part1 = base64.b64decode(parts[1]).decode("latin1")

            decrypted = "".join(chr(ord(part0[i]) ^ ord(part1[i % len(part1)])) for i in range(len(part0)))
            episodes = json.loads(decrypted)
            return episodes
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error decrypting WitAnime episodes: {e}")
            return []

    def _extract_witanime_stream(self, video: Video) -> Optional[str]:
        """Extracts playable stream from WitAnime without browser driver (pure requests)."""
        headers = dict(DEFAULT_HEADERS)
        headers["Referer"] = "https://witanime.you/"

        target_url = video.page_url
        if "/anime/" in target_url:
            if video.selected_episode and video.selected_episode.get("url"):
                target_url = video.selected_episode["url"]
            else:
                episodes = self.get_anime_episodes(target_url)
                video.episodes = episodes
                if episodes:
                    target_url = episodes[0]["url"]
                    video.selected_episode = episodes[0]
                else:
                    if self.logger:
                        self.logger.warning(f"No episodes found for WitAnime title: {video.title}")
                    return None

        if self.logger:
            self.logger.info(f"Extracting WitAnime stream from episode: {target_url}")

        try:
            ep_resp = self.session.get(target_url, headers=headers, timeout=DEFAULT_TIMEOUT)
            if ep_resp.status_code != 200:
                return None
            ep_html = ep_resp.text
        except requests.RequestException as e:
            if self.logger:
                self.logger.error(f"Failed to fetch WitAnime episode page {target_url}: {e}")
            return None

        # Decode streaming servers from _zT and _zV
        zT_match = re.search(r'var\s+_zT\s*=\s*["\']([^"\']+)["\']', ep_html)
        zV_match = re.search(r'var\s+_zV\s*=\s*["\']([^"\']+)["\']', ep_html)

        decoded_servers = []
        if zT_match and zV_match:
            try:
                resources = json.loads(base64.b64decode(zT_match.group(1)).decode("utf-8"))
                configs = json.loads(base64.b64decode(zV_match.group(1)).decode("utf-8"))
                FRAMEWORK_HASH = "9933bd27-92ea-4ee9-807d-e612029d6318"

                items = []
                if isinstance(resources, dict) and isinstance(configs, dict):
                    for k, v in resources.items():
                        if k in configs:
                            items.append((k, v, configs[k]))
                elif isinstance(resources, list) and isinstance(configs, list):
                    for i in range(min(len(resources), len(configs))):
                        items.append((str(i), resources[i], configs[i]))

                for key, res_val, cfg in items:
                    try:
                        rev = res_val[::-1]
                        clean = re.sub(r'[^A-Za-z0-9+/=]', '', rev)
                        k_idx = int(base64.b64decode(cfg['k']))
                        offset = cfg['d'][k_idx]
                        decoded_bytes = base64.b64decode(clean)
                        url = decoded_bytes[:-offset].decode('utf-8')
                        if "yonaplay" in url:
                            url += "&apiKey=" + FRAMEWORK_HASH
                        decoded_servers.append({"name": key, "url": url})
                    except Exception:
                        pass
            except Exception as e:
                if self.logger:
                    self.logger.error(f"Error decoding WitAnime servers: {e}")

        # Fallback to iframes in page
        if not decoded_servers:
            iframe_pattern = r'<iframe[^>]+src=["\']([^"\']+)["\']'
            for src in re.findall(iframe_pattern, ep_html, re.IGNORECASE):
                if src.startswith("//"):
                    src = "https:" + src
                decoded_servers.append({"name": "iframe", "url": src})

        if self.logger:
            self.logger.info(f"Decoded {len(decoded_servers)} streaming servers from WitAnime")

        # 1. Try OK.ru first (pure HLS master playlist or MP4)
        for s in decoded_servers:
            u = s.get("url", "")
            if "ok.ru" in u:
                stream_url = self._extract_from_okru(u)
                if stream_url:
                    video.embed_url = u
                    video.stream_url = stream_url
                    return stream_url

        # 2. Try StreamWish / hgcloud (Dean Edwards unpacker)
        for s in decoded_servers:
            u = s.get("url", "")
            if any(host in u for host in ["hgcloud.to", "streamwish", "swish"]):
                stream_url = self._extract_from_streamwish(u)
                if stream_url:
                    video.embed_url = u
                    video.stream_url = stream_url
                    return stream_url

        # 3. Try Mp4Upload
        for s in decoded_servers:
            u = s.get("url", "")
            if "mp4upload" in u:
                stream_url = self._extract_from_mp4upload(u)
                if stream_url:
                    video.embed_url = u
                    video.stream_url = stream_url
                    return stream_url

        # 4. Try Yonaplay
        for s in decoded_servers:
            u = s.get("url", "")
            if "yonaplay" in u:
                stream_url = self._extract_from_embed(u, referer="https://witanime.you/")
                if stream_url:
                    video.embed_url = u
                    video.stream_url = stream_url
                    return stream_url

        # 5. Fallback to any server embed
        for s in decoded_servers:
            u = s.get("url", "")
            if u.startswith("http"):
                stream_url = self._extract_from_embed(u, referer="https://witanime.you/")
                if stream_url:
                    video.embed_url = u
                    video.stream_url = stream_url
                    return stream_url

        return None

    def _extract_from_okru(self, ok_url: str) -> Optional[str]:
        """Extracts direct HLS or MP4 stream URL from OK.ru video embed."""
        headers = {
            "User-Agent": DEFAULT_HEADERS["User-Agent"],
            "Referer": "https://witanime.you/",
        }
        try:
            resp = self.session.get(ok_url, headers=headers, timeout=DEFAULT_TIMEOUT)
            if resp.status_code != 200:
                return None

            m = re.search(r'data-options=["\']({.*?})["\']', resp.text)
            if m:
                data = json.loads(html.unescape(m.group(1)))
                flashvars = data.get("flashvars", {})
                meta = flashvars.get("metadata")
                if isinstance(meta, str):
                    try:
                        meta = json.loads(meta)
                    except Exception:
                        meta = {}
                elif not meta:
                    meta = flashvars

                # Check for master HLS playlist
                hls_url = meta.get("hlsManifestUrl") or meta.get("hlsMasterPlaylistUrl") or data.get("hlsManifestUrl")
                if hls_url:
                    return hls_url

                # Fallback to direct video files
                videos = meta.get("videos", []) or flashvars.get("videos", [])
                if videos:
                    for v in videos:
                        if v.get("name") in ["full", "hd"]:
                            return v.get("url")
                    return videos[-1].get("url")
        except Exception as e:
            if self.logger:
                self.logger.debug(f"OK.ru extraction failed: {e}")
        return None

    def _extract_from_mp4upload(self, url: str) -> Optional[str]:
        """Extracts direct video MP4 URL from Mp4Upload embed."""
        headers = {
            "User-Agent": DEFAULT_HEADERS["User-Agent"],
            "Referer": "https://witanime.you/",
        }
        try:
            resp = self.session.get(url, headers=headers, timeout=DEFAULT_TIMEOUT)
            if resp.status_code != 200:
                return None
            for mp4 in re.findall(r'https?://[^\s"\'<>]+\.mp4[^\s"\'<>]*', resp.text):
                if "/d/" in mp4 or "video.mp4" in mp4:
                    return mp4
        except Exception as e:
            if self.logger:
                self.logger.debug(f"Mp4Upload extraction failed: {e}")
        return None

    def _extract_from_streamwish(self, sw_url: str) -> Optional[str]:
        """Extracts direct HLS master URL from StreamWish / hgcloud embed."""
        headers = {
            "User-Agent": DEFAULT_HEADERS["User-Agent"],
            "Referer": "https://witanime.you/",
        }
        try:
            resp = self.session.get(sw_url, headers=headers, timeout=DEFAULT_TIMEOUT)
            if resp.status_code != 200:
                return None

            m3u8 = self._find_m3u8(resp.text)
            if m3u8:
                return m3u8

            packed_match = re.search(
                r'eval\(function\(p,a,c,k,e,d\)\{.*?\}\s*\(\s*[\'\"](.*?)[\'\"]\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*[\'\"](.*?)[\'\"]\.split\([\'\"]\s*\|\s*[\'\"]\)',
                resp.text,
                re.DOTALL
            )
            if packed_match:
                p = packed_match.group(1)
                a = int(packed_match.group(2))
                c = int(packed_match.group(3))
                k = packed_match.group(4).split('|')
                unpacked_js = self._unpack_dean_edwards(p, a, c, k)
                return self._find_m3u8(unpacked_js)
        except Exception as e:
            if self.logger:
                self.logger.debug(f"StreamWish extraction failed: {e}")
        return None
