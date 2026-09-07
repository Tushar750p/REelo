def suggest_caption(topic: str) -> str:
    topic = topic.strip() or 'your video'
    return f"Sharing {topic} with the REelo community ✨"

def suggest_hashtags(topic: str) -> list[str]:
    words=[w.strip('#').lower() for w in topic.split() if w.strip()]
    return list(dict.fromkeys(['reelo','shortvideo','creator',*words]))[:8]
