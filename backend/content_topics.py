"""Dependency-free topic/hashtag inference for REelo videos.

This intentionally avoids external ML dependencies. It provides stable topic
signals that can later be replaced by an embedding/classification service.
"""
from __future__ import annotations
import re

TOPIC_KEYWORDS = {
    "technology": {"ai", "artificial", "intelligence", "tech", "technology", "coding", "code", "python", "software", "developer", "programming", "computer"},
    "education": {"learn", "learning", "study", "education", "tutorial", "course", "exam", "student", "school", "college", "knowledge"},
    "business": {"business", "startup", "entrepreneur", "money", "finance", "marketing", "sales", "investment", "career", "job"},
    "fitness": {"fitness", "gym", "workout", "exercise", "health", "running", "training", "muscle", "yoga"},
    "food": {"food", "recipe", "cooking", "cook", "kitchen", "restaurant", "pizza", "cake", "breakfast", "lunch", "dinner"},
    "travel": {"travel", "trip", "tour", "vacation", "holiday", "hotel", "flight", "beach", "mountain", "city"},
    "gaming": {"game", "gaming", "gamer", "playstation", "xbox", "steam", "esports", "minecraft", "fortnite"},
    "music": {"music", "song", "singing", "singer", "guitar", "piano", "dance", "dj", "concert"},
    "comedy": {"comedy", "funny", "joke", "meme", "laugh", "prank", "humor"},
    "sports": {"sport", "sports", "cricket", "football", "soccer", "basketball", "tennis", "match", "player"},
}


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def infer_topics(*texts: str, hashtags: list[str] | None = None, limit: int = 3) -> list[str]:
    tokens = _tokens(" ".join(texts))
    tags = _tokens(" ".join(hashtags or []))
    counts = {topic: 0 for topic in TOPIC_KEYWORDS}
    for topic, words in TOPIC_KEYWORDS.items():
        counts[topic] = sum(tokens.count(word) for word in words) + 2 * sum(tag in words for tag in tags)
    ranked = sorted(counts.items(), key=lambda x: (-x[1], x[0]))
    return [topic for topic, score in ranked[:limit] if score > 0]
