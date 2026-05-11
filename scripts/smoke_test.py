import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

import app.jobs.collect_pairs as collect_pairs
from app.main import app
from app.db.models import CandidateObservation
from app.db.session import engine
from app.services.filters import (
    get_early_watch_rejection_reasons,
    get_filter_rejection_reasons,
    passes_basic_filters,
    passes_early_watch_filters,
)
from app.services.scoring import calculate_market_score
from app.services.alerts import (
    can_create_alert_after_cooldown,
    passes_alert_quality_gate,
)
from app.services.filter_v2 import (
    build_filter_v2_metrics,
    calculate_buy_ratio,
    calculate_fdv_volume_ratio_1h,
    calculate_liquidity_fdv_ratio,
    calculate_txns_1h_total,
    calculate_volume_liquidity_ratio_1h,
    evaluate_avoid_reasons_v2,
    evaluate_early_watch_v2,
    evaluate_filter_v2,
    evaluate_high_signal_v2,
    evaluate_watch_v2,
    safe_div,
)


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
        "priceChange": {"h1": 12, "h6": 18},
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
        "txns": {"h1": {"buys": 1, "sells": 3}},
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


def _watch_v2_mock_pair() -> dict:
    return {
        "chainId": "ethereum",
        "pairAddress": "0xwatchv2pair0000000000000000000000000001",
        "baseToken": {
            "address": "0xwatchv2token000000000000000000000000001",
            "symbol": "WATCH2",
            "name": "Watch V2 Token",
        },
        "liquidity": {"usd": 100_000},
        "volume": {"h1": 30_000},
        "txns": {"h1": {"buys": 22, "sells": 18}},
        "fdv": 20_000_000,
        "priceChange": {"h1": 1, "h6": 2, "h24": 15},
    }


def _overheated_v2_mock_pair() -> dict:
    return {
        "chainId": "ethereum",
        "pairAddress": "0xoverheatedv2pair000000000000000000000001",
        "baseToken": {
            "address": "0xoverheatedv2token00000000000000000000001",
            "symbol": "HOT2",
            "name": "Overheated V2 Token",
        },
        "liquidity": {"usd": 10_000},
        "volume": {"h1": 1_000},
        "txns": {"h1": {"buys": 1, "sells": 9}},
        "fdv": 250_000_000,
        "priceChange": {"h1": 120, "h6": 140, "h24": 450},
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
    checks.append(
        (
            "import /dashboard/observations endpoint",
            "/dashboard/observations" in route_paths,
            "dashboard observations route registered",
        )
    )
    checks.append(
        (
            "import CandidateObservation model",
            CandidateObservation.__tablename__ == "candidate_observations",
            CandidateObservation.__tablename__,
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
    alert_quality_passed, alert_quality_reasons = passes_alert_quality_gate(passing_pair)
    checks.append(
        (
            "passes_alert_quality_gate",
            alert_quality_passed and not alert_quality_reasons,
            "good mock pair checked",
        )
    )
    weak_alert_passed, weak_alert_reasons = passes_alert_quality_gate(rejected_pair)
    expected_alert_rejections = {
        "alert_liquidity_below_threshold",
        "alert_volume_1h_below_threshold",
        "alert_txns_1h_below_threshold",
        "alert_fdv_missing",
        "alert_buy_ratio_too_low",
        "alert_negative_momentum",
    }
    checks.append(
        (
            "passes_alert_quality_gate rejection reasons",
            not weak_alert_passed and expected_alert_rejections.issubset(set(weak_alert_reasons)),
            ",".join(weak_alert_reasons),
        )
    )
    now = datetime.now(timezone.utc)
    cooldown_allowed, cooldown_reason = can_create_alert_after_cooldown(
        now - timedelta(hours=1),
        "watch",
        "watch",
        now=now,
    )
    checks.append(
        (
            "alert cooldown blocks repeat",
            not cooldown_allowed and cooldown_reason == "cooldown_active",
            cooldown_reason,
        )
    )
    upgrade_allowed, upgrade_reason = can_create_alert_after_cooldown(
        now - timedelta(hours=1),
        "watch",
        "high",
        now=now,
    )
    checks.append(
        (
            "alert cooldown allows upgrade",
            upgrade_allowed and upgrade_reason == "level_upgrade",
            upgrade_reason,
        )
    )

    filter_v2_metrics = build_filter_v2_metrics(passing_pair)
    checks.append(
        (
            "filter v2 derived metrics",
            filter_v2_metrics["txns_1h_total"] == 200
            and filter_v2_metrics["buy_ratio"] == 0.6
            and filter_v2_metrics["volume_liquidity_ratio_1h"] == 0.5
            and filter_v2_metrics["fdv_volume_ratio_1h"] == 30
            and round(filter_v2_metrics["liquidity_fdv_ratio"] or 0, 4) == 0.0667,
            str(filter_v2_metrics),
        )
    )
    checks.append(
        (
            "filter v2 division by zero",
            safe_div(10, 0) is None
            and calculate_buy_ratio(0, 0) is None
            and calculate_volume_liquidity_ratio_1h(10, 0) is None
            and calculate_fdv_volume_ratio_1h(10, 0) is None
            and calculate_liquidity_fdv_ratio(10, 0) is None
            and calculate_txns_1h_total(None, None) == 0,
            "zero denominators checked",
        )
    )
    early_v2 = evaluate_early_watch_v2(build_filter_v2_metrics(early_watch_pair))
    checks.append(
        (
            "evaluate_early_watch_v2",
            early_v2["passed"],
            str(early_v2),
        )
    )
    watch_v2_pair = _watch_v2_mock_pair()
    watch_v2 = evaluate_watch_v2(build_filter_v2_metrics(watch_v2_pair))
    checks.append(
        (
            "evaluate_watch_v2",
            watch_v2["passed"],
            str(watch_v2),
        )
    )
    high_v2 = evaluate_high_signal_v2(filter_v2_metrics)
    final_high_v2 = evaluate_filter_v2(filter_v2_metrics)
    checks.append(
        (
            "evaluate_high_signal_v2",
            high_v2["passed"] and final_high_v2["status"] == "high_signal",
            str(final_high_v2),
        )
    )
    overheated_reasons = evaluate_avoid_reasons_v2(build_filter_v2_metrics(_overheated_v2_mock_pair()))
    expected_v2_avoid = {
        "liquidity_below_20k",
        "volume_1h_below_5k",
        "fdv_above_150m",
        "fdv_volume_ratio_too_high",
        "buy_ratio_too_low",
        "overheated_1h",
        "overheated_24h",
    }
    checks.append(
        (
            "evaluate_avoid_reasons_v2",
            expected_v2_avoid.issubset(set(overheated_reasons)),
            ",".join(overheated_reasons),
        )
    )
    checks.append(
        (
            "snapshot before filters pipeline",
            hasattr(collect_pairs, "_save_pair_snapshot"),
            "fetched pairs are saved before filter eligibility checks",
        )
    )

    client = TestClient(app)
    route_checks = [
        ("GET /api/status", client.get("/api/status")),
        ("GET /dashboard/pairs", client.get("/dashboard/pairs", auth=("admin", "admin"))),
        (
            "GET /dashboard/observations",
            client.get("/dashboard/observations", auth=("admin", "admin")),
        ),
    ]
    for name, response in route_checks:
        checks.append((name, response.status_code == 200, f"status_code={response.status_code}"))

    failed = False
    for name, ok, detail in checks:
        status = "OK" if ok else "FAIL"
        print(f"[{status}] {name}: {detail}")
        failed = failed or not ok

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
