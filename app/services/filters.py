from typing import Any

ETHEREUM_CHAIN_ID = "ethereum"
BASIC_LIQUIDITY_USD_THRESHOLD = 100_000
BASIC_VOLUME_1H_THRESHOLD = 50_000
BASIC_TXNS_1H_THRESHOLD = 50
BASIC_FDV_THRESHOLD = 50_000_000
EARLY_WATCH_LIQUIDITY_USD_THRESHOLD = 20_000
EARLY_WATCH_VOLUME_1H_THRESHOLD = 5_000
EARLY_WATCH_TXNS_1H_THRESHOLD = 10
EARLY_WATCH_FDV_THRESHOLD = 100_000_000


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


def passes_basic_filters(pair: dict[str, Any]) -> bool:
    return not get_filter_rejection_reasons(pair)


def get_filter_rejection_reasons(pair: dict[str, Any]) -> list[str]:
    return _get_rejection_reasons(
        pair,
        liquidity_usd_threshold=BASIC_LIQUIDITY_USD_THRESHOLD,
        volume_1h_threshold=BASIC_VOLUME_1H_THRESHOLD,
        txns_1h_threshold=BASIC_TXNS_1H_THRESHOLD,
        fdv_threshold=BASIC_FDV_THRESHOLD,
    )


def passes_early_watch_filters(pair: dict[str, Any]) -> bool:
    return not get_early_watch_rejection_reasons(pair)


def get_early_watch_rejection_reasons(pair: dict[str, Any]) -> list[str]:
    return _get_rejection_reasons(
        pair,
        liquidity_usd_threshold=EARLY_WATCH_LIQUIDITY_USD_THRESHOLD,
        volume_1h_threshold=EARLY_WATCH_VOLUME_1H_THRESHOLD,
        txns_1h_threshold=EARLY_WATCH_TXNS_1H_THRESHOLD,
        fdv_threshold=EARLY_WATCH_FDV_THRESHOLD,
    )


def _get_rejection_reasons(
    pair: dict[str, Any],
    liquidity_usd_threshold: float,
    volume_1h_threshold: float,
    txns_1h_threshold: float,
    fdv_threshold: float,
) -> list[str]:
    reasons: list[str] = []

    if pair.get("chainId") != ETHEREUM_CHAIN_ID:
        reasons.append("non_ethereum_chain")

    liquidity_usd = _nested_number(pair, "liquidity", "usd") or 0.0
    volume_1h = _nested_number(pair, "volume", "h1") or 0.0
    fdv = _nested_number(pair, "fdv")
    buys_1h = _nested_number(pair, "txns", "h1", "buys") or 0.0
    sells_1h = _nested_number(pair, "txns", "h1", "sells") or 0.0

    if liquidity_usd < liquidity_usd_threshold:
        reasons.append("liquidity_below_threshold")
    if volume_1h < volume_1h_threshold:
        reasons.append("volume_1h_below_threshold")
    if buys_1h + sells_1h < txns_1h_threshold:
        reasons.append("txns_1h_below_threshold")
    if fdv is None:
        reasons.append("fdv_missing")
    elif fdv > fdv_threshold:
        reasons.append("fdv_above_threshold")

    return reasons
