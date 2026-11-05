"""OPS34 adversarial research fixtures: never connect to a market or storage.

Identity publishers below are *synthetic reserved example domains* and not
proof of any real asset; a pass must never set a marketwide/live flag.
"""
from __future__ import annotations

from copy import deepcopy
import json
import unittest

from crypto_intelligence_agent.crypto_asset_registry import (
    CryptoRegistrySnapshot, registry_sha256,
)
from crypto_intelligence_agent.j1_causal_source_decision import SourceEvidence
from crypto_intelligence_agent.j1_binance_top50_pit import (
    HOUR_MS as H, BinanceCatalogCapture, BinanceKlineCapture,
    bind_binance_ws_close_to_catalog_offline, content_sha256,
    rank_binance_reviewed_24h_offline,
)
from crypto_intelligence_agent.market_data import DataGapError, DataValidationError

DECISION = ((1793287659000 // H) + 1) * H
PREQUEST = DECISION + 65_000
PRECEIPT = PREQUEST + 10


def registry_for(bases=("BTC", "ETH"), *, observed=None):
    observed = PRECEIPT - 10_000 if observed is None else observed
    assets = []
    for base in bases:
        assets.append({
            "base": base, "canonical_id": "synthetic-" + base.lower(),
            "reviewed_by": "synthetic-reviewer", "reviewed_at_ms": observed - 1000,
            "evidence": [
                {"publisher": "research-one", "asset_ref": base.lower(),
                 "url": "https://identity.example.org/assets/" + base.lower(),
                 "observed_at_ms": observed - 2000},
                {"publisher": "research-two", "asset_ref": base.lower(),
                 "url": "https://identity.example.net/assets/" + base.lower(),
                 "observed_at_ms": observed - 3000},
            ],
        })
    data = {"schema_version": 1, "observed_at_ms": observed,
            "label": "synthetic-ops34", "usage_policy": "internal_research_only",
            "assets": assets}
    return CryptoRegistrySnapshot.from_manifest({**data, "sha256": registry_sha256(data)})


def instrument(base, *, onboard=None):
    sym = base + "USDT"
    return {"symbol": sym, "pair": sym, "baseAsset": base,
            "quoteAsset": "USDT", "marginAsset": "USDT",
            "contractType": "PERPETUAL", "status": "TRADING",
            "onboardDate": DECISION - 100*H if onboard is None else onboard,
            "deliveryDate": 4133404800000,
            "underlyingType": "COIN", "underlyingSubType": ["STORAGE"]}


def catalog(rows, *, requested=PREQUEST, received=PRECEIPT,
            endpoint="/fapi/v1/exchangeInfo", complete=True):
    payload = {"timezone": "UTC", "serverTime": received-1,
               "symbols": deepcopy(rows), "assets": []}
    return BinanceCatalogCapture(payload, requested, received,
        content_sha256(payload), endpoint, complete)


def kline_rows(turnover="12"):
    output = []
    for i in range(24):
        start = DECISION - (24-i)*H
        output.append([start, "1", "2", "0.5", "1.5", "10",
                       start+H-1, str(turnover), 4, "5", "6", "0"])
    return output


def kline(symbol, turnover="12", *, requested=DECISION+66_000,
          received=DECISION+66_010, endpoint="/fapi/v1/klines", venue="binance_usdm"):
    rows = kline_rows(turnover)
    return BinanceKlineCapture(symbol, rows, requested, received,
                               content_sha256(rows), endpoint, "1h", venue)


def scenario(bases=("BTC", "ETH"), *, extras=()):
    all_rows = [instrument(base) for base in bases] + list(extras)
    before = catalog(all_rows)
    klines = {base+"USDT": kline(base+"USDT", str(idx+12),
              requested=DECISION+66_000+100*idx,
              received=DECISION+66_020+100*idx)
              for idx, base in enumerate(bases)}
    after = catalog(all_rows, requested=DECISION+77_000,
                    received=DECISION+77_020)
    return dict(before=before, after=after,
                registry=registry_for(bases), klines=klines,
                decision_at_ms=DECISION)


def shadow(symbol="BTCUSDT", *, ack=True, closed=True, interval="1h"):
    st = DECISION - H
    data = {"e": "kline", "E": DECISION+68_000, "s": symbol,
            "k": {"t": st, "T": DECISION-1, "s": symbol, "i": interval,
                  "f": 5, "L": 8, "o": "1", "c": "1.5", "h": "2",
                  "l": "0.5", "v": "10", "n": 4, "x": closed,
                  "q": "12", "V": "5", "Q": "6", "B": "0"}}
    return SourceEvidence("binance_usdm", "ws", symbol, "1h",
                          data, DECISION+68_020, None, ack)


class BinanceCausalTop50ResearchTests(unittest.TestCase):
    def assertRejected(self, params, kind=DataValidationError):
        with self.assertRaises(kind):
            rank_binance_reviewed_24h_offline(**params)

    def test_two_member_exact_closed_quote_rank_not_marketwide(self):
        result = rank_binance_reviewed_24h_offline(**scenario())
        self.assertEqual([x.symbol for x in result.ranked], ["ETHUSDT", "BTCUSDT"])
        self.assertEqual([str(x.turnover_24h_usdt) for x in result.ranked], ["312", "288"])
        report = result.sanitized_report()
        self.assertEqual(report["quote_turnover_currency"], "USDT")
        self.assertEqual(report["reviewed_24h_windows_complete"], 2)
        self.assertFalse(report["rolling_ticker_used_for_rank"])
        for key in ("usdm_contract_verified", "marketwide_top50_verified",
                    "canonical_ohlcv_approved", "source_authenticated",
                    "continuous_collector_authorized", "orders_sent"):
            self.assertFalse(report[key])
        public_dump = json.dumps(report)
        self.assertNotIn("BTCUSDT", public_dump)
        self.assertNotIn('"312"', public_dump)
        self.assertEqual(result.sanitized_report(include_public_symbols=True)
                         ["reviewed_public_symbols_only"], ["ETHUSDT", "BTCUSDT"])
        with self.assertRaises(DataValidationError):
            result.sanitized_report(include_public_symbols=1)

    def test_deterministic_tie_order_and_integrity_digest(self):
        p = scenario()
        p["klines"]["ETHUSDT"] = kline("ETHUSDT", "12", requested=DECISION+66_100,
                                         received=DECISION+66_120)
        x = rank_binance_reviewed_24h_offline(**p)
        self.assertEqual([i.symbol for i in x.ranked], ["BTCUSDT", "ETHUSDT"])
        self.assertEqual(x.sanitized_report()["reviewed_rank_digest_sha256"],
                         rank_binance_reviewed_24h_offline(**p)
                         .sanitized_report()["reviewed_rank_digest_sha256"])

    def test_52_synthetic_fixtures_remain_not_marketwide(self):
        bases = tuple(f"C{i:02}" for i in range(52))
        x = rank_binance_reviewed_24h_offline(**scenario(bases))
        self.assertEqual(len(x.ranked), 50)
        self.assertEqual(x.reviewed_eligible, 52)
        self.assertFalse(x.sanitized_report()["marketwide_top50_verified"])
        self.assertEqual(x.ranked[0].symbol, "C51USDT")

    def test_rolling_ticker_cannot_be_substituted_for_24_bars(self):
        p = scenario()
        p["klines"]["ETHUSDT"] = {"symbol":"ETHUSDT", "quoteVolume":"999999"}
        self.assertRejected(p)

    def test_every_eligible_reviewed_member_needs_all_24_hours(self):
        p = scenario()
        p["klines"].pop("ETHUSDT")
        self.assertRejected(p, DataGapError)
        p = scenario()
        p["klines"]["ETHUSDT"].payload.pop()
        self.assertRejected(p, DataValidationError)  # changed bytes, no silent edits
        p["klines"]["ETHUSDT"] = kline("ETHUSDT")
        p["klines"]["ETHUSDT"].payload.pop()
        self.assertRejected(p)

    def test_one_missing_hour_duplicate_out_of_order_and_future_bar(self):
        for mutation in (lambda z: z.pop(8),
                         lambda z: z.__setitem__(4, deepcopy(z[3])),
                         lambda z: z.reverse(),
                         lambda z: z[-1].__setitem__(0, DECISION)):
            with self.subTest(mutation=mutation):
                p = scenario()
                sample = p["klines"]["BTCUSDT"]
                mutation(sample.payload)
                p["klines"]["BTCUSDT"] = BinanceKlineCapture(
                    sample.symbol, sample.payload, sample.requested_at_ms,
                    sample.received_at_ms, content_sha256(sample.payload))
                self.assertRejected(p, DataGapError)

    def test_base_volume_cannot_be_passed_as_quote_turnover(self):
        p = scenario()
        sample = p["klines"]["ETHUSDT"]
        for row in sample.payload:
            row[7] = "5"   # would swap quote to below taker quote 6
        p["klines"]["ETHUSDT"] = BinanceKlineCapture(
            sample.symbol, sample.payload, sample.requested_at_ms,
            sample.received_at_ms, content_sha256(sample.payload))
        self.assertRejected(p)

    def test_invalid_decimal_or_ohlc_rejected(self):
        for idx, value in ((1,"NaN"), (2,"0.3"), (5,"-1"), (7,"Infinity")):
            with self.subTest(idx=idx):
                p=scenario()
                k=p["klines"]["BTCUSDT"]
                k.payload[0][idx]=value
                p["klines"]["BTCUSDT"]=BinanceKlineCapture(
                    k.symbol, k.payload, k.requested_at_ms, k.received_at_ms,
                    content_sha256(k.payload))
                self.assertRejected(p)

    def test_rest_endpoint_venue_and_interval_cannot_be_swapped(self):
        for change in ({"endpoint":"/dapi/v1/klines"},
                       {"venue":"binance_coinm"}, {"interval":"15m"},
                       {"symbol":"ADAUSDT"}):
            with self.subTest(change=change):
                p=scenario()
                k=p["klines"]["BTCUSDT"]
                values={**k.__dict__, **change}
                p["klines"]["BTCUSDT"]=BinanceKlineCapture(**values)
                self.assertRejected(p)

    def test_overlapping_capture_clock_is_not_sequential(self):
        p = scenario()
        p["klines"]["ETHUSDT"] = kline("ETHUSDT", "13",
            requested=DECISION+66_001, received=DECISION+66_040)
        self.assertRejected(p)

    def test_rest_after_close_settlement_and_no_future_query(self):
        p=scenario()
        p["klines"]["BTCUSDT"] = kline("BTCUSDT", requested=DECISION+1000,
                                        received=DECISION+1020)
        self.assertRejected(p)
        p=scenario()
        p["klines"]["BTCUSDT"] = kline("BTCUSDT", requested=DECISION+66_000,
                                        received=DECISION+77_500)
        self.assertRejected(p)

    def test_catalog_requires_exchange_info_not_coin_m_or_claimed_incomplete(self):
        p=scenario()
        p["before"] = catalog(p["before"].payload["symbols"], endpoint="/dapi/v1/exchangeInfo")
        self.assertRejected(p)
        p=scenario()
        p["before"] = catalog(p["before"].payload["symbols"], complete=False)
        self.assertRejected(p)

    def test_catalog_rejects_missing_fields_or_duplicate_symbols(self):
        p=scenario()
        p["after"] = catalog(p["after"].payload["symbols"] +
                             [p["after"].payload["symbols"][0]],
                             requested=DECISION+77_000, received=DECISION+77_020)
        self.assertRejected(p)
        p=scenario()
        rows=deepcopy(p["after"].payload["symbols"])
        rows[0].pop("marginAsset")
        p["after"]=catalog(rows, requested=DECISION+77_000,
                           received=DECISION+77_020)
        self.assertRejected(p)

    def test_metadata_drift_and_registry_change_fail_closed(self):
        p=scenario()
        rows=deepcopy(p["after"].payload["symbols"])
        rows[0]["status"]="BREAK"
        p["after"]=catalog(rows, requested=DECISION+77_000,
                           received=DECISION+77_020)
        self.assertRejected(p)
        p=scenario()
        p["registry"] = registry_for(("BTC", "ETH"), observed=DECISION+90_000)
        self.assertRejected(p)

    def test_registry_forgery_not_accepted(self):
        p=scenario()
        from dataclasses import replace
        p["registry"]=replace(p["registry"], sha256_digest="0"*64)
        self.assertRejected(p)

    def test_unknown_candidate_never_added_and_counted_as_review_gap(self):
        p=scenario(extras=(instrument("UNREVIEWED"),))
        x=rank_binance_reviewed_24h_offline(**p)
        self.assertEqual(x.plausible_unreviewed, 1)
        self.assertEqual(len(x.ranked), 2)
        self.assertFalse(x.sanitized_report()["marketwide_top50_verified"])

    def test_tradfi_cm_usdc_expiring_unlisted_and_margin_different_excluded(self):
        excluded=[]
        for base, change in (("STOCK",{"underlyingType":"STOCK"}),
                             ("CMCOIN",{"marginAsset":"BTC"}),
                             ("USDCBAD",{"quoteAsset":"USDC"}),
                             ("EXPIRY",{"contractType":"CURRENT_QUARTER"}),
                             ("DELIST",{"status":"BREAK"})):
            row=instrument(base)
            row.update(change)
            excluded.append(row)
        p=scenario(extras=tuple(excluded))
        x=rank_binance_reviewed_24h_offline(**p)
        self.assertEqual(x.plausible_unreviewed, 0)

    def test_new_listing_without_24h_is_excluded_not_zero_padded(self):
        p=scenario()
        for key in ("before", "after"):
            cap=p[key]
            rows=deepcopy(cap.payload["symbols"])
            rows[1]["onboardDate"]=DECISION-5*H
            p[key]=catalog(rows, requested=cap.requested_at_ms,
                           received=cap.received_at_ms)
        p["klines"].pop("ETHUSDT")
        x=rank_binance_reviewed_24h_offline(**p)
        self.assertEqual(x.reviewed_new_listings, 1)
        self.assertEqual([x.symbol for x in x.ranked], ["BTCUSDT"])

    def test_missing_24hour_history_for_all_abstains(self):
        p=scenario(("BTC",))
        for key in ("before", "after"):
            cap=p[key]
            rows=deepcopy(cap.payload["symbols"])
            rows[0]["onboardDate"]=DECISION-3*H
            p[key]=catalog(rows, requested=cap.requested_at_ms,
                           received=cap.received_at_ms)
        p["klines"].clear()
        self.assertRejected(p, DataGapError)

    def test_unknown_or_future_registry_does_not_upgrade_census(self):
        p=scenario()
        p["registry"]=registry_for(("BTC",), observed=PRECEIPT-10_000)
        p["klines"].pop("ETHUSDT")
        x=rank_binance_reviewed_24h_offline(**p)
        self.assertEqual(x.plausible_unreviewed, 1)
        self.assertEqual(len(x.ranked), 1)
        self.assertFalse(x.sanitized_report()["crypto_identity_independently_authenticated"])

    def test_bad_capture_digests_and_ignored_server_time(self):
        p=scenario()
        k=p["klines"]["BTCUSDT"]
        p["klines"]["BTCUSDT"]=BinanceKlineCapture(
            k.symbol, k.payload, k.requested_at_ms, k.received_at_ms, "0"*64)
        self.assertRejected(p)
        p=scenario()
        p["before"].payload["serverTime"]=PRECEIPT+80_000
        p["before"]=BinanceCatalogCapture(
            p["before"].payload, p["before"].requested_at_ms,
            p["before"].received_at_ms, content_sha256(p["before"].payload),
            caller_declares_full_response=True)
        # exchangeInfo.serverTime is documented as unfit for timing.
        self.assertFalse(rank_binance_reviewed_24h_offline(**p)
                         .sanitized_report()["catalog_server_time_used_for_pit"])
        p["before"].payload["serverTime"]="garbage"
        self.assertRejected(p)

    def test_catalog_clock_and_utc_decision(self):
        p=scenario()
        p["decision_at_ms"]+=1
        self.assertRejected(p)
        p=scenario()
        p["after"] = catalog(p["after"].payload["symbols"],
                             requested=DECISION+H, received=DECISION+H+10)
        self.assertRejected(p)
        p=scenario()
        p["before"] = catalog(p["before"].payload["symbols"],
                              requested=DECISION-1000, received=DECISION-980)
        self.assertRejected(p)

    def test_ws_x_true_bind_is_still_research_only(self):
        p=scenario()
        x=bind_binance_ws_close_to_catalog_offline(
            evidence=shadow(), catalog=p["before"], registry=p["registry"])
        self.assertEqual(x["status"], "binance_causal_metadata_link_research_only")
        self.assertTrue(x["metadata_eligible_candidate"])
        self.assertFalse(x["usdm_contract_verified"])
        self.assertFalse(x["canonical_ohlcv_approved"])

    def test_ws_open_preack_wrong_symbol_future_or_wrong_interval_abstains(self):
        p=scenario()
        candidates=(shadow(ack=False), shadow(closed=False),
                    shadow("ADAUSDT"), shadow(interval="15m"))
        for evidence in candidates:
            with self.subTest(candidate=evidence):
                x=bind_binance_ws_close_to_catalog_offline(
                    evidence=evidence, catalog=p["before"], registry=p["registry"])
                self.assertEqual(x["status"], "binance_causal_contract_abstain")

    def test_aggregate_ops33_report_cannot_be_backfilled_as_candle(self):
        p=scenario()
        x=bind_binance_ws_close_to_catalog_offline(
            evidence={"unique_closed":2, "frames_seen":178},
            catalog=p["before"], registry=p["registry"])
        self.assertEqual(x["status"], "binance_causal_contract_abstain")

    def test_snapshot_digest_rejects_non_json_values(self):
        with self.assertRaises(DataValidationError):
            content_sha256({"turnover": float("nan")})
        with self.assertRaises(DataValidationError):
            content_sha256({"bad":object()})


if __name__ == "__main__":
    unittest.main()
