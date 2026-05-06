import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.collectors.dexscreener import fetch_candidate_pairs
from app.db.models import Alert, Pair, PairSnapshot, Token
from app.db.session import SessionLocal
from app.runtime_state import set_last_collection_summary
from app.services.alerts import should_alert
from app.services.filters import (
    get_early_watch_rejection_reasons,
    get_filter_rejection_reasons,
    passes_basic_filters,
)
from app.services.scoring import calculate_market_score
from app.telegram.bot import send_telegram_message
from app.telegram.templates import render_alert_message

logger = logging.getLogger(__name__)

_collection_lock = asyncio.Lock()


def _summary() -> dict[str, int]:
    return {
        "fetched": 0,
        "snapshots_created": 0,
        "early_watch_passed": 0,
        "passed_filters": 0,
        "scored": 0,
        "alerts_created": 0,
        "telegram_sent": 0,
    }


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _to_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _to_int(value: Any) -> int:
    if value is None or value == "":
        return 0
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _parse_pair_created_at(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    try:
        timestamp = int(float(value))
    except (TypeError, ValueError):
        return None

    if timestamp > 10_000_000_000:
        timestamp = timestamp // 1000
    return datetime.fromtimestamp(timestamp, tz=timezone.utc)


def _normalize_address(value: Any) -> str | None:
    if not value:
        return None
    return str(value).lower()


def _upsert_token(session: Session, pair: dict[str, Any]) -> Token:
    base_token = _as_dict(pair.get("baseToken"))
    chain_id = pair.get("chainId")
    address = _normalize_address(base_token.get("address"))
    if not chain_id or not address:
        raise ValueError("Pair has no base token chain or address")

    token = session.scalar(
        select(Token).where(Token.chain_id == str(chain_id), Token.address == address)
    )
    if token is None:
        token = Token(
            chain_id=str(chain_id),
            address=address,
            symbol=base_token.get("symbol"),
            name=base_token.get("name"),
        )
        session.add(token)
        session.flush()
        return token

    token.symbol = base_token.get("symbol") or token.symbol
    token.name = base_token.get("name") or token.name
    return token


def _upsert_pair(session: Session, pair: dict[str, Any], token: Token) -> Pair:
    chain_id = pair.get("chainId")
    pair_address = _normalize_address(pair.get("pairAddress"))
    if not chain_id or not pair_address:
        raise ValueError("Pair has no chain or pair address")

    quote_token = _as_dict(pair.get("quoteToken"))
    db_pair = session.scalar(
        select(Pair).where(
            Pair.chain_id == str(chain_id),
            Pair.pair_address == pair_address,
        )
    )
    if db_pair is None:
        db_pair = Pair(
            chain_id=str(chain_id),
            dex_id=pair.get("dexId"),
            pair_address=pair_address,
            base_token_id=token.id,
            quote_token_symbol=quote_token.get("symbol"),
            dexscreener_url=pair.get("url"),
            pair_created_at=_parse_pair_created_at(pair.get("pairCreatedAt")),
        )
        session.add(db_pair)
        session.flush()
        return db_pair

    db_pair.dex_id = pair.get("dexId") or db_pair.dex_id
    db_pair.base_token_id = token.id
    db_pair.quote_token_symbol = quote_token.get("symbol") or db_pair.quote_token_symbol
    db_pair.dexscreener_url = pair.get("url") or db_pair.dexscreener_url
    db_pair.pair_created_at = (
        _parse_pair_created_at(pair.get("pairCreatedAt")) or db_pair.pair_created_at
    )
    return db_pair


def _create_snapshot(session: Session, db_pair: Pair, pair: dict[str, Any]) -> PairSnapshot:
    volume = _as_dict(pair.get("volume"))
    txns = _as_dict(pair.get("txns"))
    txns_5m = _as_dict(txns.get("m5"))
    txns_1h = _as_dict(txns.get("h1"))
    price_change = _as_dict(pair.get("priceChange"))

    snapshot = PairSnapshot(
        pair_id=db_pair.id,
        price_usd=_to_decimal(pair.get("priceUsd")),
        liquidity_usd=_to_decimal(_as_dict(pair.get("liquidity")).get("usd")),
        fdv=_to_decimal(pair.get("fdv")),
        market_cap=_to_decimal(pair.get("marketCap")),
        volume_5m=_to_decimal(volume.get("m5")),
        volume_1h=_to_decimal(volume.get("h1")),
        volume_6h=_to_decimal(volume.get("h6")),
        volume_24h=_to_decimal(volume.get("h24")),
        txns_5m_buys=_to_int(txns_5m.get("buys")),
        txns_5m_sells=_to_int(txns_5m.get("sells")),
        txns_1h_buys=_to_int(txns_1h.get("buys")),
        txns_1h_sells=_to_int(txns_1h.get("sells")),
        price_change_5m=_to_decimal(price_change.get("m5")),
        price_change_1h=_to_decimal(price_change.get("h1")),
        price_change_6h=_to_decimal(price_change.get("h6")),
        price_change_24h=_to_decimal(price_change.get("h24")),
        raw_json=pair.get("raw") if isinstance(pair.get("raw"), dict) else pair,
    )
    session.add(snapshot)
    session.flush()
    return snapshot


def _create_alert(
    session: Session,
    pair_id: int,
    snapshot_id: int,
    score: int,
    level: str,
    reasons: list[str],
) -> Alert:
    alert = Alert(
        pair_id=pair_id,
        snapshot_id=snapshot_id,
        score=score,
        level=level,
        reason="\n".join(reasons) if reasons else "Score threshold reached",
        sent_to_telegram=False,
    )
    session.add(alert)
    session.flush()
    return alert


def _save_pair_snapshot(pair: dict[str, Any]) -> tuple[int, int]:
    session = SessionLocal()
    try:
        token = _upsert_token(session, pair)
        db_pair = _upsert_pair(session, pair, token)
        snapshot = _create_snapshot(session, db_pair, pair)
        pair_id = db_pair.id
        snapshot_id = snapshot.id
        session.commit()
        return pair_id, snapshot_id
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _write_alert(
    pair_id: int,
    snapshot_id: int,
    score: int,
    level: str,
    reasons: list[str],
) -> int:
    session = SessionLocal()
    try:
        alert = _create_alert(session, pair_id, snapshot_id, score, level, reasons)
        alert_id = alert.id
        session.commit()
        return alert_id
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _update_alert_sent_status(alert_id: int, sent: bool) -> None:
    session = SessionLocal()
    try:
        alert = session.get(Alert, alert_id)
        if alert is None:
            logger.warning("Alert was not found while updating Telegram status: id=%s", alert_id)
            return
        alert.sent_to_telegram = sent
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        logger.exception("Failed to update Telegram status: alert_id=%s", alert_id)
    finally:
        session.close()


async def run_collection_cycle() -> dict[str, int | str]:
    if _collection_lock.locked():
        logger.warning("Collection cycle is already running; skipping this run")
        skipped_summary: dict[str, int | str] = _summary()
        skipped_summary["status"] = "skipped"
        return skipped_summary

    async with _collection_lock:
        summary: dict[str, int | str] = _summary()
        logger.info("Starting DEX pair collection cycle")

        try:
            candidates = await fetch_candidate_pairs()
        except Exception:
            logger.exception("Failed to fetch candidate pairs")
            candidates = []

        summary["fetched"] = len(candidates)
        for pair in candidates:
            pair_address = pair.get("pairAddress")
            base_symbol = _as_dict(pair.get("baseToken")).get("symbol")

            try:
                pair_id, snapshot_id = _save_pair_snapshot(pair)
                summary["snapshots_created"] = int(summary["snapshots_created"]) + 1
            except SQLAlchemyError:
                logger.exception("Database error while saving pair snapshot: pair=%s", pair_address)
                continue
            except Exception:
                logger.exception("Unexpected error while saving pair snapshot: pair=%s", pair_address)
                continue

            try:
                early_watch_rejection_reasons = get_early_watch_rejection_reasons(pair)
                if early_watch_rejection_reasons:
                    logger.info(
                        "Pair rejected by early watch filters: pair=%s base_symbol=%s reasons=%s",
                        pair_address,
                        base_symbol,
                        early_watch_rejection_reasons,
                    )
                else:
                    summary["early_watch_passed"] = int(summary["early_watch_passed"]) + 1
                    logger.info(
                        "Pair passed early watch filters: pair=%s base_symbol=%s",
                        pair_address,
                        base_symbol,
                    )

                if not passes_basic_filters(pair):
                    rejection_reasons = get_filter_rejection_reasons(pair)
                    logger.info(
                        "Pair rejected by basic filters: pair=%s base_symbol=%s reasons=%s",
                        pair_address,
                        base_symbol,
                        rejection_reasons,
                    )
                    continue

                summary["passed_filters"] = int(summary["passed_filters"]) + 1
                score, reasons = calculate_market_score(pair)
                summary["scored"] = int(summary["scored"]) + 1
                level = should_alert(score)

                if level is not None:
                    alert_id = _write_alert(pair_id, snapshot_id, score, level, reasons)
                    summary["alerts_created"] = int(summary["alerts_created"]) + 1
                    message = render_alert_message(pair, score, level, reasons)
                    sent = await send_telegram_message(message)
                    _update_alert_sent_status(alert_id, sent)
                    if sent:
                        summary["telegram_sent"] = int(summary["telegram_sent"]) + 1
            except SQLAlchemyError:
                logger.exception("Database error while scoring or alerting pair: pair=%s", pair_address)
            except Exception:
                logger.exception("Unexpected error while scoring or alerting pair: pair=%s", pair_address)

        set_last_collection_summary(summary)
        logger.info("Finished DEX pair collection cycle: summary=%s", summary)
        return summary
