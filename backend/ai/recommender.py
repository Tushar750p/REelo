"""REelo recommendation foundation.

Uses transparent weighted ranking now; replace rank() with a trained model later.
"""
from dataclasses import dataclass

@dataclass
class UserSignals:
    watched: set[str]
    liked: set[str]
    followed_creators: set[str]
    preferred_tags: set[str]

def rank(videos: list[dict], signals: UserSignals) -> list[dict]:
    scored=[]
    for v in videos:
        score=0.0
        if v.get('id') in signals.watched: score -= 3
        if v.get('creator') in signals.followed_creators: score += 5
        score += 2 * len(set(v.get('tags', [])) & signals.preferred_tags)
        score += min(v.get('likes',0)/10000, 3)
        score += min(v.get('comments',0)/1000, 2)
        item={**v,'recommendation_score':round(score,3)}
        scored.append(item)
    return sorted(scored,key=lambda x:x['recommendation_score'],reverse=True)
