import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)

ALERT_COOLDOWN_HOURS = 6
ALERT_LEVEL_PRIORITY = {
    "early_watch": 0,
    "watch": 1,
    "high": 2,
}


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _nested_value(data: dict[str, Any], *keys: str) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _metric(data: dict[str, Any] | Any, dict_path: tuple[str, ...], attr_name: str) -> float | None:
    if isinstance(data, dict):
        return _to_float(_nested_value(data, *dict_path))
    return _to_float(getattr(data, attr_name, None))


def _txns_1h_values(data: dict[str, Any] | Any) -> tuple[float, float]:
    if isinstance(data, dict):
        buys = _to_float(_nested_value(data, "txns", "h1", "buys")) or 0.0
        sells = _to_float(_nested_value(data, "txns", "h1", "sells")) or 0.0
        return buys, sells
    buys = _to_float(getattr(data, "txns_1h_buys", None)) or 0.0
    sells = _to_float(getattr(data, "txns_1h_sells", None)) or 0.0
    return buys, sells


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def should_alert(score: int) -> str | None:
    if score >= 75:
        return "high"
    if score >= 60:
        return "watch"
    return None


def passes_alert_quality_gate(data: dict[str, Any] | Any) -> tuple[bool, list[str]]:
    reasons: list[str] = []

    liquidity_usd = _metric(data, ("liquidity", "usd"), "liquidity_usd") or 0.0
    volume_1h = _metric(data, ("volume", "h1"), "volume_1h") or 0.0
    fdv = _metric(data, ("fdv",), "fdv")
    buys_1h, sells_1h = _txns_1h_values(data)
    txns_1h_total = buys_1h + sells_1h

    if liquidity_usd < 100_000:
        reasons.append("alert_liquidity_below_threshold")
    if volume_1h < 50_000:
        reasons.append("alert_volume_1h_below_threshold")
    if txns_1h_total < 50:
        reasons.append("alert_txns_1h_below_threshold")
    if fdv is None:
        reasons.append("alert_fdv_missing")
    elif fdv > 100_000_000:
        reasons.append("alert_fdv_above_threshold")

    buy_ratio = buys_1h / txns_1h_total if txns_1h_total > 0 else 0.0
    if buy_ratio < 0.45:
        reasons.append("alert_buy_ratio_too_low")

    price_change_1h = _metric(data, ("priceChange", "h1"), "price_change_1h")
    price_change_6h = _metric(data, ("priceChange", "h6"), "price_change_6h")
    if price_change_1h is None and price_change_6h is None:
        logger.info("Alert quality gate momentum data is missing; momentum check is not blocking")
    elif not (
        (price_change_1h is not None and price_change_1h >= 0)
        or (price_change_6h is not None and price_change_6h >= 3)
    ):
        reasons.append("alert_negative_momentum")

    return not reasons, reasons


def is_alert_level_upgrade(previous_level: str | None, current_level: str) -> bool:
    return ALERT_LEVEL_PRIORITY.get(current_level, -1) > ALERT_LEVEL_PRIORITY.get(
        previous_level or "",
        -1,
    )


def can_create_alert_after_cooldown(
    last_alert_created_at: datetime | None,
    last_alert_level: str | None,
    current_level: str,
    now: datetime | None = None,
) -> tuple[bool, str]:
    if last_alert_created_at is None:
        return True, "no_previous_alert"

    if is_alert_level_upgrade(last_alert_level, current_level):
        return True, "level_upgrade"

    current_time = now or datetime.now(timezone.utc)
    current_time = _ensure_aware(current_time)
    last_alert_created_at = _ensure_aware(last_alert_created_at)
    cooldown_cutoff = current_time - timedelta(hours=ALERT_COOLDOWN_HOURS)
    if last_alert_created_at <= cooldown_cutoff:
        return True, "cooldown_expired"

    return False, "cooldown_active"
