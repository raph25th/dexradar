from datetime import datetime, timezone
from typing import Any


def _nested(data: dict[str, Any], *keys: str) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _format_money(value: Any) -> str:
    if value is None or value == "":
        return "n/a"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "n/a"
    return f"${number:,.0f}"


def _format_percent(value: Any) -> str:
    if value is None or value == "":
        return "n/a"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "n/a"
    return f"{number:+.2f}%"


def _format_pair_age(pair_created_at: Any) -> str | None:
    if pair_created_at is None or pair_created_at == "":
        return None
    try:
        timestamp = int(float(pair_created_at))
    except (TypeError, ValueError):
        return None

    if timestamp > 10_000_000_000:
        timestamp = timestamp // 1000

    created_at = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    delta = datetime.now(timezone.utc) - created_at
    if delta.total_seconds() < 0:
        return None

    days = delta.days
    hours = int(delta.seconds // 3600)
    if days > 0:
        return f"{days}d {hours}h"
    minutes = int(delta.seconds // 60)
    if hours > 0:
        return f"{hours}h {minutes % 60}m"
    return f"{minutes}m"


def render_alert_message(
    pair: dict[str, Any],
    score: int,
    level: str,
    reasons: list[str],
) -> str:
    base_symbol = _nested(pair, "baseToken", "symbol") or "UNKNOWN"
    quote_symbol = _nested(pair, "quoteToken", "symbol") or "UNKNOWN"
    txns_1h_buys = int(_nested(pair, "txns", "h1", "buys") or 0)
    txns_1h_sells = int(_nested(pair, "txns", "h1", "sells") or 0)
    pair_age = _format_pair_age(pair.get("pairCreatedAt"))
    link = pair.get("url") or "n/a"

    lines = [
        f"DEX Radar alert: {base_symbol} / {quote_symbol}",
        f"Score: {score}/100",
        f"Level: {level}",
        "",
        f"Liquidity: {_format_money(_nested(pair, 'liquidity', 'usd'))}",
        f"Volume 1h: {_format_money(_nested(pair, 'volume', 'h1'))}",
        f"FDV: {_format_money(pair.get('fdv'))}",
        f"Txns 1h: {txns_1h_buys + txns_1h_sells} ({txns_1h_buys} buys / {txns_1h_sells} sells)",
        (
            "Price change: "
            f"1h {_format_percent(_nested(pair, 'priceChange', 'h1'))} / "
            f"6h {_format_percent(_nested(pair, 'priceChange', 'h6'))} / "
            f"24h {_format_percent(_nested(pair, 'priceChange', 'h24'))}"
        ),
    ]

    if pair_age:
        lines.append(f"Pair age: {pair_age}")

    if reasons:
        lines.extend(["", "Reasons:"])
        lines.extend(f"- {reason}" for reason in reasons)

    lines.extend(["", f"DEX Screener: {link}"])
    return "\n".join(lines)
