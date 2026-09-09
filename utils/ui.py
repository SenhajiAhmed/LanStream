"""
Terminal User Interface Utilities
"""
import sys
from typing import List, Optional, Tuple
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
    def display_results(cls, videos: List[Video], page: int = 1, page_size: int = 50):
        """Displays a paginated slice of search results (50 per page max) with clean truncation and provider tags."""
        total = len(videos)
        total_pages = max(1, (total + page_size - 1) // page_size)
        page = max(1, min(page, total_pages))

        start_idx = (page - 1) * page_size
        end_idx = min(start_idx + page_size, total)
        page_videos = videos[start_idx:end_idx]

        print(f"\n{cls.BOLD}{cls.GREEN}📋 Search Results ({total} found — Page {page}/{total_pages} [Items {start_idx + 1}-{end_idx}]):{cls.RESET}")
        print("─" * 72)

        max_title_len = 50
        for offset, video in enumerate(page_videos):
            global_idx = start_idx + offset + 1

            # Cleanly truncate long titles to maintain terminal alignment
            title = video.title.strip()
            if len(title) > max_title_len:
                title = title[:max_title_len - 3] + "..."

            provider = getattr(video, "provider", "egy-stream")
            if provider in ["cineby", "cinejoy"]:
                tag = f"{cls.BOLD}{cls.YELLOW}[cineby]{cls.RESET}"
                extra = []
                if getattr(video, "year", None):
                    extra.append(str(video.year))
                if getattr(video, "rating", None):
                    extra.append(f"⭐ {video.rating}/10")
                extra_str = f" ({', '.join(extra)})" if extra else ""
                print(f"  {cls.BOLD}{cls.CYAN}{global_idx:3d}.{cls.RESET} {tag} {title:<50}{extra_str} {cls.DIM}[ID: {video.id}]{cls.RESET}")
            elif provider == "witanime":
                tag = f"{cls.BOLD}{cls.BLUE}[witanime]{cls.RESET}"
                print(f"  {cls.BOLD}{cls.CYAN}{global_idx:3d}.{cls.RESET} {tag} {title:<50} {cls.DIM}[ID: {video.id}]{cls.RESET}")
            else:
                tag = f"{cls.BOLD}{cls.GREEN}[egy-stream]{cls.RESET}"
                print(f"  {cls.BOLD}{cls.CYAN}{global_idx:3d}.{cls.RESET} {tag} {title:<50} {cls.DIM}[ID: {video.id}]{cls.RESET}")

        print("─" * 72)
        nav_hints = []
        if page < total_pages:
            nav_hints.append(f"{cls.BOLD}'n'{cls.RESET} ➔ Next Page ({page + 1}/{total_pages})")
        if page > 1:
            nav_hints.append(f"{cls.BOLD}'p'{cls.RESET} ➔ Prev Page ({page - 1}/{total_pages})")
        if nav_hints:
            print(f"  {cls.DIM}Navigation: {' | '.join(nav_hints)}{cls.RESET}")

    @classmethod
    def prompt_choice(
        cls, total_items: int, current_page: int = 1, total_pages: int = 1
    ) -> Tuple[str, Optional[int]]:
        """Prompts user to select a video index or navigate pages (next/prev).
        
        Returns:
            (action, choice_index)
            action in ['select', 'next', 'prev', 'back', 'quit']
        """
        while True:
            try:
                options = [f"1-{total_items}"]
                if current_page < total_pages:
                    options.append(f"{cls.BOLD}'n'{cls.RESET} next")
                if current_page > 1:
                    options.append(f"{cls.BOLD}'p'{cls.RESET} prev")
                options.append(f"{cls.BOLD}'b'{cls.RESET} back")
                options.append(f"{cls.BOLD}'q'{cls.RESET} quit")

                prompt_str = f"\n{cls.BOLD}{cls.YELLOW}👉 Select ({', '.join(options)}): {cls.RESET}"
                raw = input(prompt_str).strip().lower()

                if raw in ["q", "quit", "exit"]:
                    return ("quit", None)
                if raw in ["b", "back"]:
                    return ("back", None)
                if raw in ["n", "next"]:
                    if current_page < total_pages:
                        return ("next", None)
                    print(f"{cls.RED}⚠ Already on the last page.{cls.RESET}")
                    continue
                if raw in ["p", "prev", "previous"]:
                    if current_page > 1:
                        return ("prev", None)
                    print(f"{cls.RED}⚠ Already on the first page.{cls.RESET}")
                    continue

                try:
                    choice = int(raw)
                    if 1 <= choice <= total_items:
                        return ("select", choice - 1)
                    print(f"{cls.RED}⚠ Please enter a number between 1 and {total_items}.{cls.RESET}")
                except ValueError:
                    print(f"{cls.RED}⚠ Invalid input. Enter a number or command ('n', 'p', 'b', 'q').{cls.RESET}")
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

