"""
Video Data Model
"""
from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass
class Video:
    """Represents a video item found in search results."""
    id: str
    title: str
    page_url: str
    embed_url: Optional[str] = None
    stream_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    duration: Optional[str] = None
    provider: str = "egy-stream"
    rating: Optional[float] = None
    year: Optional[str] = None
    overview: Optional[str] = None
    selected_resolution: Optional[Dict[str, Any]] = None
    selected_vid: Optional[int] = None

    def __str__(self) -> str:
        tag = f"[{self.provider}] " if self.provider else ""
        return f"{tag}{self.title} [ID: {self.id}]"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "page_url": self.page_url,
            "embed_url": self.embed_url,
            "stream_url": self.stream_url,
            "thumbnail_url": self.thumbnail_url,
            "duration": self.duration,
            "provider": self.provider,
            "rating": self.rating,
            "year": self.year,
            "overview": self.overview,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Video":
        return cls(
            id=data["id"],
            title=data["title"],
            page_url=data["page_url"],
            embed_url=data.get("embed_url"),
            stream_url=data.get("stream_url"),
            thumbnail_url=data.get("thumbnail_url"),
            duration=data.get("duration"),
            provider=data.get("provider", "egy-stream"),
            rating=data.get("rating"),
            year=data.get("year"),
            overview=data.get("overview"),
        )
