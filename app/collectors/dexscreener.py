import logging
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

SEARCH_QUERIES = ("WETH", "ETH", "USDC", "PEPE", "AI")
ETHEREUM_CHAIN_ID = "ethereum"
HTTP_TIMEOUT_SECONDS = 20.0


def _as_mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


async def _get_json(path: str, params: dict[str, Any] | None = None) -> Any:
    settings = get_settings()
    url = f"{settings.normalized_dexscreener_base_url}{path}"
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
            response = await client.get(url, params=params)
            if response.status_code >= 400:
                logger.warning(
                    "DEX Screener request failed: status=%s url=%s body=%s",
                    response.status_code,
                    url,
                    response.text[:500],
                )
                return {}
            return response.json()
    except httpx.HTTPError:
        logger.exception("DEX Screener request error: url=%s", url)
    except ValueError:
        logger.exception("DEX Screener returned invalid JSON: url=%s", url)
    return {}


async def search_pairs(query: str) -> list[dict[str, Any]]:
    data = await _get_json("/latest/dex/search", {"q": query})
    pairs = _as_mapping(data).get("pairs", [])
    if not isinstance(pairs, list):
        logger.warning("Unexpected DEX Screener search response shape: query=%s", query)
        return []
    return [pair for pair in pairs if isinstance(pair, dict)]


async def get_token_pairs(chain_id: str, token_address: str) -> list[dict[str, Any]]:
    data = await _get_json(f"/token-pairs/v1/{chain_id}/{token_address}")
    if isinstance(data, list):
        return [pair for pair in data if isinstance(pair, dict)]
    logger.warning(
        "Unexpected DEX Screener token pairs response shape: chain=%s token=%s",
        chain_id,
        token_address,
    )
    return []


def normalize_pair(raw: dict[str, Any]) -> dict[str, Any]:
    base_token = _as_mapping(raw.get("baseToken"))
    quote_token = _as_mapping(raw.get("quoteToken"))
    liquidity = _as_mapping(raw.get("liquidity"))
    volume = _as_mapping(raw.get("volume"))
    txns = _as_mapping(raw.get("txns"))
    price_change = _as_mapping(raw.get("priceChange"))

    normalized_txns: dict[str, dict[str, int]] = {}
    for period in ("m5", "h1", "h6", "h24"):
        period_txns = _as_mapping(txns.get(period))
        normalized_txns[period] = {
            "buys": _to_int(period_txns.get("buys")) or 0,
            "sells": _to_int(period_txns.get("sells")) or 0,
        }

    return {
        "chainId": raw.get("chainId"),
        "dexId": raw.get("dexId"),
        "pairAddress": raw.get("pairAddress"),
        "url": raw.get("url"),
        "baseToken": {
            "address": base_token.get("address"),
            "symbol": base_token.get("symbol"),
            "name": base_token.get("name"),
        },
        "quoteToken": {
            "address": quote_token.get("address"),
            "symbol": quote_token.get("symbol"),
            "name": quote_token.get("name"),
        },
        "priceUsd": _to_float(raw.get("priceUsd")),
        "liquidity": {
            "usd": _to_float(liquidity.get("usd")),
        },
        "fdv": _to_float(raw.get("fdv")),
        "marketCap": _to_float(raw.get("marketCap")),
        "volume": {
            "m5": _to_float(volume.get("m5")),
            "h1": _to_float(volume.get("h1")),
            "h6": _to_float(volume.get("h6")),
            "h24": _to_float(volume.get("h24")),
        },
        "txns": normalized_txns,
        "priceChange": {
            "m5": _to_float(price_change.get("m5")),
            "h1": _to_float(price_change.get("h1")),
            "h6": _to_float(price_change.get("h6")),
            "h24": _to_float(price_change.get("h24")),
        },
        "pairCreatedAt": _to_int(raw.get("pairCreatedAt")),
        "raw": raw,
    }


async def fetch_candidate_pairs() -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for query in SEARCH_QUERIES:
        raw_pairs = await search_pairs(query)
        logger.info("Fetched DEX Screener pairs: query=%s count=%s", query, len(raw_pairs))

        for raw_pair in raw_pairs:
            try:
                pair = normalize_pair(raw_pair)
                if pair.get("chainId") != ETHEREUM_CHAIN_ID:
                    continue

                pair_address = pair.get("pairAddress")
                if not pair_address:
                    logger.debug("Skipping pair without pairAddress: query=%s", query)
                    continue

                dedupe_key = (ETHEREUM_CHAIN_ID, str(pair_address).lower())
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                candidates.append(pair)
            except Exception:
                logger.exception("Failed to normalize DEX Screener pair: query=%s", query)

    logger.info("Collected candidate Ethereum pairs: count=%s", len(candidates))
    return candidates
