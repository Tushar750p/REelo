"""Safety interface for automated video moderation.

This intentionally returns a review state rather than pretending a demo
heuristic is production-grade moderation. Plug in a vision/audio model later.
"""
from dataclasses import dataclass

@dataclass
class ModerationResult:
    allowed: bool
    labels: list[str]
    confidence: float
    action: str

def moderate_video(metadata: dict) -> ModerationResult:
    # Safe default: uploads are reviewable until a real multimodal model runs.
    return ModerationResult(True, [], 0.0, 'review')
