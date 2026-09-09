# 🗺️ LanStream: Provider Engineering, Reverse-Engineering & Architectural Roadmap

## 📌 Vision & Overview

**LanStream** is a unified, local streaming hub designed to aggregate content from diverse web video providers, extract their underlying media streams (HLS/fMP4), and broadcast them seamlessly across all local network hardware:
- **Desktop PCs & Laptops** (High-fidelity native playback via MPV / VLC)
- **Mobile Devices** (Universal HTML5 web player with responsive controls on iOS & Android)
- **Smart TVs** (Direct MP4 transmuxing on-the-fly for legacy Samsung Orsay, Tizen, LG webOS, and NetRange devices)

This document serves as the **central repository of reverse-engineering findings**, past and current sniffing results, and the **standardized engineering pipeline** for onboarding new streaming providers into the LanStream core.

---

## 🔄 The 6-Step Provider Integration Lifecycle

Every streaming provider follows an identical, repeatable engineering lifecycle:

```
┌─────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│ 1. Recon &      │ ──> │ 2. Protocol &       │ ──> │ 3. Pipeline         │
│    CDP Sniffing │     │    Security Reverse │     │    Integration      │
└─────────────────┘     └─────────────────────┘     └─────────────────────┘
         │                                                     │
         ▼                                                     ▼
┌─────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│ 6. Validation & │ <── │ 5. Multi-Device     │ <── │ 4. Resolution       │
│    Telemetry    │     │    Proxy Adaptation │     │    Discovery        │
└─────────────────┘     └─────────────────────┘     └─────────────────────┘
```

### 1. Reconnaissance & Network Sniffing (`tests/test_sniff.py`)
- Launch **Undetected ChromeDriver** in headful or headless mode with genuine BoringSSL TLS fingerprinting.
- Attach Chrome DevTools Protocol (`Network.enable`, `Target.setAutoAttach`) to capture all HTTP/2, XHR, and Fetch traffic across all renderer frames.
- Automate iframe traversal (`driver.switch_to.frame`), close intrusive ad popups, and simulate genuine user interaction on media player overlays.
- Dump the top-level DOM, iframe DOMs, and complete structured request logs (`captured_requests.json`).

### 2. Protocol & Security Dissection
- Identify the streaming protocol: Master HLS (`.m3u8`), DASH (`.mpd`), fragmented MP4 (`fMP4`), or direct progressive `.mp4`.
- Detect obfuscation layers:
  - **MIME disguise**: Segments served with `.html` or `.jpg` extensions returning synthetic Content-Types.
  - **Encryption**: AES-128 CBC segment keys (`#EXT-X-KEY:METHOD=AES-128`).
  - **Access policies**: Cross-Origin Resource Sharing (CORS), `Referer` / `Origin` verification, and Cloudflare WAF bot challenges.

### 3. Pipeline Integration (Models & Services)
- **Model**: Register the provider identifier in `models/video.py` (`provider: str = "new-provider"`).
- **Search**: Implement asynchronous or multi-threaded search harvesting in `services/search_service.py` to aggregate results alongside existing catalogs.
- **Extractor**: Build a dedicated extraction function in `services/extractor_service.py` capable of obtaining the direct master stream URL.

### 4. Resolution Discovery & Interactive Prompting
- Query the extracted Master HLS Playlist for `#EXT-X-STREAM-INF` descriptors.
- Parse bandwidth, resolution dimensions (`1920x1080`, `1280x720`, etc.), and frame rates.
- Present the resolution selection menu in `TerminalUI.prompt_resolution()` so the user can choose their preferred quality before streaming begins.

### 5. Multi-Device Proxy Adaptation (`services/stream_proxy_service.py`)
- **Direct M3U8 (`/playlist.m3u8`)**: Rewrite all segment URIs, key URIs, and initialization maps to route through the local proxy with upstream spoofed headers (`Referer`, `User-Agent`).
- **Direct MP4 (`/stream.mp4`)**: Invoke FFmpeg on-the-fly with `-c copy` to remux HLS/fMP4 into progressive MP4 with `faststart` (moov atom at front), stripping AES-128 encryption on the host to enable immediate playback on legacy Smart TVs.
- **Web Player (`/`)**: Serve a responsive HTML5 UI utilizing `Hls.js` with auto-buffer tuning for mobile smartphones and tablets.

