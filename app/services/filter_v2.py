from decimal import Decimal
from typing import Any

CRITICAL_AVOID_REASONS = {
    "liquidity_below_20k",
    "fdv_missing",
    "fdv_above_150m",
    "buy_ratio_too_high",
    "negative_momentum",
    "overheated_1h",
    "overheated_24h",
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


def _read_metric(data: dict[str, Any] | Any, dict_path: tuple[str, ...], attr_name: str) -> float | None:
    if isinstance(data, dict):
        return _to_float(_nested_value(data, *dict_path))
    return _to_float(getattr(data, attr_name, None))


def safe_div(numerator: Any, denominator: Any) -> float | None:
    numerator_value = _to_float(numerator)
    denominator_value = _to_float(denominator)
    if numerator_value is None or denominator_value is None or denominator_value == 0:
        return None
    return numerator_value / denominator_value


def calculate_txns_1h_total(buys: Any, sells: Any) -> int:
    buys_value = _to_float(buys) or 0.0
    sells_value = _to_float(sells) or 0.0
    return int(buys_value + sells_value)


def calculate_buy_ratio(buys: Any, sells: Any) -> float | None:
    total = calculate_txns_1h_total(buys, sells)
    return safe_div(buys, total)


def calculate_volume_liquidity_ratio_1h(volume_1h: Any, liquidity_usd: Any) -> float | None:
    return safe_div(volume_1h, liquidity_usd)


def calculate_fdv_volume_ratio_1h(fdv: Any, volume_1h: Any) -> float | None:
    return safe_div(fdv, volume_1h)


def calculate_liquidity_fdv_ratio(liquidity_usd: Any, fdv: Any) -> float | None:
    return safe_div(liquidity_usd, fdv)


def build_filter_v2_metrics(data: dict[str, Any] | Any) -> dict[str, float | int | None]:
    liquidity_usd = _read_metric(data, ("liquidity", "usd"), "liquidity_usd")
    volume_1h = _read_metric(data, ("volume", "h1"), "volume_1h")
    volume_24h = _read_metric(data, ("volume", "h24"), "volume_24h")
    fdv = _read_metric(data, ("fdv",), "fdv")
    market_cap = _read_metric(data, ("marketCap",), "market_cap")
    price_change_1h = _read_metric(data, ("priceChange", "h1"), "price_change_1h")
    price_change_6h = _read_metric(data, ("priceChange", "h6"), "price_change_6h")
    price_change_24h = _read_metric(data, ("priceChange", "h24"), "price_change_24h")

    if isinstance(data, dict):
        buys_1h = _to_float(_nested_value(data, "txns", "h1", "buys")) or 0.0
        sells_1h = _to_float(_nested_value(data, "txns", "h1", "sells")) or 0.0
    else:
        buys_1h = _to_float(getattr(data, "txns_1h_buys", None)) or 0.0
        sells_1h = _to_float(getattr(data, "txns_1h_sells", None)) or 0.0

    txns_1h_total = calculate_txns_1h_total(buys_1h, sells_1h)
    buy_ratio = calculate_buy_ratio(buys_1h, sells_1h)
    volume_liquidity_ratio_1h = calculate_volume_liquidity_ratio_1h(volume_1h, liquidity_usd)
    fdv_volume_ratio_1h = calculate_fdv_volume_ratio_1h(fdv, volume_1h)
    liquidity_fdv_ratio = calculate_liquidity_fdv_ratio(liquidity_usd, fdv)

    return {
        "liquidity_usd": liquidity_usd,
        "volume_1h": volume_1h,
        "volume_24h": volume_24h,
        "fdv": fdv,
        "market_cap": market_cap,
        "txns_1h_buys": buys_1h,
        "txns_1h_sells": sells_1h,
        "txns_1h_total": txns_1h_total,
        "buy_ratio": buy_ratio,
        "volume_liquidity_ratio_1h": volume_liquidity_ratio_1h,
        "fdv_volume_ratio_1h": fdv_volume_ratio_1h,
        "liquidity_fdv_ratio": liquidity_fdv_ratio,
        "price_change_1h": price_change_1h,
        "price_change_6h": price_change_6h,
        "price_change_24h": price_change_24h,
    }


def _profile_result(passed: bool, reasons: list[str]) -> dict[str, Any]:
    return {
        "passed": passed,
        "reasons": reasons,
    }


def _metric_value(metrics: dict[str, Any], key: str) -> float | int | None:
    return metrics.get(key)


def _missing_momentum(metrics: dict[str, Any]) -> bool:
    return metrics.get("price_change_1h") is None and metrics.get("price_change_6h") is None


def evaluate_early_watch_v2(metrics: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []

    if (_metric_value(metrics, "liquidity_usd") or 0) < 20_000:
        reasons.append("liquidity_below_20k")
    if (_metric_value(metrics, "volume_1h") or 0) < 5_000:
        reasons.append("volume_1h_below_5k")
    if (_metric_value(metrics, "txns_1h_total") or 0) < 10:
        reasons.append("txns_1h_below_10")

    fdv = _metric_value(metrics, "fdv")
    if fdv is None:
        reasons.append("fdv_missing")
    elif fdv > 150_000_000:
        reasons.append("fdv_above_150m")

    volume_liquidity_ratio = _metric_value(metrics, "volume_liquidity_ratio_1h")
    if volume_liquidity_ratio is None or volume_liquidity_ratio < 0.05:
        reasons.append("volume_liquidity_ratio_too_low")

    buy_ratio = _metric_value(metrics, "buy_ratio")
    if buy_ratio is None or buy_ratio < 0.40:
        reasons.append("buy_ratio_too_low")

    price_change_1h = _metric_value(metrics, "price_change_1h")
    price_change_6h = _metric_value(metrics, "price_change_6h")
    if _missing_momentum(metrics):
        reasons.append("momentum_data_missing")
    elif not (
        (price_change_1h is not None and price_change_1h > -10)
        or (price_change_6h is not None and price_change_6h > -15)
    ):
        reasons.append("negative_momentum")

    blocking_reasons = [reason for reason in reasons if reason != "momentum_data_missing"]
    return _profile_result(not blocking_reasons, reasons)


def evaluate_watch_v2(metrics: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []

    if (_metric_value(metrics, "liquidity_usd") or 0) < 75_000:
        reasons.append("liquidity_below_75k")
    if (_metric_value(metrics, "volume_1h") or 0) < 25_000:
        reasons.append("volume_1h_below_25k")
    if (_metric_value(metrics, "txns_1h_total") or 0) < 30:
        reasons.append("txns_1h_below_30")

    fdv = _metric_value(metrics, "fdv")
    if fdv is None:
        reasons.append("fdv_missing")
    elif fdv > 100_000_000:
        reasons.append("fdv_above_100m")

    volume_liquidity_ratio = _metric_value(metrics, "volume_liquidity_ratio_1h")
    if volume_liquidity_ratio is None or volume_liquidity_ratio < 0.10:
        reasons.append("volume_liquidity_ratio_too_low")

    fdv_volume_ratio = _metric_value(metrics, "fdv_volume_ratio_1h")
    if fdv_volume_ratio is None or fdv_volume_ratio > 1_000:
        reasons.append("fdv_volume_ratio_too_high")

    buy_ratio = _metric_value(metrics, "buy_ratio")
    if buy_ratio is None or buy_ratio < 0.45:
        reasons.append("buy_ratio_too_low")
    elif buy_ratio > 0.85:
        reasons.append("buy_ratio_too_high")

    price_change_1h = _metric_value(metrics, "price_change_1h")
    price_change_6h = _metric_value(metrics, "price_change_6h")
    if _missing_momentum(metrics):
        reasons.append("momentum_data_missing")
    else:
        if price_change_1h is not None and price_change_1h <= -5:
            reasons.append("negative_momentum_1h")
        if price_change_6h is not None and price_change_6h <= -10:
            reasons.append("negative_momentum_6h")

    blocking_reasons = [reason for reason in reasons if reason != "momentum_data_missing"]
    return _profile_result(not blocking_reasons, reasons)


def evaluate_high_signal_v2(metrics: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []

    if (_metric_value(metrics, "liquidity_usd") or 0) < 150_000:
        reasons.append("liquidity_below_150k")
    if (_metric_value(metrics, "volume_1h") or 0) < 75_000:
        reasons.append("volume_1h_below_75k")
    if (_metric_value(metrics, "txns_1h_total") or 0) < 75:
        reasons.append("txns_1h_below_75")

    fdv = _metric_value(metrics, "fdv")
    if fdv is None:
        reasons.append("fdv_missing")
    elif fdv > 75_000_000:
        reasons.append("fdv_above_75m")

    volume_liquidity_ratio = _metric_value(metrics, "volume_liquidity_ratio_1h")
    if volume_liquidity_ratio is None or volume_liquidity_ratio < 0.15:
        reasons.append("volume_liquidity_ratio_too_low")

    fdv_volume_ratio = _metric_value(metrics, "fdv_volume_ratio_1h")
    if fdv_volume_ratio is None or fdv_volume_ratio > 500:
        reasons.append("fdv_volume_ratio_too_high")

    buy_ratio = _metric_value(metrics, "buy_ratio")
    if buy_ratio is None or buy_ratio < 0.50:
        reasons.append("buy_ratio_too_low")
    elif buy_ratio > 0.85:
        reasons.append("buy_ratio_too_high")

    price_change_1h = _metric_value(metrics, "price_change_1h")
    price_change_6h = _metric_value(metrics, "price_change_6h")
    price_change_24h = _metric_value(metrics, "price_change_24h")
    if _missing_momentum(metrics):
        reasons.append("momentum_data_missing")
    elif not (
        (price_change_1h is not None and price_change_1h >= 3)
        or (price_change_6h is not None and price_change_6h >= 8)
    ):
        reasons.append("momentum_below_threshold")

    if price_change_1h is not None and price_change_1h > 80:
        reasons.append("overheated_1h")
    if price_change_24h is not None and price_change_24h > 300:
        reasons.append("overheated_24h")

    blocking_reasons = [reason for reason in reasons if reason != "momentum_data_missing"]
    return _profile_result(not blocking_reasons, reasons)


def evaluate_avoid_reasons_v2(metrics: dict[str, Any]) -> list[str]:
    reasons: list[str] = []

    if (_metric_value(metrics, "liquidity_usd") or 0) < 20_000:
        reasons.append("liquidity_below_20k")
    if (_metric_value(metrics, "volume_1h") or 0) < 5_000:
        reasons.append("volume_1h_below_5k")
    if (_metric_value(metrics, "txns_1h_total") or 0) < 10:
        reasons.append("txns_1h_below_10")

    fdv = _metric_value(metrics, "fdv")
    if fdv is None:
        reasons.append("fdv_missing")
    elif fdv > 150_000_000:
        reasons.append("fdv_above_150m")

    volume_liquidity_ratio = _metric_value(metrics, "volume_liquidity_ratio_1h")
    if volume_liquidity_ratio is None or volume_liquidity_ratio < 0.05:
        reasons.append("volume_liquidity_ratio_too_low")
    elif volume_liquidity_ratio > 5:
        reasons.append("volume_liquidity_ratio_too_high")

    fdv_volume_ratio = _metric_value(metrics, "fdv_volume_ratio_1h")
    if fdv_volume_ratio is not None and fdv_volume_ratio > 2_000:
        reasons.append("fdv_volume_ratio_too_high")

    buy_ratio = _metric_value(metrics, "buy_ratio")
    if buy_ratio is None or buy_ratio < 0.35:
        reasons.append("buy_ratio_too_low")
    elif buy_ratio > 0.95:
        reasons.append("buy_ratio_too_high")

    price_change_1h = _metric_value(metrics, "price_change_1h")
    price_change_6h = _metric_value(metrics, "price_change_6h")
    price_change_24h = _metric_value(metrics, "price_change_24h")
    if (
        (price_change_1h is not None and price_change_1h < -15)
        or (price_change_6h is not None and price_change_6h < -25)
    ):
        reasons.append("negative_momentum")
    if price_change_1h is not None and price_change_1h > 100:
        reasons.append("overheated_1h")
    if price_change_24h is not None and price_change_24h > 400:
        reasons.append("overheated_24h")

    return reasons


def evaluate_filter_v2(metrics: dict[str, Any]) -> dict[str, Any]:
    early_watch = evaluate_early_watch_v2(metrics)
    watch = evaluate_watch_v2(metrics)
    high_signal = evaluate_high_signal_v2(metrics)
    avoid_reasons = evaluate_avoid_reasons_v2(metrics)
    critical_avoid_reasons = [
        reason for reason in avoid_reasons if reason in CRITICAL_AVOID_REASONS
    ]

    passed_profiles: list[str] = []
    if early_watch["passed"]:
        passed_profiles.append("early_watch")
    if watch["passed"]:
        passed_profiles.append("watch")
    if high_signal["passed"]:
        passed_profiles.append("high_signal")

    if high_signal["passed"] and not critical_avoid_reasons:
        status = "high_signal"
    elif watch["passed"] and not critical_avoid_reasons:
        status = "watch"
    elif early_watch["passed"] and not critical_avoid_reasons:
        status = "early_watch"
    elif critical_avoid_reasons:
        status = "avoid"
    else:
        status = "rejected"

    reasons: list[str] = []
    if passed_profiles:
        reasons.extend(f"passed_{profile}" for profile in passed_profiles)
    else:
        reasons.extend(avoid_reasons[:6])

    for profile_result in (early_watch, watch, high_signal):
        if "momentum_data_missing" in profile_result["reasons"] and "momentum_data_missing" not in reasons:
            reasons.append("momentum_data_missing")

    return {
        "status": status,
        "passed_profiles": passed_profiles,
        "reasons": reasons,
        "avoid_reasons": avoid_reasons,
        "metrics": metrics,
    }
