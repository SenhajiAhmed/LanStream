"""
Terminal User Interface Utilities
"""
import sys
from typing import List, Optional
from models.video import Video


class TerminalUI:
    """Handles terminal formatting, menus, and user input prompts."""

    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"

    @classmethod
    def print_banner(cls):
        banner = f"""
{cls.CYAN}{cls.BOLD}╔═══════════════════════════════════════════════════════════╗
║                   📺  E G Y - S T R E A M                 ║
║          CLI Video Search, Stream Extraction & Playback   ║
╚═══════════════════════════════════════════════════════════╝{cls.RESET}
"""
        print(banner)

    @classmethod
    def prompt_query(cls) -> Optional[str]:
        """Prompts the user for a search keyword."""
        try:
            query = input(f"{cls.BOLD}{cls.YELLOW}🔍 Enter search query (or 'q' to quit): {cls.RESET}").strip()
            if query.lower() in ["q", "quit", "exit"]:
                return None
            return query
        except (KeyboardInterrupt, EOFError):
            print("\nExiting...")
            sys.exit(0)

    @classmethod
    def display_results(cls, videos: List[Video]):
        """Displays search results in a clean numbered list with provider tags."""
        print(f"\n{cls.BOLD}{cls.GREEN}📋 Search Results ({len(videos)} found):{cls.RESET}")
        print("─" * 65)
        for idx, video in enumerate(videos, start=1):
            provider = getattr(video, "provider", "egy-stream")
            if provider in ["cineby", "cinejoy"]:
                tag = f"{cls.BOLD}{cls.YELLOW}[cineby]{cls.RESET}"
                extra = []
                if getattr(video, "year", None):
                    extra.append(str(video.year))
                if getattr(video, "rating", None):
                    extra.append(f"⭐ {video.rating}/10")
                extra_str = f" ({', '.join(extra)})" if extra else ""
                print(f"  {cls.BOLD}{cls.CYAN}{idx:2d}.{cls.RESET} {tag} {video.title}{extra_str} {cls.DIM}[ID: {video.id}]{cls.RESET}")
            elif provider == "witanime":
                tag = f"{cls.BOLD}{cls.BLUE}[witanime]{cls.RESET}"
                print(f"  {cls.BOLD}{cls.CYAN}{idx:2d}.{cls.RESET} {tag} {video.title} {cls.DIM}[ID: {video.id}]{cls.RESET}")
            else:
                tag = f"{cls.BOLD}{cls.GREEN}[egy-stream]{cls.RESET}"
                print(f"  {cls.BOLD}{cls.CYAN}{idx:2d}.{cls.RESET} {tag} {video.title} {cls.DIM}[ID: {video.id}]{cls.RESET}")
        print("─" * 65)

    @classmethod
    def prompt_choice(cls, max_val: int) -> Optional[int]:
        """Prompts the user to choose an index (1 to max_val)."""
        while True:
            try:
                raw = input(f"\n{cls.BOLD}{cls.YELLOW}👉 Select a video number (1-{max_val}, 'b' to back, 'q' to quit): {cls.RESET}").strip()
                if raw.lower() in ["b", "back"]:
                    return -1
                if raw.lower() in ["q", "quit", "exit"]:
                    return None
                
                choice = int(raw)
                if 1 <= choice <= max_val:
                    return choice - 1
                print(f"{cls.RED}⚠ Please enter a number between 1 and {max_val}.{cls.RESET}")
            except ValueError:
                print(f"{cls.RED}⚠ Invalid input. Please enter a valid number.{cls.RESET}")
            except (KeyboardInterrupt, EOFError):
                print("\nExiting...")
                sys.exit(0)

    @classmethod
    def prompt_playback_action(cls, video_title: str) -> str:
        """Prompts user for playback mode (MPV, Local Wi-Fi Stream, Both, Back)."""
        print(f"\n{cls.BOLD}{cls.GREEN}🎬 Selected: {cls.CYAN}{video_title}{cls.RESET}")
        print(f"{cls.BOLD}Choose how to play / share:{cls.RESET}")
        print(f"  {cls.BOLD}{cls.CYAN}1.{cls.RESET} ▶️  Play locally with MPV")
        print(f"  {cls.BOLD}{cls.CYAN}2.{cls.RESET} 📡 Share on local Wi-Fi (Start HTTP/HLS Proxy & Web Player)")
        print(f"  {cls.BOLD}{cls.CYAN}3.{cls.RESET} 🚀 Play locally with MPV AND Share on Wi-Fi simultaneously")
        print(f"  {cls.BOLD}{cls.CYAN}4.{cls.RESET} 🔙 Back to search results")

        while True:
            try:
                choice = input(f"\n{cls.BOLD}{cls.YELLOW}👉 Select option (1-4): {cls.RESET}").strip()
                if choice in ["1", "2", "3", "4"]:
                    return choice
                print(f"{cls.RED}⚠ Please choose 1, 2, 3, or 4.{cls.RESET}")
            except (KeyboardInterrupt, EOFError):
                print("\nExiting...")
                sys.exit(0)

    @classmethod
    def prompt_resolution(cls, resolutions: list) -> Optional[dict]:
        """Displays available resolutions and lets the user choose one."""
        if not resolutions:
            return None

        print(f"\n{cls.BOLD}{cls.GREEN}📺 Available Video Resolutions:{cls.RESET}")
        print("─" * 65)
        print(f"  {cls.BOLD}{cls.CYAN} 1.{cls.RESET} ⚡ Auto / Adaptive (Auto quality switching based on network)")
        for idx, res in enumerate(resolutions, start=2):
            rec = f" {cls.YELLOW}[Recommended]{cls.RESET}" if res.get("height") == 1080 else ""
            print(f"  {cls.BOLD}{cls.CYAN}{idx:2d}.{cls.RESET} {res['name']}{rec}")
        print("─" * 65)

        max_val = len(resolutions) + 1
        while True:
            try:
                raw = input(f"\n{cls.BOLD}{cls.YELLOW}👉 Select resolution [1-{max_val}] (Press Enter for Auto): {cls.RESET}").strip()
                if not raw or raw == "1":
                    return None  # Auto / Default master
                choice = int(raw)
                if 2 <= choice <= max_val:
                    return resolutions[choice - 2]
                print(f"{cls.RED}⚠ Please enter a number between 1 and {max_val}.{cls.RESET}")
            except ValueError:
                print(f"{cls.RED}⚠ Invalid input. Please enter a valid number.{cls.RESET}")
            except (KeyboardInterrupt, EOFError):
                return None

    @classmethod
    def prompt_episode(cls, episodes: list) -> Optional[dict]:
        """Displays available episodes and lets the user select one."""
        if not episodes:
            return None

        print(f"\n{cls.BOLD}{cls.GREEN}📑 Available Episodes ({len(episodes)} total):{cls.RESET}")
        print("─" * 65)
        display_limit = 25
        for idx, ep in enumerate(episodes[:display_limit], start=1):
            ep_type = ep.get("type", "الحلقة")
            ep_num = ep.get("number", idx)
            print(f"  {cls.BOLD}{cls.CYAN}{idx:2d}.{cls.RESET} {ep_type} {ep_num}")
        if len(episodes) > display_limit:
            print(f"  {cls.DIM}... and {len(episodes) - display_limit} more episodes (enter any number up to {len(episodes)}){cls.RESET}")
        print("─" * 65)

        max_val = len(episodes)
        while True:
            try:
                raw = input(f"\n{cls.BOLD}{cls.YELLOW}👉 Select episode [1-{max_val}] (Press Enter for Ep 1): {cls.RESET}").strip()
                if not raw:
                    return episodes[0]
                choice = int(raw)
                if 1 <= choice <= max_val:
                    return episodes[choice - 1]
                print(f"{cls.RED}⚠ Please enter a number between 1 and {max_val}.{cls.RESET}")
            except ValueError:
                print(f"{cls.RED}⚠ Invalid input. Please enter a valid number.{cls.RESET}")
            except (KeyboardInterrupt, EOFError):
                return episodes[0]

