"""
Device Logger & Tracker Service
=================================
Tracks and audits all devices connected to the local proxy (IP, port, User-Agent,
device type, requests, streamed volume, and error diagnostics).
"""
import datetime
import json
import os
import re
import threading
from typing import Dict, List, Optional

from config import DEVICES_LOG_FILE, DEVICES_JSON_FILE


class DeviceLoggerService:
    """Thread-safe service to record connected client devices and their activity/error logs."""

    _instance = None
    _lock = threading.Lock()

    def __init__(self, log_file: str = DEVICES_LOG_FILE, json_file: str = DEVICES_JSON_FILE):
        self.log_file = log_file
        self.json_file = json_file
        self.devices: Dict[str, dict] = {}
        self.lock = threading.Lock()

        # Ensure output directory exists
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)

    @classmethod
    def get_instance(cls) -> "DeviceLoggerService":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    @staticmethod
    def parse_device_type(user_agent: str) -> str:
        """Heuristically determines device brand and platform from the User-Agent header."""
        if not user_agent:
            return "Appareil Inconnu (User-Agent manquant)"

        ua = user_agent.lower()

        # Samsung Smart TVs (Orsay, Tizen, Maple, SmartTV)
        if "samsung" in ua or "smart-tv" in ua or "smarttv" in ua:
            if "tizen" in ua:
                match = re.search(r'tizen\s*([0-9.]+)', ua)
                ver = match.group(1) if match else ""
                return f"Samsung Smart TV (Tizen {ver})".strip()
            elif "maple" in ua:
                return "Samsung Smart TV (Orsay / Série 3-5 ancienne)"
            elif "otv" in ua:
                return "Samsung Smart TV (Orsay TV)"
            return "Samsung Smart TV"

        # LG Smart TVs
        if "web0s" in ua or "webos" in ua:
            return "LG Smart TV (webOS)"
        if "netcast" in ua:
            return "LG Smart TV (NetCast ancienne)"

        # Media Players
        if "vlc" in ua:
            return "VLC Media Player"
        if "kodi" in ua:
            return "Kodi Media Center"
        if "mpv" in ua:
            return "MPV Player"
        if "ffmpeg" in ua:
            return "FFmpeg client"

        # Apple Ecosystem
        if "iphone" in ua:
            return "Apple iPhone (Safari / iOS)"
        if "ipad" in ua:
            return "Apple iPad (iPadOS)"
        if "macintosh" in ua or "mac os" in ua:
            return "Apple Mac (macOS)"

        # Android
        if "android" in ua:
            if "tv" in ua or "aft" in ua or "bravia" in ua:
                return "Android TV / Fire TV"
            return "Smartphone / Tablette Android"

        # Desktop
        if "windows" in ua:
            return "PC Windows"
        if "linux" in ua:
            return "PC Linux"

        return "Appareil Universel / Navigateur Web"

    def on_request(self, ip: str, port: int, user_agent: str, method: str, path: str):
        """Records an incoming request from a device."""
        now = datetime.datetime.now()
        timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
        device_type = self.parse_device_type(user_agent)

        with self.lock:
            is_new = ip not in self.devices

            if is_new:
                self.devices[ip] = {
                    "ip": ip,
                    "device_type": device_type,
                    "user_agent": user_agent,
                    "first_seen": timestamp,
                    "last_seen": timestamp,
                    "last_port": port,
                    "total_requests": 1,
                    "bytes_sent": 0,
                    "last_path": path,
                    "errors_count": 0,
                    "errors": []
                }
                # Console alert for new device
                print(f"\n\033[92m✨ [NOUVEL APPAREIL CONNECTÉ]\033[0m IP: \033[1m{ip}\033[0m | Type: \033[96m{device_type}\033[0m (Port: {port})")
                print(f"   UA: {user_agent[:90]}...")
            else:
                dev = self.devices[ip]
                dev["last_seen"] = timestamp
                dev["last_port"] = port
                dev["total_requests"] += 1
                dev["last_path"] = path
                if user_agent and not dev["user_agent"]:
                    dev["user_agent"] = user_agent
                    dev["device_type"] = device_type

            # File log
            self._append_log(f"[{timestamp}] [REQUEST] IP: {ip}:{port} | {method} {path} | Device: {device_type}")
            self._save_json()

    def on_response(self, ip: str, path: str, status_code: int, bytes_sent: int = 0):
        """Records the completion of a request."""
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.lock:
            dev = self.devices.get(ip)
            dev_type = dev["device_type"] if dev else "Appareil"
            if dev:
                dev["bytes_sent"] += bytes_sent

            # Format bytes nicely
            size_str = self._format_bytes(bytes_sent)
            self._append_log(f"[{now}] [RESPONSE] IP: {ip} | {path} -> {status_code} | Taille: {size_str}")

    def on_error(self, ip: str, path: str, error_type: str, message: str, details: Optional[dict] = None):
        """Records an error or unexpected disconnection encountered for a device."""
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        error_entry = {
            "timestamp": now,
            "path": path,
            "error_type": error_type,
            "message": message,
            "details": details or {}
        }

        with self.lock:
            dev = self.devices.get(ip)
            dev_name = dev["device_type"] if dev else "Inconnu"
            if dev:
                dev["errors_count"] += 1
                dev["errors"].append(error_entry)

            # High-visibility console warning
            print(f"\n\033[91m\033[1m⚠️  [PROBLÈME APPAREIL DÉTECTÉ]\033[0m")
            print(f"   Appareil : \033[93m{ip}\033[0m ({dev_name})")
            print(f"   Route    : {path}")
            print(f"   Erreur   : \033[1m{error_type}\033[0m - {message}")
            if details:
                print(f"   Détails  : {details}")
            print()

            self._append_log(f"[{now}] [ERROR] IP: {ip} ({dev_name}) | Route: {path} | {error_type}: {message} | Details: {details}")
            self._save_json()

    def on_client_telemetry(self, ip: str, payload: dict):
        """Processes client-side diagnostic reports sent by the HTML5 web player via POST /api/log."""
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        event = payload.get("event", "client_event")
        details = payload.get("details", {})
        err_msg = payload.get("message") or str(details)

        error_entry = {
            "timestamp": now,
            "source": "client_player",
            "event": event,
            "message": err_msg,
            "raw": payload
        }

        with self.lock:
            dev = self.devices.get(ip)
            dev_name = dev["device_type"] if dev else "Client Web"
            if dev:
                dev["errors_count"] += 1
                dev["errors"].append(error_entry)

            print(f"\n\033[95m\033[1m🚨 [RAPPORT DIAGNOSTIC DU LECTEUR WEB]\033[0m")
            print(f"   Appareil : \033[93m{ip}\033[0m ({dev_name})")
            print(f"   Événement: {event}")
            print(f"   Message  : {err_msg}")
            print()

            self._append_log(f"[{now}] [CLIENT_TELEMETRY] IP: {ip} ({dev_name}) | Event: {event} | {err_msg}")
            self._save_json()

    def _append_log(self, line: str):
        """Appends a line to the devices activity log file."""
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except IOError:
            pass

    def _save_json(self):
        """Dumps current devices registry to JSON file."""
        try:
            with open(self.json_file, "w", encoding="utf-8") as f:
                json.dump(self.devices, f, indent=2, ensure_ascii=False)
        except IOError:
            pass

    @staticmethod
    def _format_bytes(num_bytes: int) -> str:
        """Formats byte count into readable KB/MB string."""
        if num_bytes < 1024:
            return f"{num_bytes} B"
        elif num_bytes < 1024 * 1024:
            return f"{num_bytes / 1024:.1f} KB"
        else:
            return f"{num_bytes / (1024 * 1024):.2f} MB"
