"""
Search Service - Multi-Provider Aggregator
==========================================
Searches across both providers:
1. Cinejoy / Cineby (via TMDB API for international movies & ratings)
2. EGY-Stream (via Ahwak for Arabic content & dubbed/subbed movies)
"""
import json
import urllib.parse
import re
from typing import List
import requests
from bs4 import BeautifulSoup

from config import (
    SEARCH_URL, DEFAULT_HEADERS, DEFAULT_TIMEOUT, SEARCH_RESULTS_FILE,
    WITANIME_BASE_URL, WITANIME_SEARCH_URL
)
from models.video import Video

TMDB_API_KEY = "8476a7ab80ad76f0936744df0430e67c"
TMDB_SEARCH_URL = "https://api.themoviedb.org/3/search/movie"
CINEJOY_MOVIE_BASE = "https://cinejoy.to/watch/movie"


class SearchService:
    """Handles multi-provider searching across Cinejoy/Cineby and EGY-Stream."""

    def __init__(self, logger=None):
        self.logger = logger
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def search(self, query: str) -> List[Video]:
        """Queries both providers and returns an aggregated, indexed list of Video objects."""
        if self.logger:
            self.logger.info(f"Multi-provider search for: '{query}'")

        cleaned_query = query.strip()
        if not cleaned_query:
            return []

        # 1. Search Cineby / Cinejoy via TMDB
        cinejoy_videos = self._search_cinejoy(cleaned_query)

        # 2. Search EGY-Stream / Ahwak
        egystream_videos = self._search_egystream(cleaned_query)

        # 3. Search WitAnime (pure requests)
        witanime_videos = self._search_witanime(cleaned_query)

        # Combine results
        combined_videos = cinejoy_videos + egystream_videos + witanime_videos

        # Sort: shortest title first, maintaining stable provider relevance order
        combined_videos.sort(key=lambda v: len(v.title.strip()))

        if self.logger:
            self.logger.info(
                f"Search results: {len(cinejoy_videos)} [cineby], "
                f"{len(egystream_videos)} [egy-stream], "
                f"{len(witanime_videos)} [witanime] (Total: {len(combined_videos)})"
            )

        # Save results to output file
        self._save_results(combined_videos)

        return combined_videos

    def _search_cinejoy(self, query: str, limit: int = 8) -> List[Video]:
        """Searches movies on TMDB for Cineby/Cinejoy streaming."""
        params = {
            "api_key": TMDB_API_KEY,
            "query": query,
            "include_adult": "false",
            "language": "en-US",
        }
        videos = []
        try:
            resp = self.session.get(TMDB_SEARCH_URL, params=params, timeout=DEFAULT_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", [])
                for item in results[:limit]:
                    tmdb_id = str(item.get("id"))
                    title = item.get("title", "Unknown")
                    release_date = item.get("release_date", "")
                    year = release_date[:4] if release_date else ""
                    vote = item.get("vote_average", 0.0)
                    rating = round(vote, 1) if vote else None
                    overview = item.get("overview", "")

                    videos.append(
                        Video(
                            id=tmdb_id,
                            title=title,
                            page_url=f"{CINEJOY_MOVIE_BASE}/{tmdb_id}",
                            embed_url="https://cinejoy.to/",
                            provider="cineby",
                            year=year,
                            rating=rating,
                            overview=overview
                        )
                    )
        except Exception as e:
            if self.logger:
                self.logger.error(f"Cineby/TMDB search error: {e}")

        return videos

    def _search_egystream(self, query: str) -> List[Video]:
        """Searches the Arabic provider (Ahwak / EGY-Stream)."""
        encoded = urllib.parse.quote(query)
        url = f"{SEARCH_URL}?keywords={encoded}"

        try:
            response = self.session.get(url, timeout=DEFAULT_TIMEOUT)
            if response.status_code == 200:
                return self._parse_egystream_html(response.text)
        except requests.RequestException as e:
            if self.logger:
                self.logger.error(f"EGY-Stream search request failed: {e}")

        return []

    def _parse_egystream_html(self, html: str) -> List[Video]:
        """Parses video items from EGY-Stream HTML page."""
        videos = []
        seen_ids = set()

        pattern = r'<a[^>]+href=["\']([^"\']*(?:see\.php|watch\.php)\?vid=([a-zA-Z0-9]+)[^"\']*)[^>]*>(.*?)</a>'
        matches = re.findall(pattern, html, re.DOTALL | re.IGNORECASE)

        for match in matches:
            page_url, vid, raw_title = match
            clean_title = re.sub(r'<[^>]+>', '', raw_title).strip()

            if not clean_title or vid in seen_ids:
                continue

            if len(clean_title) < 3 or clean_title.lower() in ["مشاهدة", "تحميل", "play", "see"]:
                continue

            seen_ids.add(vid)
            page_url = f"https://yam.ahwaktv.net/see.php?vid={vid}"

            videos.append(
                Video(
                    id=vid,
                    title=clean_title,
                    page_url=page_url,
                    provider="egy-stream"
                )
            )

        return videos

    def _search_witanime(self, query: str, limit: int = 8) -> List[Video]:
        """Searches anime on WitAnime (witanime.you) via pure requests."""
        videos = []
        headers = dict(DEFAULT_HEADERS)
        headers["Referer"] = f"{WITANIME_BASE_URL}/"

        try:
            # 1. Search for anime series
            params = {"search_param": "animes", "s": query}
            resp = self.session.get(f"{WITANIME_BASE_URL}/", params=params, headers=headers, timeout=DEFAULT_TIMEOUT)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                seen_urls = set()

                for a in soup.find_all("a", href=re.compile(r"/anime/[^/]+/?$")):
                    url = a.get("href", "").strip()
                    title = a.get_text(strip=True)
                    if not url or url in seen_urls or not title or len(title) < 2:
                        continue
                    if any(skip in title.lower() for skip in ["قائمة الانمي", "anime-type", "anime-genre"]):
                        continue

                    seen_urls.add(url)
                    slug = url.rstrip("/").split("/")[-1]

                    parent_card = a.find_parent(class_=re.compile(r"anime-card|col-md-3|item"))
                    thumb = None
                    if parent_card:
                        img = parent_card.find("img")
                        if img:
                            thumb = img.get("src") or img.get("data-src")

                    videos.append(
                        Video(
                            id=slug,
                            title=title,
                            page_url=url,
                            thumbnail_url=thumb,
                            provider="witanime"
                        )
                    )
                    if len(videos) >= limit:
                        break

            # 2. If no series found, fallback to searching individual episodes
            if not videos:
                params_ep = {"search_param": "episodes", "s": query}
                resp_ep = self.session.get(f"{WITANIME_BASE_URL}/", params=params_ep, headers=headers, timeout=DEFAULT_TIMEOUT)
                if resp_ep.status_code == 200:
                    soup_ep = BeautifulSoup(resp_ep.text, "html.parser")
                    seen_urls = set()
                    for a in soup_ep.find_all("a", href=re.compile(r"/episode/[^/]+/?$")):
                        url = a.get("href", "").strip()
                        title = a.get_text(strip=True)
                        if not url or url in seen_urls or not title or "اقرأ المزيد" in title:
                            continue
                        seen_urls.add(url)
                        slug = url.rstrip("/").split("/")[-1]

                        videos.append(
                            Video(
                                id=slug,
                                title=title,
                                page_url=url,
                                provider="witanime"
                            )
                        )
                        if len(videos) >= limit:
                            break
        except Exception as e:
            if self.logger:
                self.logger.error(f"WitAnime search error: {e}")

        return videos

    def _save_results(self, videos: List[Video]):
        """Persists search results to JSON."""
        try:
            data = [v.to_dict() for v in videos]
            with open(SEARCH_RESULTS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except IOError:
            pass
