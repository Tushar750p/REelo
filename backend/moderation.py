"""Content moderation primitives for REelo.

Dependency-free baseline moderation. This is intentionally conservative: it
flags clearly suspicious text for review rather than pretending automated
checks are perfect.
"""
from __future__ import annotations
import re

_BLOCKED_PATTERNS = [
    r"\b(?:kill|murder)\s+(?:yourself|himself|herself|themself)\b",
    r"\b(?:terrorist|bomb)\b",
]
_SPAM_PATTERNS = [
    r"(?:https?://){2,}",
    r"\b(?:free money|guaranteed profit|click here now)\b",
]


def moderate_text(text: str | None) -> dict:
    value = (text or "").strip()
    normalized = re.sub(r"\s+", " ", value.lower())
    reasons: list[str] = []
    for pattern in _BLOCKED_PATTERNS:
        if re.search(pattern, normalized):
            reasons.append("unsafe_text")
            break
    for pattern in _SPAM_PATTERNS:
        if re.search(pattern, normalized):
            reasons.append("spam_text")
            break
    status = "blocked" if "unsafe_text" in reasons else ("review" if reasons else "clear")
    return {"status": status, "reasons": reasons}
