"""D314: dynamic 50-member WS scope from D287 + V5 metadata fixture.

No GET, WebSocket session, systemd, real exchange, or orders in these tests.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import json
from tempfile import TemporaryDirectory
import unittest

from crypto_intelligence_agent.j1_n50_ws_dynamic_scope import (
    admit_dynamic_n50_ws_scope, capture_n50_dynamic_ws_metadata_once,
)
from crypto_intelligence_agent.bybit_public_j1_transport import (
    BoundedBybitPublicClient, instruments_url,
)
from crypto_intelligence_agent.bybit_ws_supervisor import _topic_batches
from crypto_intelligence_agent.bybit_closed_stream_cache import (
    SQLiteOfflineClosedStreamJournal, parse_offline_confirmed_kline,
)
from crypto_intelligence_agent.j1_n50_ws_hourly_attestation import (
    attest_n50_ws_hour_once,
)
from crypto_intelligence_agent.market_data import DataValidationError
from test_j1_n50_managed_cycle import T, SYMS, sealed
from test_j1_n50_ws_hourly_attestation_d313 import candle, DECISION

OBS = T + 180_000
SERVER = T + 170_000


def row(symbol: str) -> dict:
    return {
        "symbol":symbol, "baseCoin":symbol[:-4],
        "quoteCoin":"USDT","settleCoin":"USDT",
        "contractType":"LinearPerpetual", "status":"Trading",
        "symbolType":"","marketRegion":"","underlyingTicker":"",
        "tags":[],"isPreListing":False,"preListingInfo":None,
        "deliveryTime":"0","launchTime":str(T - 30*3_600_000),
        "leverageFilter":{"minLeverage":"1","maxLeverage":"50"},
        "priceFilter":{"tickSize":"0.01"},
        "lotSizeFilter":{"qtyStep":"0.001"},
    }


def page(symbols: tuple[str, ...], *, cursor="") -> dict:
    return {
        "retCode":0, "time":SERVER,
        "result":{
            "category":"linear", "nextPageCursor":cursor,
            "list":[row(s) for s in symbols],
        },
    }


class DynamicN50WSScopeTests(unittest.TestCase):
    def args(self):
        return dict(
            ranked_scope=sealed(T),
            instrument_pages=(page(tuple(SYMS)),),
            requested_cursors=(None,),
            page_received_at_ms=(OBS,),
            now_ms=OBS,
        )

    def build(self, **overrides):
        args=self.args()
        args.update(overrides)
        return admit_dynamic_n50_ws_scope(**args)

    def test_admits_all_fifty_dynamic_members_without_fixed_registry(self):
        approved=self.build()
        self.assertEqual(len(approved.ws_scope.contracts),50)
        self.assertEqual(set(m.symbol for m in approved.ws_scope.contracts),set(SYMS))
        self.assertEqual(approved.ranked_scope_sha256,sealed(T)["scope_digest_sha256"])
        self.assertEqual(approved.metadata_sha256,approved.ws_scope.registry_sha256)
        self.assertEqual(len(approved.metadata_sha256),64)
        self.assertEqual(len(_topic_batches(approved.ws_scope)),1)
        self.assertEqual(len(_topic_batches(approved.ws_scope)[0]),50)
        report=approved.sanitized_report()
        self.assertEqual(report["selected_contracts"],50)
        self.assertEqual(report["network_requests"],0)
        self.assertEqual(report["ws_connections_opened"],0)
        for label in ("catalog_source_authenticated","marketwide_top50_verified",
                      "crypto_identity_independently_verified","orders_sent",
                      "live_trading_authorized"):
            self.assertFalse(report[label])
        serialized=json.dumps(report)
        for symbol in SYMS:
            self.assertNotIn(symbol,serialized)
        self.assertNotIn("Binance",serialized)

    def test_two_valid_pages_are_concatenated_without_missing_or_duplication(self):
        symbols=tuple(SYMS)
        two=self.build(
            instrument_pages=(page(symbols[:25],cursor="ABC"),page(symbols[25:])),
            requested_cursors=(None,"ABC"),
            page_received_at_ms=(OBS,OBS+2000),
            now_ms=OBS+3000,
        )
        self.assertEqual(two.selected_contracts,50)
        self.assertEqual(len(_topic_batches(two.ws_scope)[0]),50)
        one=self.build()
        self.assertNotEqual(one.metadata_sha256,two.metadata_sha256)
        self.assertEqual(one.ranked_scope_sha256,two.ranked_scope_sha256)

    def test_dynamic_metadata_is_usable_with_existing_ws_journal_and_d313(self):
        approved=self.build()
        with TemporaryDirectory() as d:
            journal=SQLiteOfflineClosedStreamJournal.create(
                Path(d)/"dynamic-wsjournal.sqlite"
            )
            for symbol in SYMS:
                event=parse_offline_confirmed_kline(
                    candle(symbol), scope=approved.ws_scope,
                    received_at_ms=DECISION+2000,
                )
                self.assertEqual(journal.append(event),"appended")
            attested=attest_n50_ws_hour_once(
                ranked_scope=sealed(T), ws_scope=approved.ws_scope,
                journal=journal, decision_at_ms=DECISION,
                observed_at_ms=DECISION+4000,
            )
        self.assertEqual(attested["status"],
                         "ws_hour_50_observed_local_only_not_marketwide")
        self.assertEqual(attested["confirmed_contracts"],50)
        self.assertFalse(attested["published_rest_pit"])
        self.assertFalse(attested["source_authenticated"])

    def test_one_missing_metadata_for_selected_member_blocks_before_topics(self):
        args=self.args()
        args["instrument_pages"]=(page(tuple(SYMS[:-1])),)
        with self.assertRaises(DataValidationError):
            admit_dynamic_n50_ws_scope(**args)

    def test_pagination_duplication_or_forged_cursor_abstains(self):
        s=tuple(SYMS)
        good1=page(s[:25],cursor="PAGETWO")
        good2=page(s[25:])
        broken=[
            ((good1,good2), (None,"OTHER")),
            ((good1,good2), (None,None)),
            ((page(s),good2),(None,"PAGETWO")),
            ((page(s[:25],cursor=""),good2),(None,"PAGETWO")),
            ((page(s[:25],cursor="PAGETWO"),page(s[25:],cursor="PAGETHREE")),
             (None,"PAGETWO")),
            ((page(s),page(s)),(None,"")),
        ]
        for pages,cursors in broken:
            with self.subTest(cursors=cursors), self.assertRaises(DataValidationError):
                self.build(
                    instrument_pages=pages,
                    requested_cursors=cursors,
                    page_received_at_ms=(OBS,OBS+2000),
                    now_ms=OBS+3000,
                )

    def test_selected_tradfi_or_delisted_or_wrong_unit_fails_closed(self):
        for key,value in (
            ("symbolType","tradfi"),
            ("marketRegion","US"),
            ("underlyingTicker","AAPL"),
            ("tags",["stock"]),
            ("isPreListing",True),
            ("contractType","LinearFutures"),
            ("status","Settled"),
            ("settleCoin","USD"),
            ("baseCoin","OTHER"),
            ("deliveryTime","1"),
            ("launchTime",str(T+500_000)),
        ):
            doc=page(tuple(SYMS))
            doc["result"]["list"][1][key]=value
            with self.subTest(key=key,value=value), self.assertRaises(
                DataValidationError
            ):
                self.build(instrument_pages=(doc,))

    def test_bad_metadata_tick_leverage_or_quantity_blocks(self):
        for parent,field,value in (
            ("leverageFilter","minLeverage","100"),
            ("leverageFilter","maxLeverage","1e3"),
            ("leverageFilter","maxLeverage","NaN"),
            ("priceFilter","tickSize","0"),
            ("lotSizeFilter","qtyStep","-0.01"),
        ):
            doc=page(tuple(SYMS))
            doc["result"]["list"][0][parent][field]=value
            with self.subTest(parent=parent,field=field,value=value), self.assertRaises(
                DataValidationError
            ):
                self.build(instrument_pages=(doc,))

    def test_causal_metadata_clock_and_ranked_drift_deny(self):
        args=self.args()
        args["page_received_at_ms"]=(T+119_000,)
        with self.assertRaises(DataValidationError):
            admit_dynamic_n50_ws_scope(**args)
        for wrong in (T+180_000-31_000, T+180_000+1):
            doc=page(tuple(SYMS))
            doc["time"]=wrong
            with self.subTest(wrong=wrong), self.assertRaises(DataValidationError):
                self.build(instrument_pages=(doc,))
        old=sealed(T)
        old["scope_digest_sha256"]="0"*64
        with self.assertRaises(DataValidationError):
            self.build(ranked_scope=old)
        old=sealed(T)
        old["marketwide_top50_verified"]=True
        with self.assertRaises(DataValidationError):
            self.build(ranked_scope=old)

    def test_foreign_catalog_member_may_be_ignored_but_no_fake_top50(self):
        doc=page(tuple(SYMS))
        extra=row("EXTRAUSDT")
        extra["marketRegion"]="US"
        doc["result"]["list"].append(extra)
        scope=self.build(instrument_pages=(doc,))
        self.assertEqual(scope.selected_contracts,50)
        self.assertNotIn("EXTRAUSDT",_topic_batches(scope.ws_scope)[0])
        self.assertFalse(scope.sanitized_report()["marketwide_top50_verified"])

    def test_wrong_arg_types_fail_without_any_network(self):
        for name,value in (
            ("instrument_pages",[]),("requested_cursors",[]),
            ("page_received_at_ms",[]),("now_ms",True),
            ("instrument_pages",()),("requested_cursors",("no",)),
        ):
            with self.subTest(name=name), self.assertRaises(DataValidationError):
                self.build(**{name:value})


class OwnerDynamicMetadataCaptureTests(unittest.TestCase):
    def invoke(self, **kw):
        args = dict(
            ranked_scope=sealed(T),
            owner_ok=True,
            allow_public_network=True,
            confirm_region_and_personal_research=True,
            enable_n50_ws_metadata_capture=True,
            clock_ms=lambda: OBS,
        )
        args.update(kw)
        return capture_n50_dynamic_ws_metadata_once(**args)

    def test_missing_owner_or_optin_makes_zero_network_gets(self):
        calls = []
        client = BoundedBybitPublicClient(
            transport=lambda *_: calls.append("get") or
            b'{"retCode":10006,"retMsg":"secret"}',
        )
        for key, value in (
            ("owner_ok",False),("allow_public_network",False),
            ("confirm_region_and_personal_research",False),
            ("enable_n50_ws_metadata_capture",False),
        ):
            with self.subTest(key=key):
                result = self.invoke(client=client, **{key:value})
                self.assertEqual(result.requests_attempted,0)
                self.assertIsNone(result.admission)
                self.assertFalse(result.sanitized_report()["orders_sent"])
        self.assertEqual(calls,[])
        self.assertEqual(client.requests_attempted,0)

    def test_one_current_catalog_get_admits_50_dynamic_perps(self):
        calls=[]
        wire=json.dumps(page(tuple(SYMS))).encode("ascii")
        client=BoundedBybitPublicClient(
            transport=lambda url, size: calls.append(url) or wire,
        )
        result=self.invoke(client=client)
        self.assertEqual(result.status,
                         "dynamic_n50_ws_metadata_captured_research_only")
        self.assertEqual(result.requests_attempted,1)
        self.assertEqual(calls,[instruments_url()])
        self.assertEqual(len(_topic_batches(result.admission.ws_scope)[0]),50)
        report=result.sanitized_report()
        self.assertEqual(report["selected_contracts"],50)
        self.assertTrue(report["network_accessed"])
        self.assertFalse(report["source_authenticated"])
        self.assertFalse(report["marketwide_top50_verified"])
        self.assertFalse(report["orders_sent"])

    def test_two_pages_get_exact_pagination_and_zero_retries(self):
        first=page(tuple(SYMS[:25]),cursor="PAGETWO")
        second=page(tuple(SYMS[25:]))
        seen=[]
        docs=[first,second]
        def fetch(url,size):
            seen.append(url)
            return json.dumps(docs.pop(0)).encode("ascii")
        client=BoundedBybitPublicClient(transport=fetch)
        result=self.invoke(client=client)
        self.assertEqual(result.requests_attempted,2)
        self.assertEqual(len(seen),2)
        self.assertEqual(seen[0],instruments_url())
        self.assertEqual(seen[1],instruments_url(cursor="PAGETWO"))
        self.assertEqual(result.admission.selected_contracts,50)

    def test_retcode_10006_aborts_once_and_never_leaks_provider_body(self):
        urls=[]
        def wire(url,limit):
            urls.append(url)
            return b'{"retCode":10006,"retMsg":"SENSITIVE_MARKET_SYMBOL_TOKEN"}'
        client=BoundedBybitPublicClient(transport=wire)
        result=self.invoke(client=client)
        self.assertEqual(result.status,
                         "dynamic_n50_ws_metadata_abstained_no_retry")
        self.assertEqual(result.requests_attempted,1)
        self.assertEqual(result.failure_category,"provider_rate_limit_no_retry")
        self.assertIsNone(result.admission)
        self.assertEqual(len(urls),1)
        self.assertNotIn("SENSITIVE",json.dumps(result.sanitized_report()))
        self.assertFalse(result.sanitized_report()["live_trading_authorized"])

    def test_stale_ranked_scope_denies_before_issuing_catalog_get(self):
        calls=[]
        client=BoundedBybitPublicClient(
            transport=lambda *_: calls.append("get") or b'{"retCode":0}',
        )
        changed=sealed(T)
        changed["scope_digest_sha256"]="a"*64
        result=self.invoke(ranked_scope=changed,client=client)
        self.assertEqual(result.status,"untrusted_ranked_scope_no_get")
        self.assertEqual(result.requests_attempted,0)
        self.assertEqual(calls,[])

    def test_preconsumed_client_or_malformed_result_has_no_retry(self):
        client=BoundedBybitPublicClient(
            transport=lambda *_: json.dumps(page(tuple(SYMS))).encode("ascii"),
        )
        client.get(instruments_url())
        self.assertEqual(
            self.invoke(client=client).status,"client_budget_already_used",
        )
        broken=page(tuple(SYMS[:49]))
        calls=[]
        failing=BoundedBybitPublicClient(
            transport=lambda url,size: calls.append(url) or json.dumps(
                broken).encode("ascii"),
        )
        result=self.invoke(client=failing)
        self.assertEqual(result.status,
                         "dynamic_n50_ws_metadata_abstained_no_retry")
        self.assertEqual(result.requests_attempted,1)
        self.assertEqual(len(calls),1)
        self.assertIsNone(result.admission)


if __name__ == "__main__":
    unittest.main()
