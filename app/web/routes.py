from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload

from app.db.models import Alert, Pair, PairSnapshot, Token
from app.db.session import SessionLocal
from app.runtime_state import get_runtime_state
from app.web.auth import require_dashboard_auth

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

PairStatus = Literal["all", "early_watch", "basic", "alerted", "rejected", "tracked"]
PairSort = Literal["latest", "volume_1h", "liquidity", "txns_1h", "price_change_1h", "fdv"]

STATUS_META: dict[str, dict[str, str]] = {
    "alerted": {"label": "Alerted", "class": "status-alerted"},
    "basic": {"label": "Basic Signal", "class": "status-basic"},
    "early_watch": {"label": "Early Watch", "class": "status-early-watch"},
    "rejected": {"label": "Rejected", "class": "status-rejected"},
    "tracked": {"label": "Tracked", "class": "status-tracked"},
}

STATUS_PRIORITY = {
    "alerted": 0,
    "basic": 1,
    "early_watch": 2,
    "tracked": 3,
    "rejected": 4,
}


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_money(value: Any) -> str:
    number = _as_float(value)
    if number is None:
        return "n/a"
    return f"${number:,.0f}"


def _format_number(value: Any, digits: int = 2) -> str:
    number = _as_float(value)
    if number is None:
        return "n/a"
    return f"{number:,.{digits}f}"


def _format_percent(value: Any) -> str:
    number = _as_float(value)
    if number is None:
        return "n/a"
    return f"{number:+.2f}%"


def _short_address(value: str | None) -> str:
    if not value:
        return "n/a"
    if len(value) <= 14:
        return value
    return f"{value[:6]}...{value[-4:]}"


def _format_datetime(value: datetime | None) -> str:
    if value is None:
        return "n/a"
    return value.isoformat()


def _format_relative_time(value: datetime | None) -> str:
    if value is None:
        return "n/a"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)

    now = datetime.now(value.tzinfo)
    seconds = int((now - value).total_seconds())
    if seconds < 0:
        return "now"
    if seconds < 60:
        return f"{seconds}s ago"

    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"

    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"

    days = hours // 24
    return f"{days}d ago"


templates.env.filters["money"] = _format_money
templates.env.filters["number"] = _format_number
templates.env.filters["percent"] = _format_percent
templates.env.filters["short_address"] = _short_address
templates.env.filters["datetime"] = _format_datetime
templates.env.filters["relative_time"] = _format_relative_time


def _txns_1h(snapshot: PairSnapshot) -> int:
    return int((snapshot.txns_1h_buys or 0) + (snapshot.txns_1h_sells or 0))


def _snapshot_passes_early_watch(snapshot: PairSnapshot) -> bool:
    liquidity_usd = _as_float(snapshot.liquidity_usd) or 0.0
    volume_1h = _as_float(snapshot.volume_1h) or 0.0
    txns_1h = _txns_1h(snapshot)
    fdv = _as_float(snapshot.fdv)
    return (
        liquidity_usd >= 20_000
        and volume_1h >= 5_000
        and txns_1h >= 10
        and fdv is not None
        and fdv <= 100_000_000
    )


def _snapshot_passes_basic(snapshot: PairSnapshot) -> bool:
    liquidity_usd = _as_float(snapshot.liquidity_usd) or 0.0
    volume_1h = _as_float(snapshot.volume_1h) or 0.0
    txns_1h = _txns_1h(snapshot)
    fdv = _as_float(snapshot.fdv)
    return (
        liquidity_usd >= 100_000
        and volume_1h >= 50_000
        and txns_1h >= 50
        and fdv is not None
        and fdv <= 50_000_000
    )


def _snapshot_has_filter_metrics(snapshot: PairSnapshot) -> bool:
    return any(
        value is not None
        for value in (
            snapshot.liquidity_usd,
            snapshot.volume_1h,
            snapshot.fdv,
            snapshot.txns_1h_buys,
            snapshot.txns_1h_sells,
        )
    )


def _pair_status(snapshot: PairSnapshot, alerts_count: int) -> dict[str, str]:
    if alerts_count > 0:
        key = "alerted"
    elif _snapshot_passes_basic(snapshot):
        key = "basic"
    elif _snapshot_passes_early_watch(snapshot):
        key = "early_watch"
    elif _snapshot_has_filter_metrics(snapshot):
        key = "rejected"
    else:
        key = "tracked"

    return {"key": key, **STATUS_META[key]}


