"""
Local HLS Micro-Proxy Service (Option A)
=========================================
Runs a lightweight, zero-transcode HTTP relay server on LAN (0.0.0.0:port)
allowing any device on the same Wi-Fi (Smart TV, mobile phone, tablet, VLC)
to watch the extracted stream without referer or CORS restrictions.

Includes:
- Dynamic m3u8 playlist and AES-128 key URL rewriting
- Integrated modern HTML5 Web Player with Hls.js
- Local IP auto-discovery
- CORS headers enabled for all clients
- Threaded non-blocking server architecture
"""

import http.server
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import urllib.parse
from typing import Optional, List
import requests
import urllib3

from models.video import Video
from utils.logger import setup_logger
from services.device_logger_service import DeviceLoggerService


class StreamProxyHandler(http.server.BaseHTTPRequestHandler):
    """Handles HTTP requests for local HTML5 player, rewritten playlists, segments, and direct MP4 streams."""

    video: Video = None
    upstream_referer: str = "https://1vid.xyz/"
    session: requests.Session = None
    key_cache: dict = {}
    segment_cache: dict = {}
    segment_cache_keys: list = []
    MAX_SEGMENT_CACHE: int = 35
    active_processes: List[subprocess.Popen] = []
    device_logger: DeviceLoggerService = DeviceLoggerService.get_instance()

    def log_message(self, format, *args):
        """Silences standard BaseHTTPRequestHandler console spam."""
        pass

    def do_OPTIONS(self):
        """Responds to CORS pre-flight requests."""
        self.send_response(200)
        self._send_cors_headers()
        self.end_headers()

    def do_POST(self):
        """Handles diagnostic telemetry and error reports from web players."""
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path
        client_ip = self.client_address[0]
        client_port = self.client_address[1]
        user_agent = self.headers.get("User-Agent", "")

        self.device_logger.on_request(client_ip, client_port, user_agent, "POST", path)

        if path == "/api/log":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length) if content_length > 0 else b"{}"
            try:
                payload = json.loads(body.decode("utf-8"))
                self.device_logger.on_client_telemetry(client_ip, payload)
            except Exception as e:
                self.device_logger.on_error(client_ip, path, "TelemetryParseError", str(e))

            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
            self.device_logger.on_response(client_ip, path, 200, 15)
        else:
            self.send_error(404, "Not Found")
            self.device_logger.on_error(client_ip, path, "NotFound", "Route non trouvee")

    def do_GET(self):
        """Routes GET requests to Web Player, Playlist, Segment Proxy, or Direct MP4 Stream."""
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path
        query = urllib.parse.parse_qs(parsed_path.query)

        client_ip = self.client_address[0]
        client_port = self.client_address[1]
        user_agent = self.headers.get("User-Agent", "")

        # Record incoming request in device tracker
        self.device_logger.on_request(client_ip, client_port, user_agent, "GET", path)

        if path in ["/", "/index.html"]:
            self._serve_web_player(client_ip)
        elif path in ["/playlist.m3u8", "/master.m3u8"]:
            if not self.video or not self.video.stream_url:
                self.send_error(404, "No stream URL configured.")
                self.device_logger.on_error(client_ip, path, "NoStream", "URL de flux non configurée")
                return
            self._serve_rewritten_playlist(self.video.stream_url, client_ip)
        elif path in ["/stream.mp4", "/video.mp4"]:
            if not self.video or not self.video.stream_url:
                self.send_error(404, "No stream URL configured.")
                self.device_logger.on_error(client_ip, path, "NoStream", "URL de flux non configurée")
                return
            self._serve_direct_stream(format="mp4", client_ip=client_ip)
        elif path in ["/stream.ts", "/live.ts"]:
            if not self.video or not self.video.stream_url:
                self.send_error(404, "No stream URL configured.")
                self.device_logger.on_error(client_ip, path, "NoStream", "URL de flux non configurée")
                return
            self._serve_direct_stream(format="mpegts", client_ip=client_ip)
        elif path == "/proxy":
            upstream_url = query.get("url", [None])[0]
            if not upstream_url:
                self.send_error(400, "Missing 'url' parameter")
                self.device_logger.on_error(client_ip, path, "BadRequest", "Parametre 'url' manquant")
                return
            self._proxy_upstream(upstream_url, client_ip)
        else:
            self.send_error(404, "Not Found")
            self.device_logger.on_error(client_ip, path, "NotFound", "Route non trouvee")

    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS, HEAD")
        self.send_header("Access-Control-Allow-Headers", "*")

    def _serve_web_player(self, client_ip: str = "127.0.0.1"):
        """Serves a sleek, dark-themed responsive HTML5 video player compatible with both
        modern devices (Hls.js) and older Smart TVs (Samsung Serie 3 / Orsay / WebKit 534) via Direct MP4.
        """
        title = self.video.title if self.video else "EGY-Stream Video"
        html = f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - EGY-Stream</title>
    <script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            background-color: #09090b;
            color: #f4f4f5;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            display: flex;
            flex-direction: column;
            align-items: center;
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{
            width: 100%;
            max-width: 1000px;
            display: flex;
            flex-direction: column;
            gap: 16px;
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid #27272a;
            padding-bottom: 12px;
        }}
        .title {{
            font-size: 1.4rem;
            font-weight: 700;
            color: #38bdf8;
        }}
        .badge {{
            background: #27272a;
            color: #a1a1aa;
            font-size: 0.8rem;
            padding: 4px 10px;
            border-radius: 9999px;
            font-family: monospace;
        }}
        .player-wrapper {{
            position: relative;
            width: 100%;
            background: #000;
            border-radius: 16px;
            overflow: hidden;
            box-shadow: 0 20px 50px rgba(0,0,0,0.8);
            aspect-ratio: 16/9;
        }}
        video {{
            width: 100%;
            height: 100%;
            object-fit: contain;
        }}
        .mode-selector {{
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }}
        .mode-btn {{
            flex: 1;
            min-width: 220px;
            background: #18181b;
            color: #f4f4f5;
            border: 2px solid #27272a;
            padding: 12px 16px;
            border-radius: 10px;
            font-size: 0.95rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
            text-align: center;
        }}
        .mode-btn:hover {{
            background: #27272a;
            border-color: #38bdf8;
        }}
        .mode-btn.active {{
            background: #0284c7;
            border-color: #38bdf8;
            color: #fff;
            box-shadow: 0 0 15px rgba(56, 189, 248, 0.4);
        }}
        .status-bar {{
            background: #18181b;
            border-left: 4px solid #38bdf8;
            border-radius: 8px;
            padding: 10px 14px;
            font-size: 0.88rem;
            color: #d4d4d8;
        }}
        .info-card {{
            background: #18181b;
            border: 1px solid #27272a;
            border-radius: 12px;
            padding: 16px;
            font-size: 0.9rem;
            color: #a1a1aa;
            display: flex;
            flex-direction: column;
            gap: 8px;
        }}
        .code {{
            background: #09090b;
            padding: 8px 12px;
            border-radius: 8px;
            color: #22c55e;
            font-family: monospace;
            word-break: break-all;
            direction: ltr;
            text-align: left;
        }}
        .code.mp4 {{
            color: #fbbf24;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1 class="title">📺 {title}</h1>
            <span class="badge">EGY-STREAM MULTI-DEVICE RELAY</span>
        </div>

        <div class="player-wrapper">
            <video id="video" controls autoplay playsinline preload="auto">
                <source id="source-hls" src="/playlist.m3u8" type="application/vnd.apple.mpegurl">
                <source id="source-ts" src="/stream.ts" type="video/mp2t">
                Votre appareil ne supporte pas la lecture HTML5.
            </video>
        </div>

        <div class="mode-selector">
            <button type="button" id="btn-native-hls" class="mode-btn active" onclick="switchMode('native_hls')">
                📺 Mode HLS Natif (TV Samsung Tizen / iOS)
            </button>
            <button type="button" id="btn-hls-js" class="mode-btn" onclick="switchMode('hls_js')">
                📡 Mode Hls.js (Chrome / PC / Android)
            </button>
            <button type="button" id="btn-ts" class="mode-btn" onclick="switchMode('ts')">
                🎞️ Mode Direct MPEG-TS (Alternative TV)
            </button>
            <button type="button" id="btn-mp4" class="mode-btn" onclick="switchMode('mp4')">
                ⚡ Mode Direct MP4
            </button>
        </div>

        <div id="status-bar" class="status-bar">
            Initialisation du lecteur vidéo...
        </div>

        <div class="info-card">
            <span>📺 <strong>Flux HLS M3U8 (Recommandé Samsung Tizen & VLC) :</strong></span>
            <div class="code" id="m3u8-link">Chargement...</div>
        </div>

        <div class="info-card">
            <span>🎞️ <strong>Flux Direct MPEG-TS (Idéal anciennes Smart TV) :</strong></span>
            <div class="code mp4" id="ts-link">Chargement...</div>
        </div>

        <div class="info-card">
            <span>⚡ <strong>Flux Direct MP4 :</strong></span>
            <div class="code mp4" id="mp4-link">Chargement...</div>
        </div>
    </div>

    <script>
        var video = document.getElementById('video');
        var origin = window.location.origin || (window.location.protocol + '//' + window.location.host);
        var streamUrl = origin + '/playlist.m3u8';
        var tsUrl = origin + '/stream.ts';
        var mp4Url = origin + '/stream.mp4';

        document.getElementById('m3u8-link').innerText = streamUrl;
        document.getElementById('ts-link').innerText = tsUrl;
        document.getElementById('mp4-link').innerText = mp4Url;

        var currentHls = null;

        function reportTelemetry(event, message, details) {{
            try {{
                var xhr = new XMLHttpRequest();
                xhr.open("POST", origin + "/api/log", true);
                xhr.setRequestHeader("Content-Type", "application/json");
                xhr.send(JSON.stringify({{
                    event: event,
                    message: message,
                    details: details || {{}},
                    currentTime: video ? video.currentTime : 0
                }}));
            }} catch(e) {{}}
        }}

        function updateStatus(text, isAlert) {{
            var bar = document.getElementById('status-bar');
            if (bar) {{
                bar.innerHTML = text;
                bar.style.borderLeftColor = isAlert ? '#ef4444' : '#38bdf8';
            }}
        }}

        // Gestion de la persistance de position (résilience aux coupures)
        var lastValidTime = 0;
        var storageKey = 'lanstream_resume_' + encodeURIComponent('{title}');
        try {{
            var savedPos = localStorage.getItem(storageKey);
            if (savedPos) lastValidTime = parseFloat(savedPos) || 0;
        }} catch(e) {{}}

        video.addEventListener('timeupdate', function() {{
            if (video.currentTime > 2) {{
                lastValidTime = video.currentTime;
                try {{ localStorage.setItem(storageKey, lastValidTime); }} catch(e) {{}}
            }}
        }});

        // Moteur de reconnexion automatique en cas d'interruption Internet
        var isReconnecting = false;
        var reconnectTimer = null;

        function startAutoReconnect() {{
            if (isReconnecting) return;
            isReconnecting = true;
            reportTelemetry("network_disconnect", "Perte de connexion detectee, maintien du flux a " + Math.floor(lastValidTime) + "s", {{ time: lastValidTime }});
            updateStatus("⚠️ Connexion Internet interrompue. LanStream préserve votre position (" + Math.floor(lastValidTime) + "s) et se reconnecte...", true);

            var attempts = 0;
            if (reconnectTimer) clearInterval(reconnectTimer);
            reconnectTimer = setInterval(function() {{
                attempts++;
                var probe = new XMLHttpRequest();
                probe.open('GET', streamUrl + '?probe=' + Date.now(), true);
                probe.timeout = 3500;
                probe.onload = function() {{
                    if (probe.status >= 200 && probe.status < 400) {{
                        clearInterval(reconnectTimer);
                        reconnectTimer = null;
                        isReconnecting = false;
                        updateStatus("✅ Connexion Internet rétablie ! Reprise automatique du flux...", false);
                        reportTelemetry("network_reconnected", "Connexion retablie avec succes apres " + attempts + " tentatives", {{ attempts: attempts }});
                        resumeStreamAt(lastValidTime);
                    }}
                }};
                probe.onerror = probe.ontimeout = function() {{
                    updateStatus("⚠️ Connexion en attente (tentative " + attempts + ")... LanStream maintient votre position (" + Math.floor(lastValidTime) + "s)", true);
                }};
                probe.send();
            }}, 2500);
        }}

        function resumeStreamAt(targetTime) {{
            if (currentHls) {{
                currentHls.startLoad(targetTime);
                if (targetTime > 0) video.currentTime = targetTime;
                var p = video.play();
                if (p && p.catch) p.catch(function() {{}});
            }} else {{
                video.src = streamUrl + '?t=' + Date.now();
                video.load();
                var onMeta = function() {{
                    video.removeEventListener('loadedmetadata', onMeta);
                    if (targetTime > 0) video.currentTime = targetTime;
                    var p = video.play();
                    if (p && p.catch) p.catch(function() {{}});
                }};
                video.addEventListener('loadedmetadata', onMeta);
            }}
        }}

        window.addEventListener('offline', function() {{
            startAutoReconnect();
        }});

        window.addEventListener('online', function() {{
            startAutoReconnect();
        }});

        var stallTimeout = null;
        video.addEventListener('waiting', function() {{
            clearTimeout(stallTimeout);
            stallTimeout = setTimeout(function() {{
                if (video.paused === false && video.readyState < 3) {{
                    startAutoReconnect();
                }}
            }}, 6000);
        }});
        video.addEventListener('playing', function() {{
            clearTimeout(stallTimeout);
            if (isReconnecting) {{
                isReconnecting = false;
                if (reconnectTimer) {{ clearInterval(reconnectTimer); reconnectTimer = null; }}
            }}
        }});

        video.addEventListener('error', function() {{
            var err = video.error;
            var code = err ? err.code : 0;
            var msg = "Erreur balise video (code " + code + ")";
            if (code === 1) msg = "MEDIA_ERR_ABORTED: Lecture interrompue";
            else if (code === 2) {{
                msg = "MEDIA_ERR_NETWORK: Erreur de telechargement reseau";
                startAutoReconnect();
            }}
            else if (code === 3) msg = "MEDIA_ERR_DECODE: Erreur de decodage materiel TV";
            else if (code === 4) msg = "MEDIA_ERR_SRC_NOT_SUPPORTED: Format non supporte par ce televiseur";
            updateStatus("⚠️ " + msg, true);
            reportTelemetry("video_tag_error", msg, {{ code: code }});
        }});

        function setActiveButton(btnId) {{
            var btns = ['btn-native-hls', 'btn-hls-js', 'btn-ts', 'btn-mp4'];
            for (var i = 0; i < btns.length; i++) {{
                var b = document.getElementById(btns[i]);
                if (b) {{
                    b.className = (btns[i] === btnId) ? 'mode-btn active' : 'mode-btn';
                }}
            }}
        }}

        function switchMode(mode) {{
            if (currentHls) {{
                try {{ currentHls.destroy(); }} catch(e) {{}}
                currentHls = null;
            }}

            reportTelemetry("switch_mode", "Bascule vers mode " + mode, {{ mode: mode }});

            if (mode === 'native_hls') {{
                setActiveButton('btn-native-hls');
                updateStatus("Mode actif : <strong>HLS Natif Samsung TV / iOS (Recommandé)</strong>", false);
                video.src = streamUrl;
                video.load();
                if (lastValidTime > 5) {{
                    var onMeta = function() {{
                        video.removeEventListener('loadedmetadata', onMeta);
                        video.currentTime = lastValidTime;
                    }};
                    video.addEventListener('loadedmetadata', onMeta);
                }}
                var p = video.play();
                if (p && p.catch) p.catch(function(e) {{ reportTelemetry("play_catch", e.message, {{}}); }});
            }} else if (mode === 'hls_js') {{
                setActiveButton('btn-hls-js');
                updateStatus("Mode actif : <strong>Hls.js Adaptatif (Chrome / Android / PC)</strong>", false);
                if (typeof Hls !== 'undefined' && Hls.isSupported()) {{
                    currentHls = new Hls({{
                        maxBufferLength: 60,
                        maxMaxBufferLength: 120,
                        enableWorker: true,
                        manifestLoadingMaxRetry: 20,
                        manifestLoadingRetryDelay: 1500,
                        manifestLoadingMaxRetryTimeout: 90000,
                        fragLoadingMaxRetry: 20,
                        fragLoadingRetryDelay: 1500,
                        fragLoadingMaxRetryTimeout: 90000,
                        levelLoadingMaxRetry: 20,
                        levelLoadingRetryDelay: 1500,
                        levelLoadingMaxRetryTimeout: 90000
                    }});
                    currentHls.loadSource(streamUrl);
                    currentHls.attachMedia(video);
                    currentHls.on(Hls.Events.MANIFEST_PARSED, function() {{
                        if (lastValidTime > 5) {{
                            video.currentTime = lastValidTime;
                        }}
                        video.play();
                    }});
                    currentHls.on(Hls.Events.ERROR, function(event, data) {{
                        reportTelemetry("hls_error", data.type + " : " + (data.details || ""), data);
                        if (data && data.fatal) {{
                            if (data.type === Hls.ErrorTypes.NETWORK_ERROR) {{
                                startAutoReconnect();
                            }} else if (data.type === Hls.ErrorTypes.MEDIA_ERROR) {{
                                currentHls.recoverMediaError();
                            }} else {{
                                updateStatus("⚠️ Erreur Hls.js non récupérable. Bascule sur HLS Natif...", true);
                                switchMode('native_hls');
                            }}
                        }}
                    }});
                }} else {{
                    updateStatus("Hls.js non supporté par ce navigateur TV. Utilisation du mode Natif.", true);
                    switchMode('native_hls');
                }}
            }} else if (mode === 'ts') {{
                setActiveButton('btn-ts');
                updateStatus("Mode actif : <strong>MPEG-TS Direct (Flux broadcast universel)</strong>", false);
                video.src = tsUrl;
                video.load();
                if (lastValidTime > 5) {{
                    var onMeta = function() {{
                        video.removeEventListener('loadedmetadata', onMeta);
                        video.currentTime = lastValidTime;
                    }};
                    video.addEventListener('loadedmetadata', onMeta);
                }}
                video.play();
            }} else if (mode === 'mp4') {{
                setActiveButton('btn-mp4');
                updateStatus("Mode actif : <strong>Direct MP4</strong>", false);
                video.src = mp4Url;
                video.load();
                if (lastValidTime > 5) {{
                    var onMeta = function() {{
                        video.removeEventListener('loadedmetadata', onMeta);
                        video.currentTime = lastValidTime;
                    }};
                    video.addEventListener('loadedmetadata', onMeta);
                }}
                video.play();
            }}
        }}

        // Détection initiale ultra-intelligente
        try {{
            var canHls = false;
            if (video.canPlayType) {{
                var canApple = video.canPlayType('application/vnd.apple.mpegurl');
                var canX = video.canPlayType('application/x-mpegURL');
                if (canApple === 'probably' || canApple === 'maybe' || canX === 'probably' || canX === 'maybe') {{
                    canHls = true;
                }}
            }}

            var isTv = /smart-tv|tizen|maple|webos|netcast/i.test(navigator.userAgent);

            // Sur une Smart TV (Tizen / WebKit TV), toujours préférer le HLS Natif matériel !
            if (isTv && canHls) {{
                switchMode('native_hls');
            }} else if (typeof Hls !== 'undefined' && Hls.isSupported()) {{
                switchMode('hls_js');
            }} else if (canHls) {{
                switchMode('native_hls');
            }} else {{
                switchMode('ts');
            }}
        }} catch(e) {{
            switchMode('native_hls');
        }}
    </script>
</body>
</html>"""
        encoded = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(encoded)
        self.device_logger.on_response(client_ip, self.path, 200, len(encoded))

    def _serve_direct_stream(self, format: str = "mp4", client_ip: str = "127.0.0.1"):
        """Streams a live remuxed progressive MP4 or MPEG-TS feed using ffmpeg with -c copy.
        Decrypts AES-128 chunks on the fly on the host, producing a clean unencrypted
        stream directly playable by older Smart TVs (Samsung Serie 3, etc.) and legacy browsers.
        """
        if not shutil.which("ffmpeg"):
            self.send_error(501, "FFmpeg is required for direct MP4/TS remuxing but is not installed.")
            self.device_logger.on_error(client_ip, self.path, "DependencyError", "FFmpeg non installe sur l'hote")
            return

        is_mp4 = format == "mp4"
        content_type = "video/mp4" if is_mp4 else "video/mp2t"

        headers_str = f"Referer: {self.upstream_referer}\r\nUser-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36\r\n"
        if "cinejoy" in self.upstream_referer or "cineby" in self.upstream_referer or "moviebox" in (self.video.stream_url or ""):
            origin = self.upstream_referer.rstrip("/")
            headers_str = f"Referer: {self.upstream_referer}\r\nOrigin: {origin}\r\nUser-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36\r\n"

        cmd = [
            "ffmpeg",
            "-loglevel", "error",
            "-reconnect", "1",
            "-reconnect_on_network_error", "1",
            "-reconnect_delay_max", "5",
            "-extension_picky", "0",
            "-headers", headers_str,
            "-i", self.video.stream_url,
        ]

        # Select strictly 1 video stream and 1 audio stream to ensure Samsung TV / browser compatibility
        if getattr(self.video, "selected_vid", None):
            prog_idx = self.video.selected_vid - 1
            cmd.extend([
                "-map", f"0:p:{prog_idx}:v:0",
                "-map", "0:a:0?",
            ])
        elif getattr(self.video, "available_resolutions", None) and len(self.video.available_resolutions) > 0:
            # Auto: prefer 1080p if available, else first resolution program
            res_list = self.video.available_resolutions
            best_idx = 1
            for r in res_list:
                if r.get("height") == 1080:
                    best_idx = r["index"]
                    break
            prog_idx = best_idx - 1
            cmd.extend([
                "-map", f"0:p:{prog_idx}:v:0",
                "-map", "0:a:0?",
            ])
        elif "moviebox" in (self.video.stream_url or "") or "cinejoy" in self.upstream_referer or "cineby" in self.upstream_referer:
            cmd.extend([
                "-map", "0:p:1:v:0",
                "-map", "0:a:0?",
            ])
        else:
            cmd.extend([
                "-map", "0:v:0",
                "-map", "0:a:0?",
            ])

        cmd.extend([
            "-c:v", "copy",
            "-c:a", "copy",
        ])

        if is_mp4:
            cmd.extend([
                "-bsf:a", "aac_adtstoasc",
                "-movflags", "frag_keyframe+empty_moov+default_base_moof",
                "-f", "mp4",
            ])
        else:
            cmd.extend([
                "-f", "mpegts",
            ])

        cmd.append("pipe:1")

        if "Range" in self.headers:
            self.send_response(206)
            self.send_header("Content-Range", "bytes 0-1000000000/1000000001")
        else:
            self.send_response(200)

        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Accept-Ranges", "bytes")
        self._send_cors_headers()
        self.end_headers()

        proc = None
        total_bytes = 0
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            StreamProxyHandler.active_processes.append(proc)

            while True:
                chunk = proc.stdout.read(65536)
                if not chunk:
                    break
                self.wfile.write(chunk)
                total_bytes += len(chunk)
            self.device_logger.on_response(client_ip, self.path, 200, total_bytes)
        except (requests.exceptions.RequestException,
                urllib3.exceptions.HTTPError,
                BrokenPipeError,
                ConnectionResetError,
                socket.error,
                Exception) as e:
            self.device_logger.on_error(
                client_ip,
                self.path,
                type(e).__name__,
                str(e) or "Flux coupe par client ou upstream",
                {"bytes_streamed": total_bytes, "format": format}
            )
        finally:
            if proc:
                try:
                    proc.stdout.close()
                except Exception:
                    pass
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                if proc in StreamProxyHandler.active_processes:
                    StreamProxyHandler.active_processes.remove(proc)

    def _serve_rewritten_playlist(self, m3u8_url: str, client_ip: str = "127.0.0.1"):
        """Fetches upstream m3u8 and rewrites internal URLs through this proxy using absolute URLs."""
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
            "Referer": self.upstream_referer,
        }
        try:
            resp = self.session.get(m3u8_url, headers=headers, timeout=15)
            resp.raise_for_status()
            content = resp.text
        except Exception as e:
            self.send_error(502, f"Failed to fetch upstream playlist: {e}")
            self.device_logger.on_error(client_ip, self.path, type(e).__name__, str(e))
            return

        host = self.headers.get("Host", f"127.0.0.1:{self.server.server_port}")
        proxy_base = f"http://{host}"
        selected_vid = getattr(self.video, "selected_vid", None)
        rewritten = self._rewrite_m3u8_content(content, m3u8_url, proxy_base=proxy_base, selected_vid=selected_vid)
        encoded = rewritten.encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "application/vnd.apple.mpegurl")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(encoded)
        self.device_logger.on_response(client_ip, self.path, 200, len(encoded))

    def _proxy_upstream(self, upstream_url: str, client_ip: str = "127.0.0.1"):
        """Streams upstream segments, encryption keys, or sub-manifests to the client.
        Includes in-memory LRU caching and resilient exponential backoff retry to survive network drops.
        """
        # Fast path 1: in-memory cache for AES-128 encryption keys
        is_key = "encryption.key" in upstream_url or ".key" in upstream_url
        if is_key and upstream_url in self.key_cache:
            cached_key = self.key_cache[upstream_url]
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(cached_key)))
            self.send_header("Cache-Control", "public, max-age=86400")
            self._send_cors_headers()
            self.end_headers()
            try:
                self.wfile.write(cached_key)
                self.device_logger.on_response(client_ip, self.path, 200, len(cached_key))
            except (BrokenPipeError, ConnectionResetError, socket.error):
                pass
            return

        # Fast path 2: in-memory LRU cache for recent video/audio segments (instant fallback during network drops)
        if not is_key and upstream_url in self.segment_cache:
            cached_data, cached_ct = self.segment_cache[upstream_url]
            self.send_response(200)
            self.send_header("Content-Type", cached_ct)
            self.send_header("Content-Length", str(len(cached_data)))
            self.send_header("Cache-Control", "public, max-age=3600")
            self._send_cors_headers()
            self.end_headers()
            try:
                self.wfile.write(cached_data)
                self.device_logger.on_response(client_ip, self.path, 200, len(cached_data))
            except (BrokenPipeError, ConnectionResetError, socket.error):
                pass
            return

        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
            "Referer": self.upstream_referer,
        }
        # Forward Range header if requested by player
        if "Range" in self.headers:
            headers["Range"] = self.headers["Range"]

        # Fetch from upstream with automatic retry & exponential backoff (~15-20s resilience window)
        upstream_resp = None
        last_exc = None
        import time
        for attempt in range(6):
            try:
                upstream_resp = self.session.get(upstream_url, headers=headers, timeout=(4, 20))
                if upstream_resp.status_code == 200 or (upstream_resp.status_code < 500 and upstream_resp.status_code != 404):
                    break
            except Exception as e:
                last_exc = e
                backoff = min(0.3 * (1.8 ** attempt), 3.5)
                time.sleep(backoff)

        if upstream_resp is None:
            self.send_error(502, f"Upstream proxy request error: {last_exc}")
            self.device_logger.on_error(client_ip, self.path, type(last_exc).__name__, str(last_exc), {"upstream_url": upstream_url})
            return

        # If upstream is an m3u8 playlist, rewrite it on the fly with absolute URLs
        content_type = upstream_resp.headers.get("Content-Type", "").lower()
        if "mpegurl" in content_type or ".m3u8" in upstream_url.lower() or upstream_resp.text.strip().startswith("#EXTM3U"):
            text = upstream_resp.text
            host = self.headers.get("Host", f"127.0.0.1:{self.server.server_port}")
            proxy_base = f"http://{host}"
            rewritten = self._rewrite_m3u8_content(text, upstream_url, proxy_base=proxy_base, selected_vid=None)
            encoded = rewritten.encode("utf-8")

            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.apple.mpegurl")
            self.send_header("Content-Length", str(len(encoded)))
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(encoded)
            self.device_logger.on_response(client_ip, self.path, 200, len(encoded))
            return

        # Cache AES-128 key in RAM
        if is_key and upstream_resp.status_code == 200:
            self.key_cache[upstream_url] = upstream_resp.content

        # Deliver clean complete segment / key to client
        content = upstream_resp.content
        url_lower = upstream_url.lower()

        # Determine proper MIME type, overriding upstream text/html disguise (MovieBox CDN)
        if is_key:
            mime_type = "application/octet-stream"
        elif "audio" in url_lower:
            mime_type = "audio/mp4"
        elif ".ts" in url_lower:
            mime_type = "video/mp2t"
        elif ".vtt" in url_lower:
            mime_type = "text/vtt"
        elif any(ext in url_lower for ext in [".m4s", ".mp4", "video", "init"]) or ".html" in url_lower:
            mime_type = "video/mp4"
        else:
            upstream_ct = upstream_resp.headers.get("Content-Type", "")
            if not upstream_ct or "text/html" in upstream_ct.lower() or "text/plain" in upstream_ct.lower():
                mime_type = "video/mp4"
            else:
                mime_type = upstream_ct

        # Populate LRU segment cache
        if not is_key and upstream_resp.status_code == 200 and len(content) > 0:
            if len(self.segment_cache_keys) >= self.MAX_SEGMENT_CACHE:
                oldest_key = self.segment_cache_keys.pop(0)
                self.segment_cache.pop(oldest_key, None)
            self.segment_cache[upstream_url] = (content, mime_type)
            self.segment_cache_keys.append(upstream_url)

        self.send_response(upstream_resp.status_code)
        self.send_header("Content-Type", mime_type)
        self.send_header("Content-Length", str(len(content)))

        if "Content-Range" in upstream_resp.headers:
            self.send_header("Content-Range", upstream_resp.headers["Content-Range"])
        if "Accept-Ranges" in upstream_resp.headers:
            self.send_header("Accept-Ranges", upstream_resp.headers["Accept-Ranges"])

        if is_key:
            self.send_header("Cache-Control", "public, max-age=86400")
        else:
            self.send_header("Cache-Control", "public, max-age=3600")

        self._send_cors_headers()
        self.end_headers()

        try:
            self.wfile.write(content)
            self.device_logger.on_response(client_ip, self.path, upstream_resp.status_code, len(content))
        except (BrokenPipeError, ConnectionResetError, socket.error) as e:
            self.device_logger.on_error(
                client_ip,
                self.path,
                type(e).__name__,
                str(e) or "Flux coupe par client",
                {"upstream_url": upstream_url, "bytes_sent": 0}
            )

    @classmethod
    def _rewrite_m3u8_content(cls, content: str, base_url: str, proxy_base: str = "", selected_vid: Optional[int] = None) -> str:
        """Rewrites m3u8 URI lines to route through the local proxy using full absolute URLs.

        Handles:
        - Tag URIs: #EXT-X-KEY, #EXT-X-MAP, #EXT-X-MEDIA, etc.
        - Segment and playlist URLs
        - Variant stream filtering when selected_vid is specified
        """
        # Validate selected_vid against available variants
        if selected_vid is not None:
            total_variants = sum(1 for l in content.splitlines() if l.strip().startswith("#EXT-X-STREAM-INF:"))
            if selected_vid < 1 or selected_vid > total_variants:
                selected_vid = None

        lines = []
        stream_inf_idx = 0
        skip_next_uri = False

        def _replace_uri(m):
            orig_uri = m.group(1) or m.group(2) or m.group(3)
            full_uri = urllib.parse.urljoin(base_url, orig_uri)
            encoded = urllib.parse.quote(full_uri, safe="")
            return f'URI="{proxy_base}/proxy?url={encoded}"'

        for line in content.splitlines():
            s = line.strip()
            if not s:
                continue

            # Variant streams in master playlist
            if s.startswith("#EXT-X-STREAM-INF:"):
                stream_inf_idx += 1
                if selected_vid is not None and stream_inf_idx != selected_vid:
                    skip_next_uri = True
                    continue
                skip_next_uri = False
                if "URI=" in s:
                    s = re.sub(r'URI=(?:"([^"]+)"|\'([^\']+)\'|([^\s,]+))', _replace_uri, s)
                lines.append(s)
                continue

            # If previous variant stream was skipped, skip its target URL line
            if skip_next_uri:
                skip_next_uri = False
                continue

            # Tag line: rewrite any URI attributes (e.g. #EXT-X-KEY, #EXT-X-MAP, #EXT-X-MEDIA)
            if s.startswith("#"):
                if "URI=" in s:
                    s = re.sub(r'URI=(?:"([^"]+)"|\'([^\']+)\'|([^\s,]+))', _replace_uri, s)
                lines.append(s)
            # Media segment or sub-playlist URL
            else:
                full_uri = urllib.parse.urljoin(base_url, s)
                encoded = urllib.parse.quote(full_uri, safe="")
                lines.append(f"{proxy_base}/proxy?url={encoded}")

        return "\n".join(lines)



class StreamProxyService:
    """Manages the local HLS stream micro-proxy server on the LAN."""

    def __init__(self, video: Video, port: int = 8080, logger=None):
        self.video = video
        self.port = port
        self.logger = logger or setup_logger("StreamProxy")
        self.server: Optional[http.server.ThreadingHTTPServer] = None
        self.thread: Optional[threading.Thread] = None
        self.is_running = False
        self.local_ip = self.get_local_ip()

    @staticmethod
    def get_local_ip() -> str:
        """Determines the active LAN IPv4 address (e.g. 192.168.1.X)."""
        # Method 1: Outbound socket check
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                ip = s.getsockname()[0]
                if not ip.startswith("127."):
                    return ip
        except Exception:
            pass

        # Method 2: hostname -I command fallback
        try:
            out = subprocess.check_output(["hostname", "-I"], text=True, stderr=subprocess.DEVNULL).strip()
            for candidate in out.split():
                if candidate.startswith("192.168.") or candidate.startswith("10.") or candidate.startswith("172."):
                    return candidate
        except Exception:
            pass

        return "127.0.0.1"

    def get_web_url(self) -> str:
        """Returns the shareable HTML5 web player URL."""
        return f"http://{self.local_ip}:{self.port}/"

    def get_stream_url(self) -> str:
        """Returns the direct rewritten m3u8 stream URL."""
        return f"http://{self.local_ip}:{self.port}/playlist.m3u8"

    def get_mp4_url(self) -> str:
        """Returns the direct unencrypted progressive MP4 stream URL (ideal for old Smart TVs)."""
        return f"http://{self.local_ip}:{self.port}/stream.mp4"

    def get_ts_url(self) -> str:
        """Returns the direct MPEG-TS stream URL."""
        return f"http://{self.local_ip}:{self.port}/stream.ts"

    def start(self, background: bool = True):
        """Binds and starts the HTTP proxy server."""
        # Configure handler class state
        handler_class = StreamProxyHandler
        handler_class.video = self.video
        handler_class.key_cache = {}
        if self.video and (self.video.embed_url or self.video.page_url):
            ref_url = self.video.embed_url or self.video.page_url
            parsed = urllib.parse.urlparse(ref_url)
            handler_class.upstream_referer = f"{parsed.scheme}://{parsed.netloc}/"

        # Configure resilient session with HTTPAdapter and connection pooling
        session = requests.Session()
        from urllib3.util import Retry
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=25,
            pool_maxsize=25,
            max_retries=Retry(
                total=3,
                backoff_factor=0.3,
                status_forcelist=[500, 502, 503, 504],
                raise_on_status=False
            )
        )
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        handler_class.session = session

        # Find available port starting from self.port
        for p in range(self.port, self.port + 10):
            try:
                self.server = http.server.ThreadingHTTPServer(("0.0.0.0", p), handler_class)
                self.port = p
                break
            except OSError:
                continue

        if not self.server:
            raise RuntimeError(f"Could not bind to any port in range {self.port}-{self.port+10}")

        self.is_running = True
        self.logger.info(f"Stream proxy listening on 0.0.0.0:{self.port}")

        if background:
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
        else:
            self.server.serve_forever()

    def stop(self):
        """Stops the proxy server and frees network resources."""
        if self.server:
            self.logger.info("Stopping stream proxy...")
            for proc in list(StreamProxyHandler.active_processes):
                try:
                    if proc.poll() is None:
                        proc.terminate()
                except Exception:
                    pass
            StreamProxyHandler.active_processes.clear()
            self.server.shutdown()
            self.server.server_close()
            self.is_running = False

    def print_sharing_banner(self):
        """Displays formatted terminal instructions for connected LAN devices."""
        web_url = self.get_web_url()
        mp4_url = self.get_mp4_url()
        m3u8_url = self.get_stream_url()

        print("\n" + "═" * 72)
        print("  📡  LOCAL WI-FI STREAM PROXY ACTIVE (SMART TV & MULTI-DEVICE)")
        print("═" * 72)
        print(f"  🎬 Film         : {self.video.title}")
        print(f"  📱 Lecteur Web  : \033[96m\033[1m{web_url}\033[0m")
        print(f"  📺 Direct MP4   : \033[93m\033[1m{mp4_url}\033[0m  (\033[33m⚡ Recommandé TV Samsung\033[0m)")
        print(f"  🔗 Direct M3U8  : \033[92m{m3u8_url}\033[0m  (VLC / IPTV / Mobiles récents)")
        print("─" * 72)
        print("  💡 Astuce pour Samsung Smart TV (Série 3 / Anciennes TV) :")
        print("     1. Dans le navigateur de la TV, ouvrez le Lecteur Web ci-dessus.")
        print("     2. Cliquez sur 'Mode TV Samsung (Direct MP4)' si le lecteur reste noir.")
        print("     3. Ou entrez directement l'URL Direct MP4 dans le navigateur TV.")
        print("─" * 72)
        print("  📝 Diagnostic & Audit des appareils :")
        print("     • Historique live : output/devices_activity.log")
        print("     • État JSON       : output/connected_devices.json")
        print("═" * 72 + "\n")
