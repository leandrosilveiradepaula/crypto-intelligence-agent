"""D482: owner-only, persistent, explicitly FICTIONAL PAPER-DEMO open.

Use the existing D442 J3 cost veto, D426 AUTO4 scenario seed, D425
persisted position route, D391 intra-hour supervisor, and D446 J5 reader.
A real Bybit public post-ACK quote is a PRICE REFERENCE, never a broker fill
or an approved hourly J2 signal. No account, order sender, J1 or expiry clock.
This CLI can create one demo position in a previously EMPTY owner-only folder.
"""
from __future__ import annotations

import argparse
from decimal import Decimal, localcontext
import json
import os
from pathlib import Path
import time

from crypto_intelligence_agent.bybit_closed_stream_cache import _scope_contract_fingerprint
from crypto_intelligence_agent.bybit_public_ticker_optin_d390 import _public_bybit_session
from crypto_intelligence_agent.bybit_public_ticker_state_d385 import (
    BybitPublicTickerBook, BybitTickerQuote,
)
from crypto_intelligence_agent.bybit_public_ticker_supervisor_d386 import (
    TickerLeaseBudget, supervise_public_tickers,
)
from crypto_intelligence_agent.j2_public_btc_scope_d441 import fetch_single_btc_scope_from_public_rest
from crypto_intelligence_agent.j2_j3_j4_btc_paper_shadow_d442 import (
    CostedShadowPolicy, _assumed_entry_cost_and_stop_margin_screen,
)
from crypto_intelligence_agent.j4_shadow_public_paper_pilot_d426 import (
    ShadowPaperPolicy, _eligible_anchor, _seed_paper_at_quote,
    _PLAN, _POS_ID,
)
from crypto_intelligence_agent.j4_private_paper_ws_operator_d425 import (
    _private_directory, load_private_paper_routes,
)
from crypto_intelligence_agent.j5_owner_paper_positions_d446 import read_owner_paper_positions
from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.synthetic_manual_exit_replay import _EXACT_CONTEXT
from crypto_intelligence_agent.synthetic_position_state import SyntheticSide

SCHEMA = "d482-owner-persistent-public-price-paper-demo-v1"
_MANIFEST = "paper-routes.json"
_MAX_MANIFEST_BYTES = 4096
_BPS = Decimal("10000")