def _sort_pair_rows(rows: list[dict[str, Any]], sort: PairSort, status: PairStatus) -> list[dict[str, Any]]:
    def metric(row: dict[str, Any]) -> float:
        snapshot = row["snapshot"]
        if sort == "liquidity":
            return _as_float(snapshot.liquidity_usd) or -1.0
        if sort == "txns_1h":
            return float(row["txns_1h"])
        if sort == "price_change_1h":
            return _as_float(snapshot.price_change_1h) or -999_999.0
        if sort == "fdv":
            fdv = _as_float(snapshot.fdv)
            return fdv if fdv is not None else float("inf")
        if sort == "latest":
            created_at = snapshot.created_at
            if created_at is None:
                return 0.0
            return created_at.timestamp()
        return _as_float(snapshot.volume_1h) or -1.0

    if sort == "fdv":
        return sorted(rows, key=metric)

    if status == "all" and sort == "volume_1h":
        return sorted(
            rows,
            key=lambda row: (
                STATUS_PRIORITY.get(row["status"]["key"], 99),
                -metric(row),
            ),
        )

    return sorted(rows, key=metric, reverse=True)


def _build_status_payload() -> dict[str, Any]:
    runtime_state = get_runtime_state()
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "status": "ok",
        "total_tokens": 0,
        "total_pairs": 0,
        "total_snapshots": 0,
        "total_alerts": 0,
        "snapshots_last_1h": 0,
        "snapshots_last_24h": 0,
        "last_snapshot_at": None,
        "last_collection_summary": runtime_state["last_collection_summary"],
    }

    session = SessionLocal()
    try:
        payload["total_tokens"] = session.scalar(select(func.count()).select_from(Token)) or 0
        payload["total_pairs"] = session.scalar(select(func.count()).select_from(Pair)) or 0
        payload["total_snapshots"] = (
            session.scalar(select(func.count()).select_from(PairSnapshot)) or 0
        )
        payload["total_alerts"] = session.scalar(select(func.count()).select_from(Alert)) or 0
        payload["snapshots_last_1h"] = (
            session.scalar(
                select(func.count())
                .select_from(PairSnapshot)
                .where(PairSnapshot.created_at >= now - timedelta(hours=1))
            )
            or 0
        )
        payload["snapshots_last_24h"] = (
            session.scalar(
                select(func.count())
                .select_from(PairSnapshot)
                .where(PairSnapshot.created_at >= now - timedelta(hours=24))
            )
            or 0
        )
        last_snapshot_at = session.scalar(select(func.max(PairSnapshot.created_at)))
        payload["last_snapshot_at"] = (
            last_snapshot_at.isoformat() if last_snapshot_at is not None else None
        )
    except SQLAlchemyError:
        payload["status"] = "degraded"
    finally:
        session.close()

    return payload


@router.get("/api/status")
async def api_status() -> dict[str, Any]:
    return _build_status_payload()


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    _: Annotated[str, Depends(require_dashboard_auth)],
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "request": request,
            "page_title": "Overview",
            "status": _build_status_payload(),
        },
    )


@router.get("/dashboard/pairs", response_class=HTMLResponse)
async def dashboard_pairs(
    request: Request,
    _: Annotated[str, Depends(require_dashboard_auth)],
    min_liquidity: float | None = Query(default=None, ge=0),
    min_volume_1h: float | None = Query(default=None, ge=0),
    min_txns_1h: int | None = Query(default=None, ge=0),
    max_fdv: float | None = Query(default=None, ge=0),
    status: PairStatus = Query(default="all"),
    sort: PairSort = Query(default="volume_1h"),
    limit: int = Query(default=100, ge=1, le=500),
) -> HTMLResponse:
    row_number = func.row_number().over(
        partition_by=PairSnapshot.pair_id,
        order_by=(PairSnapshot.created_at.desc(), PairSnapshot.id.desc()),
    )
    latest_snapshot_ids = (
        select(
            PairSnapshot.id.label("snapshot_id"),
            row_number.label("row_number"),
        )
        .subquery()
    )

    alerts_count_subquery = (
        select(Alert.pair_id.label("pair_id"), func.count(Alert.id).label("alerts_count"))
        .group_by(Alert.pair_id)
        .subquery()
    )

    query = (
        select(
            Pair,
            PairSnapshot,
            Token,
            func.coalesce(alerts_count_subquery.c.alerts_count, 0).label("alerts_count"),
        )
        .join(PairSnapshot, PairSnapshot.pair_id == Pair.id)
        .join(latest_snapshot_ids, latest_snapshot_ids.c.snapshot_id == PairSnapshot.id)
        .join(Token, Token.id == Pair.base_token_id)
        .outerjoin(alerts_count_subquery, alerts_count_subquery.c.pair_id == Pair.id)
        .where(latest_snapshot_ids.c.row_number == 1)
    )

    if min_liquidity is not None:
        query = query.where(PairSnapshot.liquidity_usd >= min_liquidity)
    if min_volume_1h is not None:
        query = query.where(PairSnapshot.volume_1h >= min_volume_1h)
    if min_txns_1h is not None:
        query = query.where(
            PairSnapshot.txns_1h_buys + PairSnapshot.txns_1h_sells >= min_txns_1h
        )
    if max_fdv is not None:
        query = query.where(PairSnapshot.fdv <= max_fdv)

    session = SessionLocal()
    try:
        rows = session.execute(query).all()
        pairs = []
        for pair, snapshot, token, alerts_count in rows:
            alerts_count = int(alerts_count or 0)
            pair_status = _pair_status(snapshot, alerts_count)
            if status != "all" and pair_status["key"] != status:
                continue

            pairs.append(
                {
                    "pair": pair,
                    "snapshot": snapshot,
                    "token": token,
                    "txns_1h": _txns_1h(snapshot),
                    "buys_1h": snapshot.txns_1h_buys,
                    "sells_1h": snapshot.txns_1h_sells,
                    "alerts_count": alerts_count,
                    "status": pair_status,
                }
            )

        pairs = _sort_pair_rows(pairs, sort, status)[:limit]
    finally:
        session.close()

    return templates.TemplateResponse(
        request,
        "pairs.html",
        {
            "request": request,
            "page_title": "Pairs",
            "pairs": pairs,
            "filters": {
                "min_liquidity": min_liquidity,
                "min_volume_1h": min_volume_1h,
                "min_txns_1h": min_txns_1h,
                "max_fdv": max_fdv,
                "status": status,
                "sort": sort,
                "limit": limit,
            },
        },
    )


