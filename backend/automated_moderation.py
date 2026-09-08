"""Lightweight automated moderation signals for REelo.

This module deliberately returns review signals rather than pretending that a
keyword detector is a complete safety classifier. It can be replaced by a
trained provider later without changing API contracts.
"""
from __future__ import annotations
import re
from dataclasses import dataclass

URL_RE = re.compile(r"https?://\S+|www\.\S+", re.I)
SPAM_RE = re.compile(r"(?:free|giveaway|promo|click here|dm me|whatsapp|telegram)\b", re.I)
ABUSE_RE = re.compile(r"\b(?:kill yourself|kys|go die|rape|terrorist)\b", re.I)
REPEATED_RE = re.compile(r"(.)\1{7,}")

@dataclass(frozen=True)
class ModerationResult:
    action: str
    score: float
    labels: tuple[str, ...]
    reasons: tuple[str, ...]


def moderate_text(text: str) -> ModerationResult:
    value = (text or "").strip()
    labels: list[str] = []
    reasons: list[str] = []
    score = 0.0
    if URL_RE.search(value):
        labels.append("external_link"); reasons.append("contains external link"); score += 0.15
    if SPAM_RE.search(value):
        labels.append("spam_signal"); reasons.append("contains promotional/spam language"); score += 0.35
    if ABUSE_RE.search(value):
        labels.append("abusive_language"); reasons.append("contains abusive language"); score += 0.65
    if REPEATED_RE.search(value):
        labels.append("repetition"); reasons.append("contains excessive repeated characters"); score += 0.15
    score = min(1.0, score)
    action = "allow"
    if score >= 0.75: action = "review"
    elif score >= 0.45: action = "limit"
    return ModerationResult(action, round(score, 3), tuple(labels), tuple(reasons))


def abuse_velocity(events: list[float], now: float, window_seconds: int = 60, limit: int = 20) -> bool:
    recent = [x for x in events if 0 <= now - x <= window_seconds]
    return len(recent) >= limit
