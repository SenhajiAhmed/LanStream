"""
Player Service
"""
import shutil
import subprocess
from urllib.parse import urlparse
from config import MPV_BINARY
from models.video import Video


class PlayerService:
    """Handles video playback via MPV media player."""

    def __init__(self, logger=None):
        self.logger = logger
        self.mpv_available = shutil.which(MPV_BINARY) is not None

    def play(self, video: Video) -> bool:
        """Launches MPV to play the video stream."""
        if not self.mpv_available:
            msg = f"'{MPV_BINARY}' media player was not found on your system PATH. Please install it (e.g. sudo apt install mpv / sudo dnf install mpv)."
            if self.logger:
                self.logger.error(msg)
            else:
                print(msg)
            return False

        target_url = video.stream_url or video.embed_url
        if not target_url:
            if self.logger:
                self.logger.error("No stream or embed URL available to play.")
            return False

        cmd = [MPV_BINARY]

        # Pass Referer header if available to prevent 403 Forbidden
        referer = None
        if video.embed_url:
            parsed = urlparse(video.embed_url)
            referer = f"{parsed.scheme}://{parsed.netloc}/"
        elif video.page_url:
            parsed = urlparse(video.page_url)
            referer = f"{parsed.scheme}://{parsed.netloc}/"

        if referer:
            headers = f"Referer: {referer}"
            if "cinejoy" in referer or "cineby" in referer:
                headers += f",Origin: {referer.rstrip('/')}"
            cmd.append(f"--http-header-fields={headers}")

        if video.title:
            cmd.append(f"--force-media-title={video.title}")

        if getattr(video, "selected_vid", None):
            cmd.append(f"--vid={video.selected_vid}")
        elif getattr(video, "selected_resolution", None) and video.selected_resolution.get("bandwidth"):
            cmd.append(f"--hls-bitrate={video.selected_resolution['bandwidth']}")

        # Network resilience and high-capacity buffering to survive internet drops
        cmd.extend([
            "--demuxer-max-bytes=150M",
            "--demuxer-max-back-bytes=50M",
            "--demuxer-readahead-secs=120",
            "--network-timeout=30",
        ])

        cmd.append(target_url)

        if self.logger:
            self.logger.info(f"Launching playback for: {video.title}")
            self.logger.info(f"Stream URL: {target_url}")

        print(f"\n▶ Starting MPV playback for: {video.title}")
        print("  (Press 'q' in the player window or Ctrl+C to stop playback)\n")

        try:
            subprocess.run(cmd, check=False)
            return True
        except KeyboardInterrupt:
            print("\nPlayback stopped by user.")
            return True
        except Exception as e:
            if self.logger:
                self.logger.error(f"Playback error: {e}")
            return False
