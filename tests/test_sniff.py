#!/usr/bin/env python3
"""
Stream & XHR Traffic Detector
==============================
Inspects and sniffs HTML and network requests/responses (XHR, Fetch, Media, WebSocket)
from video streaming pages using Undetected ChromeDriver and Selenium-Wire.

Features:
- Anti-detection: eliminates navigator.webdriver, patches CDC signatures, realistic browser properties.
- TLS Fingerprint precautions: authentic BoringSSL TLS stack via native Chrome (CDP mode) or patched Selenium-Wire.
- Non-headless: runs in a visible browser window for maximum evasion of bot-defense checks.
- Comprehensive capture: saves HTML, parses video/iframe/source tags, logs requests & responses to JSON.
"""

import os
import sys
import time
import json
import re
import argparse
from urllib.parse import urlparse
from selenium.webdriver.common.by import By

# Patch OpenSSL / mitmproxy for Selenium-Wire compatibility on Python 3.12+ / 3.13
def patch_seleniumwire_ssl():
    try:
        from seleniumwire.thirdparty.mitmproxy.certs import Cert
        from cryptography import x509

        def patched_altnames(self):
            altnames = []
            try:
                crypto_cert = self.x509.to_cryptography()
                san_ext = crypto_cert.extensions.get_extension_for_oid(x509.ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
                for name in san_ext.value:
                    if isinstance(name, x509.DNSName):
                        altnames.append(name.value.encode('utf-8'))
                    elif isinstance(name, x509.IPAddress):
                        altnames.append(str(name.value).encode('utf-8'))
            except Exception:
                pass
            return altnames

        Cert.altnames = property(patched_altnames)
    except Exception:
        pass


def extract_media_candidates_from_html(html: str):
    """Parses HTML for potential video sources, iframes, and stream URLs."""
    candidates = []

    # 1. Regex for direct video/stream extensions in attributes or text
    pattern_streams = re.compile(r'https?://[^\s"\'<>]+\.(?:m3u8|mp4|webm|mpd)(?:\?[^\s"\'<>]*)?', re.IGNORECASE)
    for match in pattern_streams.findall(html):
        candidates.append({"type": "Direct Stream URL (Regex)", "url": match})

    # 2. Extract iframes
    pattern_iframes = re.compile(r'<iframe[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)
    for match in pattern_iframes.findall(html):
        candidates.append({"type": "IFrame Source", "url": match})

    # 3. Extract <video> or <source> tags
    pattern_sources = re.compile(r'<source[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)
    for match in pattern_sources.findall(html):
        candidates.append({"type": "Video <source>", "url": match})

    # 4. Extract common player setups (JWPlayer, Video.js, Clappr, Plyr, hls.js)
    pattern_player_src = re.compile(r'(?:file|source|src|stream)\s*:\s*["\'](https?://[^\s"\']+)["\']', re.IGNORECASE)
    for match in pattern_player_src.findall(html):
        if any(ext in match.lower() for ext in ['.m3u8', '.mp4', 'stream', 'hls', 'playlist']):
            candidates.append({"type": "JS Player Config", "url": match})

    # Deduplicate by url
    seen = set()
    unique = []
    for c in candidates:
        if c["url"] not in seen:
            seen.add(c["url"])
            unique.append(c)
    return unique


def get_chrome_version_main():
    """Auto-detects the installed Chrome/Chromium major version."""
    import subprocess
    for cmd in ["google-chrome --version", "google-chrome-stable --version", "chromium --version", "chromium-browser --version"]:
        try:
            out = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL).strip()
            match = re.search(r'(\d+)\.', out)
            if match:
                return int(match.group(1))
        except Exception:
            pass
    return None


def run_with_undetected_chrome(url: str, output_dir: str, duration: int = 30, version_main: int = None, headless: bool = False, early_exit: bool = False, quiet: bool = False):
    """
    Runs Undetected ChromeDriver with Chrome DevTools Protocol (CDP) Network Logging.
    
    TLS Fingerprint Precaution:
    Uses Chrome's native BoringSSL TLS stack directly. Does NOT route through a Python MITM proxy,
    which ensures JA3/JA4 TLS fingerprint is 100% genuine Google Chrome.
    """
    import undetected_chromedriver as uc

    # Find Chrome browser binary
    browser_executable = None
    for cand in [
        "/usr/bin/google-chrome-stable",
        "/usr/bin/google-chrome",
        "/opt/google/chrome/google-chrome",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/usr/bin/brave-browser",
        "/opt/brave.com/brave/brave-browser",
    ]:
        if os.path.exists(cand) and os.access(cand, os.X_OK):
            browser_executable = cand
            break

    # Find existing patched undetected_chromedriver binary
    driver_executable = None
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for cand in [
        os.path.join(project_root, ".uc_data", "undetected_chromedriver"),
        os.path.join(output_dir, ".uc_data", "undetected_chromedriver"),
    ]:
        if os.path.exists(cand) and os.access(cand, os.X_OK):
            driver_executable = cand
            break

    if not version_main:
        version_main = get_chrome_version_main() or 150

    if not quiet:
        print("\n[+] Starting Undetected ChromeDriver...", flush=True)
        print(f"    • Mode: {'Headless' if headless else 'Headful (Visible window)'}", flush=True)
        print("    • Anti-Detection: Patched ChromeDriver binary (no CDC signatures)", flush=True)
        print("    • TLS Precautions: Native BoringSSL TLS stack (authentic browser fingerprint)", flush=True)
        if browser_executable:
            print(f"    • Chrome Binary: {browser_executable}", flush=True)
        if driver_executable:
            print(f"    • Driver Executable: {driver_executable}", flush=True)
        elif version_main:
            print(f"    • Chrome Major Version: {version_main}", flush=True)

    # Ensure writable data path for patcher
    uc_data_path = os.path.abspath(os.path.join(project_root, ".uc_data"))
    os.makedirs(uc_data_path, exist_ok=True)
    uc.Patcher.data_path = uc_data_path

    options = uc.ChromeOptions()
    options.page_load_strategy = "none"
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--lang=en-US,en,ar")
    options.add_argument("--window-size=1280,850")
    if headless:
        options.add_argument("--headless=new")

    # Enable Performance logging to capture all network requests & responses via CDP
    options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

    driver_kwargs = {"options": options, "headless": headless}
    if browser_executable:
        driver_kwargs["browser_executable_path"] = browser_executable
    if driver_executable:
        driver_kwargs["driver_executable_path"] = driver_executable
    if version_main:
        driver_kwargs["version_main"] = version_main

    driver = uc.Chrome(**driver_kwargs)

    captured_requests = []
    captured_streams = []

    try:
        # Enable CDP Network domain to capture response bodies and headers
        try:
            driver.execute_cdp_cmd("Network.enable", {})
        except Exception:
            pass

        if not quiet:
            print(f"[+] Navigating to: {url}...", flush=True)
        driver.get(url)
        if not quiet:
            print(f"[+] Navigation initiated. Sniffing live traffic and player for {duration}s...", flush=True)
            print("    (You can interact with the player, click play, or inspect elements in the browser)", flush=True)

        start_time = time.time()
        seen_request_ids = set()

        while time.time() - start_time < duration:
            time.sleep(2)

            # Close unexpected popup tabs / ads
            try:
                if len(driver.window_handles) > 1:
                    orig_h = driver.window_handles[0]
                    for h in driver.window_handles[1:]:
                        driver.switch_to.window(h)
                        driver.close()
                    driver.switch_to.window(orig_h)
            except Exception:
                pass

            # 1. Try to trigger playback on main document
            try:
                driver.execute_script("""
                    const selectors = [
                        '.vjs-big-play-button',
                        '.jw-display-icon-container',
                        '#play_btn',
                        '.play-button',
                        'button.play',
                        'div[class*="play"]',
                        'div[class*="player"]',
                        'video'
                    ];
                    for (let sel of selectors) {
                        let el = document.querySelector(sel);
                        if (el) { el.click(); break; }
                    }
                """)
            except Exception:
                pass

            # 2. Try to trigger playback inside iframes (e.g. Cat-Player / Vidstream)
            try:
                frames = driver.find_elements(By.TAG_NAME, "iframe")
                for f_idx, frame in enumerate(frames):
                    try:
                        driver.switch_to.frame(frame)
                        # Check candidates inside iframe DOM and save HTML
                        try:
                            f_html = driver.page_source
                            iframe_save_path = os.path.join(output_dir, f"captured_iframe_{f_idx}.html")
                            with open(iframe_save_path, "w", encoding="utf-8") as f_out:
                                f_out.write(f_html)
                            f_cands = extract_media_candidates_from_html(f_html)
                            for c in f_cands:
                                captured_streams.append({"source": f"Iframe [{f_idx}] ({c['type']})", "url": c["url"]})
                        except Exception:
                            pass

                        # Click play inside iframe
                        driver.execute_script("""
                            const selectors = [
                                '.play-button',
                                'button',
                                '#player',
                                'video',
                                '.vjs-big-play-button',
                                '.jw-display-icon-container',
                                'div[class*="play"]',
                                'div[class*="player"]',
                                '[aria-label*="play" i]',
                                '[aria-label*="Play" i]',
                                'svg'
                            ];
                            for (let sel of selectors) {
                                let el = document.querySelector(sel);
                                if (el) { el.click(); break; }
                            }
                            const vids = document.querySelectorAll('video');
                            vids.forEach(v => {
                                try { v.muted = true; v.play(); } catch(e){}
                            });
                        """)
                        driver.switch_to.default_content()
                    except Exception:
                        driver.switch_to.default_content()
            except Exception:
                pass

            # Read performance logs in real-time
            try:
                logs = driver.get_log("performance")
            except Exception:
                logs = []

            for entry in logs:
                try:
                    obj = json.loads(entry["message"])
                    message = obj.get("message", {})
                    method = message.get("method", "")
                    params = message.get("params", {})

                    if method == "Network.requestWillBeSent":
                        req = params.get("request", {})
                        req_id = params.get("requestId")
                        req_url = req.get("url", "")
                        req_type = params.get("type", "Other")

                        if req_id and req_id not in seen_request_ids:
                            seen_request_ids.add(req_id)
                            item = {
                                "requestId": req_id,
                                "type": req_type,
                                "method": req.get("method"),
                                "url": req_url,
                                "requestHeaders": req.get("headers", {}),
                                "status": None,
                                "responseHeaders": {},
                                "mimeType": None,
                            }
                            captured_requests.append(item)

                            # Highlight media and XHR
                            if any(ext in req_url.lower() for ext in [".m3u8", ".mpd", ".ts", ".mp4", "stream", "video"]) or req_type in ["XHR", "Fetch", "Media"]:
                                if not quiet:
                                    print(f"    [XHR/Media Request] [{req_type}] {req.get('method')} {req_url[:120]}", flush=True)
                                if any(ext in req_url.lower() for ext in [".m3u8", ".mp4", ".mpd", "see.php"]):
                                    captured_streams.append({"source": "CDP Request", "url": req_url})

                    elif method == "Network.responseReceived":
                        resp = params.get("response", {})
                        req_id = params.get("requestId")
                        status = resp.get("status")
                        mime = resp.get("mimeType", "")
                        resp_url = resp.get("url", "")
                        res_type = params.get("type", "")

                        # Update status in captured_requests
                        for item in captured_requests:
                            if item.get("requestId") == req_id:
                                item["status"] = status
                                item["responseHeaders"] = resp.get("headers", {})
                                item["mimeType"] = mime
                                break

                        if "video" in mime or "mpegurl" in mime or any(ext in resp_url.lower() for ext in [".m3u8", ".mpd", ".mp4"]):
                            if not quiet:
                                print(f"    ⭐ [STREAM DETECTED] Status {status} | MIME: {mime} | URL: {resp_url}", flush=True)
                            captured_streams.append({"source": f"CDP Response ({mime})", "url": resp_url})

                        # Inspect XHR/JSON response bodies for embedded stream links
                        if "json" in mime or res_type in ["XHR", "Fetch"] or any(k in resp_url.lower() for k in ["source", "cat-player", "api", "stream"]):
                            try:
                                body_res = driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": req_id})
                                body_text = body_res.get("body", "")
                                p = re.compile(r'https?://[^\s"\'<>]+\.(?:m3u8|mp4|webm|mpd)(?:\?[^\s"\'<>]*)?', re.IGNORECASE)
                                for match in p.findall(body_text):
                                    if not quiet:
                                        print(f"    ⭐ [STREAM IN BODY] {match}", flush=True)
                                    captured_streams.append({"source": "CDP Body", "url": match})
                            except Exception:
                                pass

                except Exception:
                    pass

            if early_exit and any(s.get("source", "").startswith("CDP") and (".m3u8" in s["url"] or ".mp4" in s["url"]) for s in captured_streams):
                if not quiet:
                    print("\n[⚡] Stream playlist detected via network! Exiting early...", flush=True)
                break

        if not quiet:
            print("\n[+] Capturing page HTML source...", flush=True)
        html_content = driver.page_source
        html_candidates = extract_media_candidates_from_html(html_content)
        for cand in html_candidates:
            captured_streams.append({"source": cand["type"], "url": cand["url"]})

        # Save HTML
        html_path = os.path.join(output_dir, "captured_page.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        if not quiet:
            print(f"[✔] Page HTML saved to: {html_path}")

        # Save Requests JSON
        req_path = os.path.join(output_dir, "captured_requests.json")
        with open(req_path, "w", encoding="utf-8") as f:
            json.dump(captured_requests, f, indent=2, ensure_ascii=False)
        if not quiet:
            print(f"[✔] Captured {len(captured_requests)} requests saved to: {req_path}")

        # Save and display detected streams
        return save_and_display_streams(captured_streams, output_dir, quiet=quiet)

    finally:
        if not quiet:
            print("[+] Closing browser...")
        try:
            driver.quit()
        except Exception:
            pass


def run_with_selenium_wire(url: str, output_dir: str, duration: int = 30):
    """
    Runs Selenium-Wire proxy to intercept full request and response payloads.
    Uses patched SSL altnames for Python 3.13 compatibility.
    """
    patch_seleniumwire_ssl()
    from seleniumwire import webdriver
    from selenium.webdriver.chrome.options import Options as ChromeOptions

    print("\n[+] Starting Selenium-Wire with Chrome...")
    print("    • Mode: Headful (Visible window, no headless)")
    print("    • Interception: Full HTTP/HTTPS request & response proxy inspection")

    sw_options = {
        "disable_encoding": True,
        "suppress_connection_errors": True,
        "verify_ssl": False,
    }

    options = ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    driver = webdriver.Chrome(options=options, seleniumwire_options=sw_options)

    # Stealth script injection
    stealth_js = """
    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
    window.chrome = { runtime: {} };
    Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en', 'ar']});
    Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
    """
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": stealth_js})

    captured_requests = []
    captured_streams = []

    try:
        print(f"[+] Navigating to: {url}")
        driver.get(url)

        print(f"[+] Page loaded. Waiting {duration}s for traffic to populate...")
        time.sleep(duration)

        print("\n[+] Processing intercepted Selenium-Wire requests...")
        for req in driver.requests:
            res = req.response
            status = res.status_code if res else None
            content_type = res.headers.get("Content-Type", "") if res else ""
            
            entry = {
                "url": req.url,
                "method": req.method,
                "status": status,
                "contentType": content_type,
                "requestHeaders": dict(req.headers),
                "responseHeaders": dict(res.headers) if res else {},
            }
            captured_requests.append(entry)

            # Check for media streams
            if any(ext in req.url.lower() for ext in [".m3u8", ".mpd", ".ts", ".mp4"]) or "video" in content_type or "mpegurl" in content_type:
                print(f"    ⭐ [STREAM DETECTED] [{status}] {content_type} | {req.url}")
                captured_streams.append({"source": f"Selenium-Wire ({content_type or 'URL pattern'})", "url": req.url})

        # Save HTML
        html_content = driver.page_source
        html_candidates = extract_media_candidates_from_html(html_content)
        for cand in html_candidates:
            captured_streams.append({"source": cand["type"], "url": cand["url"]})

        html_path = os.path.join(output_dir, "captured_page.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        print(f"[✔] Page HTML saved to: {html_path}")

        # Save Requests JSON
        req_path = os.path.join(output_dir, "captured_requests.json")
        with open(req_path, "w", encoding="utf-8") as f:
            json.dump(captured_requests, f, indent=2, ensure_ascii=False)
        print(f"[✔] Captured {len(captured_requests)} requests saved to: {req_path}")

        save_and_display_streams(captured_streams, output_dir)

    finally:
        print("[+] Closing browser...")
        try:
            driver.quit()
        except Exception:
            pass


def save_and_display_streams(streams, output_dir, quiet: bool = False):
    """Formats and prints detected stream URLs and saves them to a text file."""
    # Deduplicate
    seen = set()
    unique = []
    for s in streams:
        if s["url"] not in seen:
            seen.add(s["url"])
            unique.append(s)

    out_file = os.path.join(output_dir, "detected_streams.txt")
    with open(out_file, "w", encoding="utf-8") as f:
        f.write("# Detected Video Streams & Media URLs\n")
        for idx, item in enumerate(unique, 1):
            f.write(f"[{item['source']}] {item['url']}\n")

    if not quiet:
        print("\n" + "=" * 60)
        print(f"🎬 DETECTED STREAMS / MEDIA CANDIDATES ({len(unique)} found):")
        print("=" * 60)
        if unique:
            for idx, item in enumerate(unique, 1):
                print(f"  {idx}. [{item['source']}]\n     URL: {item['url']}\n")
        else:
            print("  (No direct .m3u8/.mp4 stream URLs detected in initial window)")
        print(f"[✔] Stream list saved to: {out_file}")
        print("=" * 60 + "\n")
    return unique


def main():
    parser = argparse.ArgumentParser(description="Sniff HTML and XHR/HTTP requests from streaming pages.")
    parser.add_argument(
        "--url",
        default="https://yam.ahwaktv.net/see.php?vid=f8ba4b0ce",
        help="Target streaming URL to inspect"
    )
    parser.add_argument(
        "--mode",
        choices=["uc", "wire"],
        default="uc",
        help="Capture engine: 'uc' (Undetected ChromeDriver with CDP network capture, best for anti-bot & TLS) or 'wire' (Selenium-Wire proxy)"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=25,
        help="Time (in seconds) to keep the browser open and capture live requests"
    )
    parser.add_argument(
        "--version-main",
        type=int,
        default=None,
        help="Chrome major version (default: auto-detected)"
    )
    parser.add_argument(
        "--output-dir",
        default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output"),
        help="Directory to save captured files (default: output/)"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run Chrome in headless mode"
    )

    parser.add_argument(
        "--early-exit",
        action="store_true",
        help="Exit immediately once a valid .m3u8 stream is detected"
    )

    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    print("=" * 60, flush=True)
    print("🔎 EGY-Stream XHR & Network Traffic Sniffer", flush=True)
    print(f"   Target URL : {args.url}", flush=True)
    print(f"   Engine     : {args.mode.upper()}", flush=True)
    print(f"   Headless   : {args.headless}", flush=True)
    print(f"   Early Exit : {args.early_exit}", flush=True)
    print(f"   Duration   : {args.timeout} seconds", flush=True)
    print(f"   Output Dir : {args.output_dir}", flush=True)
    print("=" * 60, flush=True)

    if args.mode == "uc":
        run_with_undetected_chrome(args.url, args.output_dir, args.timeout, version_main=args.version_main, headless=args.headless, early_exit=args.early_exit)
    else:
        run_with_selenium_wire(args.url, args.output_dir, args.timeout)


if __name__ == "__main__":
    main()
