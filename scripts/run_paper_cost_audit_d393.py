"""D393 executable demonstration: conditional costs of ledger-recorded PAPER fills.

Uses D392's synthetic fixture builders. Nothing is downloaded, connected,
submitted to a venue, or installed. Does not estimate missing fills.
"""
from __future__ import annotations

import argparse
from decimal import Decimal as D
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from crypto_intelligence_agent.bybit_public_ticker_state_d385 import BybitPublicTickerBook
from crypto_intelligence_agent.paper_closed_cost_audit_d393 import (
    PaperDeclaredFillReference, audit_closed_paper_costs,
)
from crypto_intelligence_agent.paper_intrahour_proof_d392 import (
    HOUR_START_MS as T, MINUTE_MS as M, POSITION_ID,
    _new_position, _route, _tick, _explicit_fill,
)
from crypto_intelligence_agent.paper_position_reservations import SQLitePaperPositionJournal
from crypto_intelligence_agent.synthetic_cost_scenarios import SyntheticFundingEvent
from crypto_intelligence_agent.synthetic_order_lifecycle import (
    PaperOrderEvent, PaperOrderEventKind,
)
from crypto_intelligence_agent.synthetic_partial_costed_replay import SyntheticPartialCostRates


def run_demo(*, scenario: str) -> dict:
    if scenario not in ("closed", "unknown"):
        raise ValueError("D393 scenario must be closed or unknown")
    rates = SyntheticPartialCostRates(
        entry_fee_bps=D(10), exit_fee_bps=D(10),
        entry_adverse_slippage_bps=D(5),
        exit_adverse_slippage_bps=D(5),
    )
    with TemporaryDirectory(prefix="cia-j3-cost-audit-d393-") as temp:
        db = Path(temp) / "paper.sqlite"
        store = _new_position(db, short=False)
        router = _route(db, short=False)
        book = BybitPublicTickerBook(
            ranked_symbols=("BTCUSDT",), universe_at_ms=T + M,
        )
        book.begin_acknowledged_session()
        first = router.process(_tick(
            book, minute=12, cs=1, kind="snapshot",
            mark="100.5", bid="101", ask="101.02",
        ))
        if first is None or first.created_intent_id is None:
            raise RuntimeError("D393 failed to reserve first PAPER partial")
        refs = []
        if scenario == "unknown":
            at = T + 12 * M + 1
            store.append_exit_events(
                POSITION_ID, first.created_intent_id,
                (PaperOrderEvent(
                    "fixture_d393_cli_unknown", PaperOrderEventKind.UNKNOWN, at,
                ),), as_of_ms=at,
            )
            funding = ()
        else:
            _explicit_fill(
                store, minute=12, intent_id=first.created_intent_id,
                event_id="fixture_d393_cli_first", units=D(30),
            )
            refs.append(PaperDeclaredFillReference(
                first.created_intent_id, "fixture_d393_cli_first",
                T + 12 * M + 1, D(101),
            ))
            second = router.process(_tick(
                book, minute=19, cs=2, kind="delta",
                mark="102.5", bid="103", ask="103.02",
            ))
            if second is None or second.created_intent_id is None:
                raise RuntimeError("D393 failed to reserve second PAPER partial")
            _explicit_fill(
                store, minute=19, intent_id=second.created_intent_id,
                event_id="fixture_d393_cli_second", units=D(20),
            )
            refs.append(PaperDeclaredFillReference(
                second.created_intent_id, "fixture_d393_cli_second",
                T + 19 * M + 1, D(103),
            ))
            book.mark_disconnected()
            book.begin_acknowledged_session()
            router = _route(db, short=False)
            third = router.process(_tick(
                book, minute=27, cs=1, kind="snapshot",
                mark="98", bid="98", ask="98.02",
            ))
            if third is None or third.created_intent_id is None:
                raise RuntimeError("D393 failed to reserve PAPER stop")
            _explicit_fill(
                store, minute=27, intent_id=third.created_intent_id,
                event_id="fixture_d393_cli_stop", units=D(50),
            )
            refs.append(PaperDeclaredFillReference(
                third.created_intent_id, "fixture_d393_cli_stop",
                T + 27 * M + 1, D(98),
            ))
            funding = (SyntheticFundingEvent(
                "fixture_funding_d393_cli", T + 13 * M,
                D(7000), D(2),
            ),)
        x = audit_closed_paper_costs(
            db, POSITION_ID,
            entry_reference_price_quote=D(100),
            fill_references=tuple(refs),
            cost_rates=rates,
            funding_events=funding,
        )
        return x.sanitized_report()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only conditional cost audit of synthetic AUTO4 position."
    )
    parser.add_argument("--scenario", choices=("closed", "unknown"),
                        default="closed")
    args = parser.parse_args(argv)
    print(json.dumps(run_demo(scenario=args.scenario),
                     sort_keys=True, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
