"""D286: one-shot current 24-closed-hour research rank of ALL automatic USDT perps.

No ticker rolling volume, no token-by-token dossiers, no orders, no database IO.
An owner-only public Bybit GET census is repeated before and AFTER all candles.
The selected Top 50 is PROVISIONAL research, never a trading allowlist.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from typing import Any, Callable

from crypto_intelligence_agent.bybit_paginated_universe_research import (
    MAX_PAGES, _cursor, _response,
)
from crypto_intelligence_agent.bybit_public_j1_transport import (
    BoundedBybitPublicClient, J1BybitCaptureError, instruments_url, kline_url,
)
from crypto_intelligence_agent.j1_auto_usdt_perp import (
    AutomaticPerpResearchPool, screen_bybit_usdt_perps_offline,
    rank_auto_candidates_closed24h_offline,
)
from crypto_intelligence_agent.market_data import DataValidationError
from scripts.audit_bybit_marketwide_closed24h import (
    CensusAbstain, _closed_candles, _dec,
)

HOUR_MS = 3_600_000
MIN_START_AFTER_CLOSE_MS = 60_000
MAX_START_AFTER_CLOSE_MS = 120_000
MAX_END_AFTER_CLOSE_MS = 900_000
MAX_CANDIDATES = 400
MAX_GET_BUDGET = 450


def _blank() -> dict[str, Any]:
    return {
        "schema_version": "j1-auto-current-closed24h-research-only-v1",
        "status": "optin_required",
        "failure_category": None,
        "decision_closed_hour_end_ms": None,
        "catalog_census_matches_before_after": False,
        "current_catalog_provisional_candidates": 0,
        "complete_closed24h_candidates": 0,
        "insufficient_closed24h_candidates": 0,
        "ranked_research_candidates": 0,
        "requests_attempted": 0,
        "database_modified": False,
        "network_accessed": False,
        "rolling_ticker_volume_used": False,
        "current_crypto_identity_independently_verified": False,
        "marketwide_top50_verified": False,
        "live_trading_authorized": False,
        "orders_sent": False,
    }


def _catalog(*, client: Any, clock: Callable[[], int], decision: int
             ) -> AutomaticPerpResearchPool:
    pages: list[dict] = []
    cursors: list[str | None] = []
    timestamps: list[int] = []
    expected: str | None = None
    for _ in range(MAX_PAGES):
        before = clock()
        if (type(before) is not int or not decision + MIN_START_AFTER_CLOSE_MS
                <= before <= decision + MAX_END_AFTER_CLOSE_MS):
            raise DataValidationError("catalog outside closed UTC research window")
        _, payload = client.get(instruments_url(cursor=expected))
        received = clock()
        if (type(received) is not int or not decision + MIN_START_AFTER_CLOSE_MS
                <= received <= decision + MAX_END_AFTER_CLOSE_MS):
            raise DataValidationError("catalog response crossed UTC deadline")
        _response(payload, label="current closed24h catalog", at_ms=received,
                  age_ms=120_000)
        pages.append(payload)
        cursors.append(expected)
        timestamps.append(received)
        next_cursor = _cursor(
            payload["result"].get("nextPageCursor"), terminal_ok=True,
        )
        if next_cursor == "":
            break
        if next_cursor == expected or next_cursor in cursors:
            raise DataValidationError("catalog cursor cycle")
        expected = next_cursor
    else:
        raise DataValidationError("catalog page limit")
    return screen_bybit_usdt_perps_offline(
        instrument_pages=tuple(pages),
        requested_cursors=tuple(cursors),
        page_received_at_ms=tuple(timestamps),
        observed_at_ms=timestamps[-1],
    )


def research_current_closed24h_once(
    *, client: Any, clock_ms: Callable[[], int],
    allow_public_network: bool = False,
    confirm_region_and_personal_research: bool = False,
    include_public_symbols: bool = False,
    owner_ok: bool | None = None,
    max_candidates: int = MAX_CANDIDATES,
) -> dict[str, Any]:
    """Bounded 2-catalog + N-kline public GET; zero persistent side effects.

    The lower bound on GET cadence is enforced by BoundedBybitPublicClient in
    production; the clock checks fail closed if that cadence overruns HH:15.
    """
    out = _blank()
    owner = ((os.name == "posix" and os.getuid() == os.geteuid()
              and os.geteuid() != 0) if owner_ok is None else owner_ok)
    if (owner is not True or allow_public_network is not True
            or confirm_region_and_personal_research is not True):
        return out
    if (client is None or not callable(getattr(client, "get", None))
            or not callable(clock_ms) or type(include_public_symbols) is not bool
            or type(max_candidates) is not int
            or not 50 <= max_candidates <= MAX_CANDIDATES):
        out["status"] = "abstain"
        out["failure_category"] = "invalid_configuration"
        return out
    stage = "clock"
    try:
        now = clock_ms()
        if type(now) is not int or not 1_600_000_000_000 <= now < 4_102_444_800_000:
            raise DataValidationError("invalid observation clock")
        decision = now // HOUR_MS * HOUR_MS
        out["decision_closed_hour_end_ms"] = decision
        if not MIN_START_AFTER_CLOSE_MS <= now - decision <= MAX_START_AFTER_CLOSE_MS:
            raise DataValidationError("not in safe initial closed-hour window")
        stage = "catalog_before"
        before = _catalog(client=client, clock=clock_ms, decision=decision)
        candidates = before.candidate_symbols
        out["current_catalog_provisional_candidates"] = len(candidates)
        if not 50 <= len(candidates) <= max_candidates:
            raise DataValidationError("provisional universe below50 or over budget")
        # Real transport imposes >=2 seconds between GETs, no hidden retry.
        remaining = decision + MAX_END_AFTER_CLOSE_MS - clock_ms()
        minimum_ms = 2_000 * (len(candidates) + before.catalog_pages + 1) + 20_000
        if type(remaining) is not int or remaining < minimum_ms:
            raise DataValidationError("insufficient safe UTC budget before first kline")
        turnovers: dict[str, tuple] = {}
        stage = "closed_kline"
        start = decision - 24 * HOUR_MS
        for sym in candidates:
            now_get = clock_ms()
            if (type(now_get) is not int
                    or not decision + MIN_START_AFTER_CLOSE_MS
                    <= now_get <= decision + MAX_END_AFTER_CLOSE_MS):
                raise DataValidationError("closed kline request outside safe window")
            _, payload = client.get(kline_url(sym, start, decision))
            receipt = clock_ms()
            if (type(receipt) is not int
                    or not decision + MIN_START_AFTER_CLOSE_MS
                    <= receipt <= decision + MAX_END_AFTER_CLOSE_MS):
                raise DataValidationError("closed kline response crossed deadline")
            bars = _closed_candles(payload, sym, decision, allow_short=True)
            turnovers[sym] = tuple(
                (int(row[0]), _dec(row[-1], field="quote_turnover"))
                for row in reversed(bars)
            )
        stage = "catalog_after"
        after = _catalog(client=client, clock=clock_ms, decision=decision)
        same = (
            before.candidate_symbols == after.candidate_symbols
            and before.scanned_contracts == after.scanned_contracts
            and before.excluded_documented_tradfi == after.excluded_documented_tradfi
            and before.excluded_provider_tradfi == after.excluded_provider_tradfi
            and before.excluded_fullname_tradfi == after.excluded_fullname_tradfi
            and before.excluded_ambiguous_or_malformed ==
                after.excluded_ambiguous_or_malformed
            and before.excluded_product == after.excluded_product
        )
        if not same:
            raise DataValidationError("catalog candidate drift during capture")
        out["catalog_census_matches_before_after"] = True
        stage = "rank"
        ranked = rank_auto_candidates_closed24h_offline(
            before, closed_hour_end_ms=decision,
            closed_candle_turnovers=turnovers,
        )
        if len(ranked.ranked) < 50:
            raise DataValidationError("fewer than 50 complete closed-hour candidates")
        rank_report = ranked.sanitized_report(
            include_public_symbols=include_public_symbols,
        )
        out.update({
            "status": "current_closed24h_provisional_perpetual_rank_research_only",
            "failure_category": None,
            "catalog_pre_observed_at_ms": before.observed_at_ms,
            "catalog_post_observed_at_ms": after.observed_at_ms,
            "catalog_scanned_contracts": before.scanned_contracts,
            "catalog_pages_each_pass": before.catalog_pages,
            "catalog_provisional_pool_digest_sha256":
                before.sanitized_report()["candidate_digest_sha256"],
            "complete_closed24h_candidates": ranked.covered_count,
            "insufficient_closed24h_candidates": ranked.insufficient_count,
            "zero_closed24h_turnover_candidates": ranked.zero_turnover_count,
            "ranked_research_candidates": len(ranked.ranked),
            "rank_digest_sha256": rank_report["rank_digest_sha256"],
            "source_research_only": True,
            "all_provisional_candidates_have_complete24h":
                ranked.insufficient_count == 0,
        })
        if include_public_symbols:
            out["ranked_public_research_symbols_only"] = rank_report[
                "research_ranked_symbols_only"
            ]
    except (DataValidationError, CensusAbstain, J1BybitCaptureError,
            TypeError, ValueError, OSError, OverflowError):
        out["status"] = "abstain"
        out["failure_category"] = "current_" + stage + "_rejected"
    finally:
        gets = getattr(client, "requests_attempted", 0)
        out["requests_attempted"] = (
            gets if type(gets) is int and 0 <= gets <= MAX_GET_BUDGET
            else MAX_GET_BUDGET
        )
        out["network_accessed"] = out["requests_attempted"] > 0
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-public-network", action="store_true")
    parser.add_argument("--confirm-region-and-personal-research",
                        action="store_true")
    parser.add_argument("--include-public-symbols", action="store_true")
    args = parser.parse_args(argv)
    result = research_current_closed24h_once(
        client=BoundedBybitPublicClient(),
        clock_ms=lambda: time.time_ns() // 1_000_000,
        allow_public_network=args.allow_public_network,
        confirm_region_and_personal_research=args.confirm_region_and_personal_research,
        include_public_symbols=args.include_public_symbols,
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=True))
    return 0 if result["status"] == (
        "current_closed24h_provisional_perpetual_rank_research_only"
    ) else 65


if __name__ == "__main__":
    raise SystemExit(main())
