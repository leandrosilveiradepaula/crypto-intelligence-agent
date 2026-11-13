"""J1/D332: synthetic one-character USDT base must not halt N50 closed WS.

Reproduces the cross-parser shape mismatch; no claim about the real private
symbol behind D331's ws_scope_member_invalid, no market GET or orders.
"""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_closed_stream_cache import (
    SQLiteOfflineClosedStreamJournal, parse_offline_confirmed_kline,
)
from crypto_intelligence_agent.bybit_linear_candle_research import (
    stage_bybit_linear_kline,
)
from crypto_intelligence_agent.bybit_ws_supervisor import (
    WSRunBudget, _safe_ws_failure_class, supervise_ws_research,
)
from crypto_intelligence_agent.market_data import DataValidationError
from test_j1_n50_ws_hourly_attestation_d313 import (
    DECISION, HOUR_MS, T, reviewed_scope,
)
from test_j1_n50_ws_owner_hour_d315 import FakeSession, FakeTime
from test_j1_n50_ws_server_bounded_trade_clock_d329 import postclose

ONE = "AUSDT"  # synthetic member; NOT a claim that the venue lists this.
LONG = "A" * 31 + "USDT"


def short_base_scope():
    original = reviewed_scope()
    contracts = list(original.contracts)
    contracts[42] = replace(contracts[42], symbol=ONE, base_coin="A")
    return replace(original, contracts=tuple(contracts))


