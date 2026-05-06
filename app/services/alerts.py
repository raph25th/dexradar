def should_alert(score: int) -> str | None:
    if score >= 75:
        return "high"
    if score >= 60:
        return "watch"
    return None