def create_persistent_demo(
    *, paper_directory: Path, quote: BybitTickerQuote,
    policy: CostedShadowPolicy, universe_at_ms: int,
):
    """Explicit price-anchored fixture: never an observed strategy signal.

    Prevent replay/overwrite, reuse existing AUTO4 position/route, and keep
    all J3 vetoes. The only 'fill' is labelled fabricated in D426 AUTO4.
    """
    home = _private_directory(paper_directory)
    if any(home.iterdir()):
        raise DataValidationError("D482 requires a fresh empty PAPER-DEMO directory")
    if type(policy) is not CostedShadowPolicy or not _eligible_anchor(
        quote, policy.shadow, universe_at_ms
    ):
        raise DataValidationError("D482 fresh public post-ACK quote required")
    target_ok, stop_ok = _assumed_entry_cost_and_stop_margin_screen(quote, policy)
    if not target_ok or not stop_ok:
        raise DataValidationError("D482 cost or stop-margin veto")
    with localcontext(_EXACT_CONTEXT):
        mark = quote.mark_price
        direction = 1 if policy.shadow.side is SyntheticSide.LONG else -1
        stop = mark * (1 - direction * policy.shadow.stop_distance_bps / _BPS)
        targets = [
            mark * (1 + direction * ratio / _BPS)
            for ratio in (
                policy.shadow.target1_distance_bps,
                policy.shadow.target2_distance_bps,
            )
        ]
    if min(stop, *targets) <= 0:
        raise DataValidationError("D482 invalid hypothetical levels")
    # D426 creates the existing AUTO4 ledger with a disclosed fixture OPEN
    # FILL. It never claims Bybit executed anything.
    journal = home / "paper-positions.sqlite"
    router = _seed_paper_at_quote(journal, policy.shadow, quote)
    journal.chmod(0o600)
    manifest = {
        "schema_version": "j4-private-paper-routes-d425-v1",
        "positions": [{
            "position_id": _POS_ID, "plan_version": _PLAN,
            "stop_mark_price": format(stop, "f"),
            "target_prices": [format(t, "f") for t in targets],
            "max_spread_bps": format(policy.shadow.max_entry_spread_bps, "f"),
            "runner": None,
        }],
    }
    raw = json.dumps(manifest, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=True).encode("ascii")
    if not 2 <= len(raw) <= _MAX_MANIFEST_BYTES:
        raise DataValidationError("D482 manifest size invalid")
    fd = os.open(home / _MANIFEST,
                 os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        if os.write(fd, raw) != len(raw):
            raise DataValidationError("D482 manifest short write")
        os.fsync(fd)
    finally:
        os.close(fd)
    verified = load_private_paper_routes(home)
    if verified.monitored_position_ids != (_POS_ID,):
        raise DataValidationError("D482 J4 route not recoverable")
    snapshot = read_owner_paper_positions(directory=home)
    if (len(snapshot["positions"]) != 1
            or snapshot.get("orders_sent") is not False):
        raise DataValidationError("D482 J5 snapshot not recoverable")
    return router, {
        "symbol": "BTCUSDT",
        "direction": policy.shadow.side.value,
        "reference_mark": format(mark, "f"),
        "stop_reference": format(stop, "f"),
        "target_references": [format(t, "f") for t in targets],
        "reference_received_at_ms": quote.received_at_ms,
        "nominal_margin_usdt": str(policy.shadow.margin_quote),
        "configured_leverage": policy.shadow.leverage,
        "notional_usdt_approx": str(
            policy.shadow.margin_quote * Decimal(policy.shadow.leverage)
        ),
        "source": "bybit_v5_public_post_ack_quote_unverified",
        "entry_provenance": "EXPLICIT_PAPER_DEMO_NOT_J2_SIGNAL",
        "open_fill": "FABRICATED_FIXTURE_NOT_BYBIT_EXECUTION",
        "live_orders_sent": False,
        "real_collateral_debited": False,
        "position_expires_at": None,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--paper-directory", type=Path, required=True)
    p.add_argument("--seconds", type=int, default=20)
    p.add_argument("--max-frames", type=int, default=10000)
    p.add_argument("--side", choices=("LONG", "SHORT"), default="LONG")
    p.add_argument("--margin-quote", default="5")
    p.add_argument("--leverage", type=int, default=50)
    p.add_argument("--stop-bps", default="50")
    p.add_argument("--first-target-bps", default="200")
    p.add_argument("--second-target-bps", default="300")
    for key in ("allow-public-network", "allow-public-websocket",
                "confirm-personal-readonly-research", "confirm-region-eligible",
                "confirm-public-data-rights", "enable-explicit-paper-demo"):
        p.add_argument("--" + key, action="store_true")
    args = p.parse_args(argv)
    flags = (
        args.allow_public_network, args.allow_public_websocket,
        args.confirm_personal_readonly_research, args.confirm_region_eligible,
        args.confirm_public_data_rights, args.enable_explicit_paper_demo,
    )
    if not all(flags):
        print(json.dumps({"status": "explicit_demo_permissions_required",
                          "orders_sent": False, "network_attempted": False}))
        return 77
    try:
        if (os.name != "posix" or os.getuid() != os.geteuid()
                or os.geteuid() == 0):
            raise DataValidationError("D482 nonroot owner required")
        os.umask(0o077)
        home = _private_directory(args.paper_directory)
        if any(home.iterdir()):
            raise DataValidationError("D482 demo directory not empty")
        budget = TickerLeaseBudget(1, args.max_frames, args.seconds)
        if args.seconds > 60 or args.max_frames > 100_000:
            raise DataValidationError("D482 bounded real quote lease required")
        policy = CostedShadowPolicy(
            ShadowPaperPolicy(
                "BTCUSDT", SyntheticSide(args.side),
                margin_quote=Decimal(args.margin_quote),
                leverage=args.leverage,
                stop_distance_bps=Decimal(args.stop_bps),
                target1_distance_bps=Decimal(args.first_target_bps),
                target2_distance_bps=Decimal(args.second_target_bps),
            ),
            Decimal("6"), Decimal("6"), Decimal("3"), Decimal("3"),
        )
        scope = fetch_single_btc_scope_from_public_rest()
        now_ms = time.time_ns() // 1_000_000
        _scope_contract_fingerprint(scope)
        if (len(scope.contracts) != 1
                or scope.contracts[0].symbol != "BTCUSDT"
                or not 0 <= now_ms - scope.observed_at_ms <= 30_000
                or Decimal(policy.shadow.leverage) > scope.contracts[0].max_leverage):
            raise DataValidationError("D482 valid public BTC contract required")
        book = BybitPublicTickerBook(
            ranked_symbols=("BTCUSDT",), universe_at_ms=scope.observed_at_ms,
        )
        created = None
        router = None
        seen_after = 0
        rejected = 0
        def on_reset():
            if router is not None:
                router.begin_new_market_session()
        def on_quote(quote):
            nonlocal router, created, seen_after, rejected
            if router is None:
                if not _eligible_anchor(quote, policy.shadow, scope.observed_at_ms):
                    rejected += 1
                    return
                # A cost veto does not become an opening.
                target_ok, stop_ok = _assumed_entry_cost_and_stop_margin_screen(
                    quote, policy)
                if not target_ok or not stop_ok:
                    rejected += 1
                    return
                router, created = create_persistent_demo(
                    paper_directory=home, quote=quote, policy=policy,
                    universe_at_ms=scope.observed_at_ms,
                )
                return
            if quote.exchange_at_ms > created["reference_received_at_ms"]:
                router.process(quote)
                seen_after += 1
        outcome = supervise_public_tickers(
            session_factory=_public_bybit_session, book=book, budget=budget,
            on_quote=on_quote, on_session_reset=on_reset,
        )
        report = {
            "schema_version": SCHEMA,
            "status": (
                "persistent_paper_demo_opened" if created is not None
                else "no_eligible_price_reference"
            ),
            "market_lease_status": outcome.status,
            "market_failure_category": outcome.failure_category,
            "ticker_post_ack_frames": outcome.ticker_frames_accepted,
            "ticks_after_open": seen_after,
            "quotes_rejected": rejected,
            "paper_position_persisted": created is not None,
            "entry_signal_generated": False,
            "synthetic_filled_open_injected_explicitly": created is not None,
            "native_stop_verified": False,
            "real_orders_sent": False,
            "orders_sent": False,
            "approved_for_live_use": False,
        }
        if created is not None:
            report["paper_demo"] = created
        print(json.dumps(report, sort_keys=True, ensure_ascii=True))
        return 0 if created is not None else 2
    except (Exception,):
        # Do NOT claim no side effect after network/financial journal access.
        print(json.dumps({"status": "paper_demo_failed_closed",
                          "private_demo_journal_may_have_changed": True,
                          "network_may_have_been_attempted": True,
                          "orders_sent": False, "approved_for_live_use": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