@router.get("/dashboard/pairs/{pair_id}", response_class=HTMLResponse)
async def dashboard_pair_detail(
    request: Request,
    pair_id: int,
    _: Annotated[str, Depends(require_dashboard_auth)],
) -> HTMLResponse:
    session = SessionLocal()
    try:
        pair = session.scalar(
            select(Pair)
            .options(joinedload(Pair.base_token))
            .where(Pair.id == pair_id)
        )
        if pair is None:
            raise HTTPException(status_code=404, detail="Pair not found")

        latest_snapshot = session.scalar(
            select(PairSnapshot)
            .where(PairSnapshot.pair_id == pair_id)
            .order_by(PairSnapshot.created_at.desc(), PairSnapshot.id.desc())
            .limit(1)
        )
        snapshots = session.scalars(
            select(PairSnapshot)
            .where(PairSnapshot.pair_id == pair_id)
            .order_by(PairSnapshot.created_at.desc(), PairSnapshot.id.desc())
            .limit(50)
        ).all()
        alerts = session.scalars(
            select(Alert)
            .where(Alert.pair_id == pair_id)
            .order_by(Alert.created_at.desc(), Alert.id.desc())
            .limit(50)
        ).all()
        token = pair.base_token
        pair_data = {
            "id": pair.id,
            "chain_id": pair.chain_id,
            "dex_id": pair.dex_id,
            "pair_address": pair.pair_address,
            "quote_token_symbol": pair.quote_token_symbol,
            "dexscreener_url": pair.dexscreener_url,
            "pair_created_at": pair.pair_created_at,
            "created_at": pair.created_at,
            "updated_at": pair.updated_at,
        }
        token_data = {
            "id": token.id,
            "chain_id": token.chain_id,
            "address": token.address,
            "symbol": token.symbol,
            "name": token.name,
        }
    finally:
        session.close()

    return templates.TemplateResponse(
        request,
        "pair_detail.html",
        {
            "request": request,
            "page_title": f"{token_data['symbol'] or 'Pair'} Detail",
            "pair": pair_data,
            "token": token_data,
            "latest_snapshot": latest_snapshot,
            "snapshots": snapshots,
            "alerts": alerts,
            "latest_txns_1h": _txns_1h(latest_snapshot) if latest_snapshot else 0,
        },
    )


@router.get("/dashboard/alerts", response_class=HTMLResponse)
async def dashboard_alerts(
    request: Request,
    _: Annotated[str, Depends(require_dashboard_auth)],
) -> HTMLResponse:
    session = SessionLocal()
    try:
        alerts = session.scalars(
            select(Alert)
            .options(
                joinedload(Alert.pair).joinedload(Pair.base_token),
                joinedload(Alert.snapshot),
            )
            .order_by(Alert.created_at.desc(), Alert.id.desc())
            .limit(50)
        ).all()
    finally:
        session.close()

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "request": request,
            "page_title": "Alerts",
            "alerts": alerts,
            "status": _build_status_payload(),
            "alerts_page": True,
        },
    )
