#!/usr/bin/env python3
"""
EGY-Stream - Main Application Entrypoint
=========================================
Unified CLI for searching across providers (Cineby/Cinejoy and EGY-Stream),
extracting HLS streams automatically, and launching instant MPV playback.
"""
import argparse
import sys
from typing import Optional

from config import STREAM_PROXY_PORT
from utils.logger import setup_logger
from utils.ui import TerminalUI
from services.search_service import SearchService
from services.extractor_service import ExtractorService
from services.player_service import PlayerService
from services.stream_proxy_service import StreamProxyService
from models.video import Video


class EgyStreamApp:
    """Core CLI Application controller managing multi-provider search, selection, and auto-playback."""

    def __init__(self, debug: bool = False, share_mode: bool = False, mpv_mode: bool = False):
        self.logger = setup_logger(level="DEBUG" if debug else "INFO")
        self.search_service = SearchService(logger=self.logger)
        self.extractor_service = ExtractorService(logger=self.logger)
        self.player_service = PlayerService(logger=self.logger)
        self.share_mode = share_mode
        self.mpv_mode = mpv_mode
        self.active_proxy: Optional[StreamProxyService] = None

    def run(self, initial_query: Optional[str] = None):
        """Main application lifecycle loop."""
        TerminalUI.print_banner()

        query = initial_query
        while True:
            if not query:
                query = TerminalUI.prompt_query()
                if not query:
                    print("Goodbye!")
                    break

            print(f"\n🔍 Searching across providers for '{query}'...")
            videos = self.search_service.search(query)
            if not videos:
                print(f"❌ No results found for '{query}'. Try a different keyword.\n")
                query = None
                continue

            # Selection Loop for current results
            current_page = 1
            page_size = 50
            total_pages = max(1, (len(videos) + page_size - 1) // page_size)

            while True:
                TerminalUI.display_results(videos, page=current_page, page_size=page_size)
                action, choice = TerminalUI.prompt_choice(
                    total_items=len(videos),
                    current_page=current_page,
                    total_pages=total_pages
                )

                if action == "quit":
                    self._cleanup_proxy()
                    print("Goodbye!")
                    sys.exit(0)

                if action == "back":
                    query = None
                    break

                if action == "next":
                    if current_page < total_pages:
                        current_page += 1
                    continue

                if action == "prev":
                    if current_page > 1:
                        current_page -= 1
                    continue

                selected_video = videos[choice]

                # For anime series (e.g. WitAnime), load and prompt for episode selection
                if getattr(selected_video, "provider", None) == "witanime" and "/anime/" in (selected_video.page_url or ""):
                    print(f"\n⏳ Loading episodes for: {selected_video.title}...")
                    episodes = self.extractor_service.get_anime_episodes(selected_video.page_url)
                    if episodes:
                        selected_video.episodes = episodes
                        if len(episodes) > 1:
                            chosen_ep = TerminalUI.prompt_episode(episodes)
                        else:
                            chosen_ep = episodes[0]
                        if chosen_ep:
                            selected_video.selected_episode = chosen_ep
                            selected_video.title = f"{selected_video.title} - {chosen_ep.get('type', 'الحلقة')} {chosen_ep.get('number', '')}"
                            selected_video.page_url = chosen_ep.get("url", selected_video.page_url)
                    else:
                        print("⚠️ Could not retrieve episode catalog. Attempting direct resolution...")

                print(f"\n⏳ Resolving stream for: {selected_video.title}...")

                stream_url = self.extractor_service.extract_stream(selected_video)
                if not stream_url:
                    print(f"❌ Failed to extract stream URL for {selected_video.title}.")
                    continue

                # Check for available video resolutions in HLS playlist
                resolutions = self.extractor_service.parse_hls_resolutions(
                    master_url=stream_url,
                    referer=selected_video.embed_url or selected_video.page_url
                )
                selected_video.available_resolutions = resolutions
                if len(resolutions) > 1:
                    chosen_res = TerminalUI.prompt_resolution(resolutions)
                    if chosen_res:
                        selected_video.selected_resolution = chosen_res
                        selected_video.selected_vid = chosen_res["index"]
                        print(f"✅ Selected resolution: {chosen_res['name']}")

                # Choose playback / sharing mode
                if self.share_mode:
                    action = "2"
                elif self.mpv_mode:
                    action = "1"
                else:
                    action = TerminalUI.prompt_playback_action(selected_video.title)

                if action == "4":  # Back
                    continue

                if action in ["2", "3"]:
                    # Start Local Wi-Fi Stream Proxy (shows the TV sharing banner)
                    self._start_proxy(selected_video)

                if action in ["1", "3"]:
                    # Play locally with MPV
                    self.player_service.play(selected_video)

                if action == "2":
                    # Keep proxy running while user streams on Smart TV
                    try:
                        input("\n📡 Proxy is running! Press [Enter] anytime to stop sharing on Wi-Fi: ")
                    except (KeyboardInterrupt, EOFError):
                        pass
                    self._cleanup_proxy()
                elif action == "3":
                    # Ask if user wants to keep proxy running after MPV closes
                    try:
                        keep = input("\n📡 MPV closed. Keep sharing stream on Wi-Fi? (y/N): ").strip().lower()
                        if keep in ["y", "yes"]:
                            input("Press [Enter] anytime to stop sharing on Wi-Fi: ")
                    except (KeyboardInterrupt, EOFError):
                        pass
                    self._cleanup_proxy()

                # Reset to allow another search or another pick
                print("\n" + "─" * 65)
                try:
                    next_action = input("Press [Enter] to choose another video from list, or enter a new query ('q' to quit): ").strip()
                except (KeyboardInterrupt, EOFError):
                    self._cleanup_proxy()
                    print("\nGoodbye!")
                    sys.exit(0)

                if next_action.lower() in ["q", "quit", "exit"]:
                    self._cleanup_proxy()
                    print("Goodbye!")
                    sys.exit(0)
                elif next_action:
                    query = next_action
                    break

    def _start_proxy(self, video: Video):
        """Starts the local LAN HLS micro-proxy for the given video."""
        self._cleanup_proxy()
        self.active_proxy = StreamProxyService(
            video=video,
            port=STREAM_PROXY_PORT,
            logger=self.logger
        )
        self.active_proxy.start(background=True)
        self.active_proxy.print_sharing_banner()

    def _cleanup_proxy(self):
        """Stops any running proxy server."""
        if self.active_proxy and self.active_proxy.is_running:
            self.active_proxy.stop()
            self.active_proxy = None


def main():
    parser = argparse.ArgumentParser(description="EGY-Stream: Unified CLI video search and playback.")
    parser.add_argument(
        "search_query",
        nargs="?",
        default=None,
        help="Initial search keyword"
    )
    parser.add_argument(
        "-q", "--query",
        type=str,
        default=None,
        help="Initial search keyword"
    )
    parser.add_argument(
        "--share",
        action="store_true",
        help="Directly start Wi-Fi stream proxy for Smart TV (skips menu)"
    )
    parser.add_argument(
        "--mpv",
        action="store_true",
        help="Directly launch MPV locally (skips menu)"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )
    args = parser.parse_args()

    initial_query = args.search_query or args.query
    app = EgyStreamApp(debug=args.debug, share_mode=args.share, mpv_mode=args.mpv)
    app.run(initial_query=initial_query)


if __name__ == "__main__":
    main()
