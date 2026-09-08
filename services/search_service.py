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

from config import SEARCH_URL, DEFAULT_HEADERS, DEFAULT_TIMEOUT, SEARCH_RESULTS_FILE
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

        # Combine results
        combined_videos = cinejoy_videos + egystream_videos

        if self.logger:
            self.logger.info(
                f"Search results: {len(cinejoy_videos)} [cineby], "
                f"{len(egystream_videos)} [egy-stream] (Total: {len(combined_videos)})"
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

    def _save_results(self, videos: List[Video]):
        """Persists search results to JSON."""
        try:
            data = [v.to_dict() for v in videos]
            with open(SEARCH_RESULTS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except IOError:
            pass