### 6. Validation, Error Recovery & Telemetry
- Validate playback on PC (MPV), mobile (browser), and Smart TV (direct streaming).
- Verify connection handling in `services/device_logger_service.py`.
- Ensure connection resilience: fallback to secondary qualities or reconnection loops if upstream drops.

---

## 📊 Catalog of Analyzed & Integrated Providers

### 1. Provider: Cineby (International / TMDB)
- **Status**: ✅ **Fully Integrated**
- **Catalog**: International Movies & TV Shows (English / Multi-language)
- **Search API**: TMDB API integration with rich metadata (ratings ⭐, release dates, overviews).
- **Player Mechanics**:
  - Embedded JWPlayer / custom HTML5 player.
  - Headless CDP sniffer locates the master fMP4 playlist.
- **Underlying Protocol & Peculiarities**:
  - **Format**: HLS with fragmented MP4 (fMP4).
  - **Segment Masking**: Segments are named with `.html` extensions and served with `Content-Type: text/html`.
  - **Initialization Maps**: Relies on `#EXT-X-MAP:URI="video_init.html"` for decoder setup.
  - **Audio Tracks**: Separate audio manifest (`audio.m3u8`).
- **Resolutions Available**:
  - `4K Ultra HD` (3840×2160)
  - `1080p Full HD` (1920×1080)
  - `720p HD` (1280×720)
  - `360p SD` (640×360)
- **LanStream Solution**:
  - `StreamProxyService` transparently inspects each segment request, strips the HTML wrapper/mime-type, and injects `Content-Type: video/mp4`.
  - Rewrites `#EXT-X-MAP` tags to absolute proxy URLs.

---

### 2. Provider: Egy-Stream / Ahwak TV (Middle East / Arabic)
- **Status**: ✅ **Fully Integrated**
- **Catalog**: Arabic Cinema, Egyptian classic & modern movies, Ramadan series.
- **Search API**: Scraped search results from Egy-Stream catalog endpoints.
- **Player Mechanics**:
  - Obfuscated embed (`yam.ahwaktv.net/see.php?vid=...`).
  - Heavy JavaScript packer (`eval(function(p,a,c,k,e,d)...)`).
- **Underlying Protocol & Peculiarities**:
  - **Format**: Standard HLS with MPEG-TS segments.
  - **Encryption**: Protected by AES-128 encryption (`#EXT-X-KEY:METHOD=AES-128,URI="..."`).
  - **Tokens**: Tokenized playlist URLs expiring within minutes.
- **Resolutions Available**:
  - `1080p Full HD` (1920×1080)
  - `720p HD` (1280×720)
  - `480p SD` (854×480)
  - `360p SD` (640×360)
- **LanStream Solution**:
  - JavaScript unpacker extracts direct `.m3u8` tokens without browser overhead.
  - Proxy caches encryption keys locally and serves them with valid CORS headers.
  - FFmpeg remuxing engine decrypts AES-128 on the local host before transmitting progressive MP4 to TV.

---