class D332SingleBaseUSDTTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.journal = SQLiteOfflineClosedStreamJournal.create(
            Path(self.temp.name) / "ws-confirmed.sqlite")
        self.scope = short_base_scope()
        self.members = tuple(m.symbol for m in self.scope.contracts)
        self.assertEqual(len(set(self.members)), 50)
        self.assertEqual(len(self.members), 50)

    def audit(self):
        return self.journal.audit(
            scope=self.scope, decision_at_ms=DECISION,
            as_of_ms=DECISION + 4000,
            hour_evidence_symbols=tuple(sorted(self.members)),
        )

    def test_single_letter_base_is_allowed_only_with_valid_linear_ohlcv(self):
        msg = postclose(ONE)
        event = parse_offline_confirmed_kline(
            msg, scope=self.scope, received_at_ms=DECISION + 2000,
            allow_server_bounded_trade_clock=True)
        self.assertEqual(event.symbol, ONE)
        self.assertEqual(self.journal.append(event), "appended")
        self.assertEqual(self.audit().hour_evidence_confirmed, 1)
        assert not self.audit().hour_evidence_sha256

    def test_rest_shaped_parser_matches_existing_auto_usdt_contract_min(self):
        item = self.scope.contracts[42]
        payload = {
            "retCode": 0,
            "result": {
                "category": "linear", "symbol": ONE,
                "list": [[str(T), "10", "12", "9", "11", "1.5", "16.5"]],
            },
        }
        args = dict(
            symbol=ONE, quote_currency="USDT",
            contract_type="LinearPerpetual", contract_status="Trading",
            contract_observed_at_ms=item.observed_at_ms,
            observed_at_ms=DECISION + 2000,
            max_contract_age_ms=48 * HOUR_MS,
            interval="1h",
            start_open_ms=T, end_open_ms=DECISION,
            close_safety_ms=0, max_candles=1,
        )
        good = stage_bybit_linear_kline(payload, **args)
        self.assertEqual(len(good.candles), 1)
        for bad in (
            dict(args, quote_currency="USDC"),
            dict(args, contract_status="PreLaunch"),
            dict(args, contract_type="LinearFutures"),
            dict(args, symbol="aUSDT"),
            dict(args, symbol=LONG),
        ):
            with self.subTest(bad=bad["symbol"], status=bad["contract_status"]):
                with self.assertRaises(DataValidationError):
                    stage_bybit_linear_kline(payload, **bad)

    def test_longest_auto_eligible_base_matches_immutable_journal_bounds(self):
        # D332 CI revealed that the journal was even narrower than the WS
        # converter (legacy 2..24), so verify the N50 auto-scope max 28.
        base = "Q" * 28
        symbol = base + "USDT"
        contracts = list(self.scope.contracts)
        contracts[42] = replace(contracts[42], symbol=symbol, base_coin=base)
        scope = replace(self.scope, contracts=tuple(contracts))
        event = parse_offline_confirmed_kline(
            postclose(symbol), scope=scope,
            received_at_ms=DECISION + 2000,
            allow_server_bounded_trade_clock=True,
        )
        self.assertEqual(self.journal.append(event), "appended")
        audited = self.journal.audit(
            scope=scope, decision_at_ms=DECISION,
            as_of_ms=DECISION + 4000,
            hour_evidence_symbols=tuple(sorted(m.symbol for m in scope.contracts)),
        )
        self.assertEqual(audited.hour_evidence_confirmed, 1)

    def test_full_50_cohort_after_member_43_closes_without_exemption(self):
        clock = FakeTime()
        session = FakeSession(
            clock, market=tuple(postclose(symbol) for symbol in self.members)
        )
        with patch("socket.create_connection",
                   side_effect=AssertionError("no real WS")), patch(
            "crypto_intelligence_agent.bybit_public_j1_transport.BoundedBybitPublicClient.get",
            side_effect=AssertionError("no REST GET")
        ):
            result = supervise_ws_research(
                session_factory=lambda: session,
                scope=self.scope, journal=self.journal,
                budget=WSRunBudget(max_sessions=1, max_frames=120, max_seconds=65),
                clock=clock.clock, wall_ms=clock.wall_ms, sleeper=clock.sleep,
                allow_temporal_discard=True,
                allow_server_bounded_trade_clock=True,
            )
        self.assertEqual(result.status, "ws_budget_ended_research_only")
        self.assertIsNone(result.failure_category)
        self.assertEqual(result.subscriptions_acknowledged, 1)
        self.assertEqual(result.closed_events_appended, 50)
        self.assertEqual(result.accepted_postclose_trade_clock, 50)
        self.assertEqual(self.audit().persisted_rows, 50)
        self.assertEqual(self.audit().hour_evidence_confirmed, 50)
        self.assertFalse(result.sanitized_report()["orders_sent"])
        self.assertNotIn(ONE, json.dumps(result.sanitized_report()))
        self.assertTrue(session.closed)

    def test_scope_and_temporal_guards_remain_fail_closed(self):
        wrong = postclose("ZUSDT")  # not a member
        with self.assertRaises(DataValidationError):
            parse_offline_confirmed_kline(
                wrong, scope=self.scope, received_at_ms=DECISION + 2000,
                allow_server_bounded_trade_clock=True)
        for changed in (
            dict(confirm=False),
            dict(start=T+1),
            dict(high="1"),
        ):
            msg = postclose(ONE)
            msg["data"][0].update(changed)
            with self.subTest(changed=changed), self.assertRaises(DataValidationError):
                parse_offline_confirmed_kline(
                    msg, scope=self.scope,
                    received_at_ms=DECISION + 2000,
                    allow_server_bounded_trade_clock=True)
        self.assertEqual(self.audit().persisted_rows, 0)

    def test_symbol_format_and_scope_membership_have_distinct_safe_categories(self):
        self.assertEqual(
            _safe_ws_failure_class(DataValidationError(
                "Bybit symbol and quote currency mismatch")),
            "ws_closed_symbol_format_invalid")
        self.assertEqual(
            _safe_ws_failure_class(DataValidationError(
                "WS symbol not present in reviewed scan")),
            "ws_scope_member_invalid")
        self.assertEqual(
            _safe_ws_failure_class(DataValidationError(
                "Bybit symbol and quote currency mismatch: /secret/AUSDT")),
            "invalid_or_gapped_market_data")


if __name__ == "__main__":
    unittest.main()
