import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

import app.jobs.collect_pairs as collect_pairs
from app.main import app
from app.db.session import engine
from app.services.filters import (
    get_early_watch_rejection_reasons,
    get_filter_rejection_reasons,
    passes_basic_filters,
    passes_early_watch_filters,
)
from app.services.scoring import calculate_market_score


def _passing_mock_pair() -> dict:
    return {
        "chainId": "ethereum",
        "pairAddress": "0xpassingpair000000000000000000000000000001",
        "baseToken": {
            "address": "0xpassingtoken00000000000000000000000000001",
            "symbol": "PASS",
            "name": "Passing Token",
        },
        "liquidity": {"usd": 600_000},
        "volume": {"h1": 300_000},
        "txns": {"h1": {"buys": 120, "sells": 80}},
        "fdv": 9_000_000,
        "priceChange": {"h1": 12},
    }


def _rejected_mock_pair() -> dict:
    return {
        "chainId": "ethereum",
        "pairAddress": "0xrejectedpair0000000000000000000000000001",
        "baseToken": {
            "address": "0xrejectedtoken000000000000000000000000001",
            "symbol": "REJECT",
            "name": "Rejected Token",
        },
        "liquidity": {"usd": 10_000},
        "volume": {"h1": 1_000},
        "txns": {"h1": {"buys": 2, "sells": 1}},
        "fdv": None,
        "priceChange": {"h1": -5},
    }


def _early_watch_mock_pair() -> dict:
    return {
        "chainId": "ethereum",
        "pairAddress": "0xearlywatchpair00000000000000000000000001",
        "baseToken": {
            "address": "0xearlywatchtoken0000000000000000000000001",
            "symbol": "EARLY",
            "name": "Early Watch Token",
        },
        "liquidity": {"usd": 30_000},
        "volume": {"h1": 8_000},
        "txns": {"h1": {"buys": 8, "sells": 5}},
        "fdv": 80_000_000,
        "priceChange": {"h1": 8},
    }


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    checks.append(("import app.main", app.title == "eth-dex-radar", app.title))
    checks.append(
        (
            "import app.jobs.collect_pairs",
            hasattr(collect_pairs, "run_collection_cycle"),
            "run_collection_cycle imported",
        )
    )
    route_paths = {route.path for route in app.routes}
    checks.append(("import /status endpoint", "/status" in route_paths, "status route registered"))
    checks.append(("import /api/status endpoint", "/api/status" in route_paths, "api status route registered"))
    checks.append(("import /dashboard endpoint", "/dashboard" in route_paths, "dashboard route registered"))
    checks.append(
        (
            "import /dashboard/pairs endpoint",
            "/dashboard/pairs" in route_paths,
            "dashboard pairs route registered",
        )
    )
    checks.append(
        (
            "import /dashboard/alerts endpoint",
            "/dashboard/alerts" in route_paths,
            "dashboard alerts route registered",
        )
    )

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        checks.append(("database connection", True, "SELECT 1 ok"))
    except SQLAlchemyError as exc:
        checks.append(("database connection", False, str(exc)))

    passing_pair = _passing_mock_pair()
    checks.append(
        ("passes_basic_filters", passes_basic_filters(passing_pair), "passing mock pair checked")
    )

    rejected_pair = _rejected_mock_pair()
    rejection_reasons = get_filter_rejection_reasons(rejected_pair)
    expected_rejections = {
        "liquidity_below_threshold",
        "volume_1h_below_threshold",
        "txns_1h_below_threshold",
        "fdv_missing",
    }
    checks.append(
        (
            "get_filter_rejection_reasons",
            expected_rejections.issubset(set(rejection_reasons)),
            ",".join(rejection_reasons),
        )
    )

    early_watch_pair = _early_watch_mock_pair()
    checks.append(
        (
            "passes_early_watch_filters",
            passes_early_watch_filters(early_watch_pair)
            and not passes_basic_filters(early_watch_pair),
            "early watch mock pair checked",
        )
    )
    early_watch_rejection_reasons = get_early_watch_rejection_reasons(rejected_pair)
    checks.append(
        (
            "get_early_watch_rejection_reasons",
            expected_rejections.issubset(set(early_watch_rejection_reasons)),
            ",".join(early_watch_rejection_reasons),
        )
    )

    score, reasons = calculate_market_score(passing_pair)
    checks.append(("calculate_market_score", score >= 60 and bool(reasons), f"score={score}"))
    checks.append(
        (
            "snapshot before filters pipeline",
            hasattr(collect_pairs, "_save_pair_snapshot"),
            "fetched pairs are saved before filter eligibility checks",
        )
    )

    failed = False
    for name, ok, detail in checks:
        status = "OK" if ok else "FAIL"
        print(f"[{status}] {name}: {detail}")
        failed = failed or not ok

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