### 3. Provider: WitAnime (Anime / Arabic Subbed)
- **Status**: ✅ **Fully Integrated**
- **Catalog**: Comprehensive Japanese Anime library with Arabic subtitles.
- **Driver Dependency**: **Zero Browser Driver (100% pure Python `requests`)**.
- **Search API**: Scraped search catalog (`https://witanime.you/?search_param=animes&s=...`).
- **Player Mechanics & Security Reverse-Engineering**:
  - **Episode Catalog Cipher**: Anime detail pages encrypt the entire episode catalog within `var processedEpisodeData = "part1.part2"`. LanStream decodes this via an XOR bitwise cipher over Base64 strings:
    $$\text{decrypted}[i] = \text{part0}[i] \oplus \text{part1}[i \pmod{|\text{part1}|}]$$
    yielding structured JSON with all episode numbers and watch URLs.
  - **Streaming Server Obfuscation (`yh00.js`)**: Episode watch pages embed dynamic servers inside Base64 variables `_zT` and `_zV`. LanStream reverses the strings, strips padding, computes dynamic offset slices, and appends authorization hashes:
    - `ok.ru`: Unpacks `data-module="OKVideo"` JSON to retrieve master HLS playlists and MP4 qualities.
    - `streamwish` (`hgcloud.to`): Unpacks Dean Edwards packer to extract direct `.m3u8` streams.
    - `yonaplay`: Unpacks embedded multi-quality HLS streams.
- **Resolutions Available**:
  - `1080p Full HD` (1920×1080)
  - `720p HD` (1280×720)
  - `480p SD` (854×480)
  - `360p SD` (640×360)
- **LanStream Solution**:
  - 100% headless driver-free extraction running in milliseconds via pure Python standard libraries.
  - Interactive terminal episode selector (`TerminalUI.prompt_episode`).
  - Native multi-resolution prompting and instant MPV / Smart TV proxy streaming.

---

## 🎯 Device Compatibility Matrix

| Client Hardware | Operating System / Browser | Recommended Mode | Streaming URL | Key Architectural Solution |
| :--- | :--- | :--- | :--- | :--- |
| **Desktop / Laptop** | Linux, macOS, Windows (MPV / VLC) | **Native MPV / Direct M3U8** | `http://<IP>:8080/playlist.m3u8` | Header spoofing (`Referer`, `Origin`), resolution auto-selection via `--vid`. |
| **Smartphones / Tablets** | iOS (Safari), Android (Chrome/Firefox) | **Responsive Web Player** | `http://<IP>:8080/` | HTML5 `<video>` + `Hls.js`, auto-quality leveling, touch-friendly UI. |
| **Legacy Smart TV** | Samsung Orsay (Series 3-5), NetRange | **Direct MP4 (Remuxed)** | `http://<IP>:8080/stream.mp4` | FFmpeg on-the-fly copy remuxing (`-c copy`), stripping AES encryption & chunk disguises, instant hardware playback. |
| **Modern Smart TV** | Samsung Tizen, LG webOS, Android TV | **Web Player / Direct MP4** | `http://<IP>:8080/` or `/stream.mp4` | Dual-mode selector on web landing page: Direct MP4 or MSE HLS. |
| **IPTV Set-Top Boxes** | Android TV Boxes, Kodi, MAG | **Direct M3U8** | `http://<IP>:8080/playlist.m3u8` | Rewritten static manifest with relative URI resolution. |

---

## 🚀 Engineering Roadmap & Future Milestones

### Phase 1: Enhanced Media & Track Selection
- [ ] **Subtitle Integration**: Allow users to select subtitle languages (e.g. Arabic, English, French) from CLI and auto-load them into MPV (`--sub-file`) and Web Player.
- [ ] **Audio Track Switching**: Support selecting dubbed vs original audio tracks when multiple `#EXT-X-MEDIA:TYPE=AUDIO` streams are detected.

### Phase 2: Proxy Resilience & Cache Optimization
- [ ] **Adaptive Buffer Pool**: Implement a memory ring-buffer in `StreamProxyService` to preload 30–60 seconds of video chunks for completely stutter-free Smart TV playback.
- [ ] **Auto-Reconnect Daemon**: Add exponential backoff retry in the proxy to seamlessly fetch dropped chunks from alternate CDN mirrors without disconnecting the TV.

### Phase 3: Expansion to Additional Providers
- [ ] Research and sniff additional international streaming portals.
- [ ] Research and sniff French streaming portals (e.g. Wiflix, French-Stream).
- [ ] Research and sniff live sports and event streaming sources.
- [ ] Consolidate a unified provider plugin architecture (`plugins/` directory) for plug-and-play provider registration.
