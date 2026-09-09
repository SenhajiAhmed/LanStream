"""
EGY-Stream Configuration
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Provider Configuration
BASE_URL = "https://yam.ahwaktv.net"
SEARCH_URL = f"{BASE_URL}/search.php"
WITANIME_BASE_URL = "https://witanime.you"
WITANIME_SEARCH_URL = f"{WITANIME_BASE_URL}/?search_param=animes"

# HTTP Headers
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": f"{BASE_URL}/",
}

# Directories
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

SEARCH_RESULTS_FILE = os.path.join(OUTPUT_DIR, "search_results.json")
APP_LOG_FILE = os.path.join(OUTPUT_DIR, "app.log")
DEVICES_LOG_FILE = os.path.join(OUTPUT_DIR, "devices_activity.log")
DEVICES_JSON_FILE = os.path.join(OUTPUT_DIR, "connected_devices.json")

# Player settings
MPV_BINARY = "mpv"
REQUEST_TIMEOUT = 25
DEFAULT_TIMEOUT = REQUEST_TIMEOUT

# Local LAN Stream Proxy (Option A)
STREAM_PROXY_PORT = 8080

