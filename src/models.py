"""Data models for content pipeline."""
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Entry:
    """RSS feed entry."""

    guid: str
    title: str
    url: str
    content: str
    author: str | None
    published_at: datetime | None
    feed_id: int
    feed_title: str
    category: str  # articles, youtube, podcasts


@dataclass
class Feed:
    """Feed subscription."""

    id: int
    url: str
    title: str | None
    category: str
    is_active: bool = True
