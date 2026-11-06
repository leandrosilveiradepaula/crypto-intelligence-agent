"""OPS36 synthetic-only adversarial multi-hour Binance WS regression tests."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
import json
import unittest

from crypto_intelligence_agent.j1_causal_source_decision import HOUR_MS as H, SourceEvidence
from crypto_intelligence_agent.j1_binance_ws_24h_replay import (
    BinanceWSClosedEpoch, audit_binance_ws_closed_24h_offline,
)
from crypto_intelligence_agent.market_data import DataValidationError, DataGapError
from test_j1_binance_top50_pit import DECISION, instrument, registry_for, catalog


def closed(symbol, close, q="250", offset=40):
    start = close - H
    p = {"e": "kline", "E": close + 25, "s": symbol, "k": {
        "t": start, "T": close - 1, "s": symbol, "i": "1h",
        "f": 20, "L": 22, "o": "99", "c": "101",
        "h": "102", "l": "98", "v": "2", "n": 3,
        "x": True, "q": q, "V": "1", "Q": "100", "B": "0",
    }}
    return SourceEvidence("binance_usdm", "ws", symbol, "1h", p,
                          close + offset, ack_verified=True)


def fixture(bases=("BTC", "ETH")):
    symbols = tuple(base + "USDT" for base in bases)
    registry = registry_for(bases, observed=DECISION - 26 * H)
    rows = [instrument(base) for base in bases]
    epochs = []
    for i in range(24):
        close = DECISION - (23 - i) * H
        cat = catalog(rows, requested=close-10000, received=close-9950)
        events = tuple(closed(symbol, close, q=str(250 + j*20),
                              offset=40+j*10) for j, symbol in enumerate(symbols))
        epochs.append(BinanceWSClosedEpoch(cat, events))
    return dict(epochs=tuple(epochs), symbols=symbols,
                registry=registry, decision_at_ms=DECISION)


def modify(p, index, *, rows=None, event=None, event_index=0, catalog_kwargs=None):
    a = list(p["epochs"])
    old = a[index]
    cat = old.catalog
    if rows is not None:
        cat = catalog(rows, requested=cat.requested_at_ms,
                      received=cat.received_at_ms)
    if catalog_kwargs:
        cat = replace(cat, **catalog_kwargs)
    evs = list(old.closes)
    if event is not None:
        evs[event_index] = event(evs[event_index])
    a[index] = BinanceWSClosedEpoch(cat, tuple(evs))
    p["epochs"] = tuple(a)


def edit_event(e, *, changes=None, **fields):
    p = deepcopy(e.payload)
    if changes:
        p["k"].update(changes)
    return replace(e, payload=p, **fields)


class BinanceWS24hOfflineTests(unittest.TestCase):
    def audit(self, p=None):
        return audit_binance_ws_closed_24h_offline(**(p or fixture()))

    def veto(self, p):
        with self.assertRaises((DataGapError, DataValidationError)):
            self.audit(p)

    def test_24x2_closed_hours_rank_and_zero_live_authority(self):
        r = self.audit()
        self.assertEqual((r.selected_contract_count, r.epochs_checked), (2, 24))
        self.assertEqual([x.symbol for x in r.ranked], ["ETHUSDT", "BTCUSDT"])
        self.assertEqual([x.turnover_24h_quote_usdt for x in r.ranked],
                         [Decimal(6480), Decimal(6000)])
        d = r.sanitized_report()
        self.assertEqual(d["quote_turnover_currency"], "USDT")
        self.assertEqual((d["network_requests"], d["storage_writes"]), (0, 0))
        for k in ("source_authenticated", "usdm_contract_verified",
                  "crypto_identity_verified_live", "marketwide_top50_verified",
                  "canonical_ohlcv_approved", "continuous_collector_authorized",
                  "financial_backtest_approved", "live_trading_authorized",
                  "orders_sent"):
            self.assertIs(d[k], False)
        self.assertNotIn("BTCUSDT", json.dumps(d))
        self.assertNotIn("ETHUSDT", json.dumps(d))
        self.assertEqual(r.sanitized_report(include_public_symbols=True)
                         ["reviewed_public_symbols_only"], ["ETHUSDT", "BTCUSDT"])
        with self.assertRaises(DataValidationError):
            r.sanitized_report(include_public_symbols=1)

    def test_deterministic_digest_is_causal_to_price_scale(self):
        a = self.audit()
        self.assertEqual(a.replay_digest_sha256, self.audit().replay_digest_sha256)
        p = fixture()
        modify(p, 6, event=lambda e: edit_event(e, changes={"c": "100"}))
        b = self.audit(p)
        self.assertNotEqual(a.replay_digest_sha256, b.replay_digest_sha256)
        self.assertEqual(a.rank_digest_sha256, b.rank_digest_sha256)

    def test_missing_or_duplicate_hours_fail(self):
        p = fixture()
        p["epochs"] = p["epochs"][:-1]
        self.veto(p)
        p = fixture()
        epochs = list(p["epochs"])
        epochs[8] = epochs[7]
        p["epochs"] = tuple(epochs)
        self.veto(p)
        p = fixture()
        p["epochs"] = p["epochs"][:5] + p["epochs"][6:] + (p["epochs"][5],)
        self.veto(p)

    def test_missing_duplicate_or_extra_per_member_hour_fail(self):
        for transform in (lambda es: es[:1],
                          lambda es: es + (es[0],),
                          lambda es: (es[0], es[0])):
            p = fixture()
            epochs = list(p["epochs"])
            epochs[9] = replace(epochs[9], closes=transform(epochs[9].closes))
            p["epochs"] = tuple(epochs)
            self.veto(p)

    def test_preack_open_future_venue_symbol_and_replay_veto(self):
        for changes in (dict(ack_verified=False),
                        dict(transport="rest"),
                        dict(venue="bybit_v5_linear"),
                        dict(interval="15m"),
                        dict(requested_at_ms=DECISION),
                        dict(symbol="ADAUSDT")):
            p = fixture()
            modify(p, 7, event=lambda e: replace(e, **changes))
            self.veto(p)
        for k in ({"x": False}, {"t": DECISION, "T": DECISION+H-1},
                  {"q": "NaN"}, {"q": "0"}, {"v": "0"},
                  {"h": "97"}, {"o": "0"}, {"V": "-1"}, {"n": True}):
            p = fixture()
            modify(p, 12, event=lambda e: edit_event(e, changes=k))
            self.veto(p)

    def test_catalog_must_precede_close_and_precede_event(self):
        p = fixture()
        old = p["epochs"][10].catalog
        modify(p, 10, catalog_kwargs={
            "requested_at_ms": old.requested_at_ms + 12000,
            "received_at_ms": old.received_at_ms + 12000})
        self.veto(p)
        p = fixture()
        old = p["epochs"][10].catalog
        modify(p, 10, catalog_kwargs={
            "requested_at_ms": old.requested_at_ms - 120000,
            "received_at_ms": old.received_at_ms - 120000})
        self.veto(p)
        p = fixture()
        modify(p, 3, catalog_kwargs={"payload_sha256": "0"*64})
        self.veto(p)

    def test_registry_forgery_future_or_stale_veto(self):
        p = fixture()
        p["registry"] = registry_for(("BTC",), observed=DECISION - 26 * H)
        self.veto(p)
        for observed in (DECISION + 100, DECISION - 9*86400000):
            p = fixture()
            p["registry"] = registry_for(("BTC", "ETH"), observed=observed)
            self.veto(p)

    def test_selected_contract_drift_veto(self):
        p = fixture()
        rows = [instrument("BTC"), instrument("ETH")]
        rows[0]["underlyingType"] = "STOCK"
        modify(p, 5, rows=rows)
        self.veto(p)
        p = fixture()
        rows = [instrument("BTC"), instrument("ETH")]
        rows[1]["underlyingSubType"] = ["changed"]
        modify(p, 5, rows=rows)
        self.veto(p)

    def test_unreviewed_catalog_candidate_is_not_promoted(self):
        p = fixture()
        modify(p, 15, rows=[instrument("BTC"), instrument("ETH"),
                            instrument("NEW")])
        self.assertFalse(self.audit(p).sanitized_report()["marketwide_top50_verified"])

    def test_unreviewed_selected_asset_veto(self):
        p = fixture()
        p["registry"] = registry_for(("BTC",), observed=DECISION - 26*H)
        self.veto(p)

    def test_52_synthetic_candidates_still_not_marketwide(self):
        p = fixture(tuple("C%02d" % i for i in range(52)))
        r = self.audit(p)
        self.assertEqual(r.selected_contract_count, 52)
        self.assertEqual(len(r.ranked), 50)
        self.assertFalse(r.sanitized_report()["marketwide_top50_verified"])

    def test_wrong_scope_or_open_clock_veto(self):
        p = fixture()
        p["symbols"] = ("BTCUSDT", "BTCUSDT")
        self.veto(p)
        p = fixture()
        p["decision_at_ms"] += 1
        self.veto(p)
        p = fixture()
        modify(p, 10, event=lambda e: edit_event(
            e, **{"received_at_ms": e.received_at_ms - H}))
        self.veto(p)
        p = fixture()
        modify(p, 10, event=lambda e: edit_event(
            e, **{"received_at_ms": e.received_at_ms + 40_000}))
        self.veto(p)


if __name__ == "__main__":
    unittest.main()
