from typing import Any


def _nested_number(data: dict[str, Any], *keys: str) -> float | None:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    if current is None or current == "":
        return None
    try:
        return float(current)
    except (TypeError, ValueError):
        return None


def calculate_market_score(pair: dict[str, Any]) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []

    liquidity_usd = _nested_number(pair, "liquidity", "usd") or 0.0
    if liquidity_usd >= 100_000:
        score += 10
        reasons.append("Liquidity is at least $100k: +10")
    if liquidity_usd >= 500_000:
        score += 10
        reasons.append("Liquidity is at least $500k: +10")

    volume_1h = _nested_number(pair, "volume", "h1") or 0.0
    if volume_1h >= 50_000:
        score += 10
        reasons.append("1h volume is at least $50k: +10")
    if volume_1h >= 250_000:
        score += 10
        reasons.append("1h volume is at least $250k: +10")

    buys_1h = _nested_number(pair, "txns", "h1", "buys") or 0.0
    sells_1h = _nested_number(pair, "txns", "h1", "sells") or 0.0
    txns_1h = buys_1h + sells_1h
    if txns_1h >= 50:
        score += 10
        reasons.append("1h transactions are at least 50: +10")
    if txns_1h >= 200:
        score += 10
        reasons.append("1h transactions are at least 200: +10")

    price_change_1h = _nested_number(pair, "priceChange", "h1")
    if price_change_1h is not None:
        if 5 <= price_change_1h <= 40:
            score += 10
            reasons.append("1h price change is between 5% and 40%: +10")
        elif 40 < price_change_1h <= 120:
            score += 5
            reasons.append("1h price change is between 40% and 120%: +5")
        elif price_change_1h < -20:
            score -= 10
            reasons.append("1h price change is below -20%: -10")

    fdv = _nested_number(pair, "fdv")
    if fdv is not None:
        if fdv <= 50_000_000:
            score += 10
            reasons.append("FDV is at most $50m: +10")
        if fdv <= 10_000_000:
            score += 10
            reasons.append("FDV is at most $10m: +10")

    if txns_1h > 0:
        buy_ratio = buys_1h / txns_1h
        if 0.45 <= buy_ratio <= 0.85:
            score += 10
            reasons.append("Buy ratio is between 45% and 85%: +10")
        elif buy_ratio > 0.9:
            score -= 10
            reasons.append("Buy ratio is above 90%: -10")

    return max(0, min(100, score)), reasons
