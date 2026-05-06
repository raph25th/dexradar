import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload

from app.config import get_settings
from app.db.models import Alert, Pair, PairSnapshot, Token
from app.db.session import SessionLocal
from app.jobs.collect_pairs import run_collection_cycle
from app.logging_config import configure_logging
from app.runtime_state import get_runtime_state

configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title="eth-dex-radar", version="0.1.0")
scheduler: AsyncIOScheduler | None = None


def _json_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@app.on_event("startup")
async def startup() -> None:
    global scheduler
    settings = get_settings()
    if scheduler is not None and scheduler.running:
        logger.info("Scheduler is already running; startup hook will not start another one")
        return

    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        run_collection_cycle,
        trigger="interval",
        seconds=settings.poll_interval_seconds,
        id="collect_pairs",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    logger.info(
        "Collection scheduler started: interval_seconds=%s",
        settings.poll_interval_seconds,
    )


@app.on_event("shutdown")
async def shutdown() -> None:
    global scheduler
    if scheduler is not None and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Collection scheduler stopped")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/status")
async def status() -> dict[str, Any]:
    runtime_state = get_runtime_state()
    response: dict[str, Any] = {
        "status": "ok",
        "current_time": datetime.now(timezone.utc).isoformat(),
        "last_collection_at": runtime_state["last_collection_at"],
        "last_collection_summary": runtime_state["last_collection_summary"],
        "total_tokens": 0,
        "total_pairs": 0,
        "total_snapshots": 0,
        "total_alerts": 0,
    }

    session = SessionLocal()
    try:
        response["total_tokens"] = session.scalar(select(func.count()).select_from(Token)) or 0
        response["total_pairs"] = session.scalar(select(func.count()).select_from(Pair)) or 0
        response["total_snapshots"] = (
            session.scalar(select(func.count()).select_from(PairSnapshot)) or 0
        )
        response["total_alerts"] = session.scalar(select(func.count()).select_from(Alert)) or 0
    except SQLAlchemyError:
        logger.exception("Failed to build status response")
        response["status"] = "degraded"
    finally:
        session.close()

    return response


@app.post("/jobs/collect-once")
async def collect_once() -> dict[str, int | str]:
    return await run_collection_cycle()


@app.get("/alerts/recent")
async def recent_alerts() -> list[dict[str, Any]]:
    session = SessionLocal()
    try:
        alerts = session.scalars(
            select(Alert)
            .options(
                joinedload(Alert.pair).joinedload(Pair.base_token),
                joinedload(Alert.snapshot),
            )
            .order_by(Alert.created_at.desc())
            .limit(20)
        ).all()

        result: list[dict[str, Any]] = []
        for alert in alerts:
            pair = alert.pair
            token = pair.base_token
            snapshot = alert.snapshot
            result.append(
                {
                    "id": alert.id,
                    "score": alert.score,
                    "level": alert.level,
                    "reason": alert.reason,
                    "sent_to_telegram": alert.sent_to_telegram,
                    "created_at": alert.created_at.isoformat(),
                    "pair": {
                        "id": pair.id,
                        "chain_id": pair.chain_id,
                        "dex_id": pair.dex_id,
                        "pair_address": pair.pair_address,
                        "quote_token_symbol": pair.quote_token_symbol,
                        "dexscreener_url": pair.dexscreener_url,
                    },
                    "token": {
                        "id": token.id,
                        "address": token.address,
                        "symbol": token.symbol,
                        "name": token.name,
                    },
                    "snapshot": {
                        "id": snapshot.id,
                        "price_usd": _json_number(snapshot.price_usd),
                        "liquidity_usd": _json_number(snapshot.liquidity_usd),
                        "fdv": _json_number(snapshot.fdv),
                        "market_cap": _json_number(snapshot.market_cap),
                        "volume_1h": _json_number(snapshot.volume_1h),
                        "txns_1h_buys": snapshot.txns_1h_buys,
                        "txns_1h_sells": snapshot.txns_1h_sells,
                        "price_change_1h": _json_number(snapshot.price_change_1h),
                        "created_at": snapshot.created_at.isoformat(),
                    },
                }
            )
        return result
    finally:
        session.close()
