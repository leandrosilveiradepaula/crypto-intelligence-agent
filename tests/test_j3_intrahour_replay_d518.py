"""Offline fixtures for observed 5m exit refinement, never real acquisition."""
from dataclasses import replace
from decimal import Decimal
from hashlib import sha256
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_public_j1_transport import (
    BoundedBybitPublicClient, J1BybitCaptureError, research_five_minute_url,
)
from crypto_intelligence_agent.j2_rest_n50_history_d461 import _canonical
from crypto_intelligence_agent.j3_intrahour_replay_d518 import (
    SCHEMA, SOURCE, FIVE_MS, capture_plan, decode_intrahour,
    index_intrahour, refine_hourly_path,
)
from crypto_intelligence_agent.market_data import DataValidationError, DataGapError
from test_j3_archived_strategy_comparison_d512 import (
    archive, compare, END, HOUR, known_hypothesis,
)
from test_j3_observed_exit_scenarios_d517 import MARGIN, POLICY, bar, run

D=Decimal


def subdivide(h, *, target_first=True):
    result=[]
    for i in range(12):
        low=h.low if i==(8 if target_first else 1) else min(h.open,h.close)
        high=h.high if i==(1 if target_first else 8) else max(h.open,h.close)
        t=h.open_time_ms+i*FIVE_MS
        result.append(replace(h, interval="5m", open_time_ms=t,
                              close_time_ms=t+FIVE_MS-1, high=high, low=low))
    return tuple(result)


def envelope(h0, h1):
    hourly=dict(h1.series)["ALT00USDT"][-1]
    candles=subdivide(hourly)
    rows=[[str(c.open_time_ms),str(c.open),str(c.high),str(c.low),str(c.close),
           str(c.base_volume),str(c.quote_volume)] for c in reversed(candles)]
    received=END+2*HOUR
    p={"source":SOURCE,"created_at_ms":received,"series":{"ALT00USDT":{
        "anchor_digest":h0.digest_sha256,"anchor_end_ms":h0.window_end_ms,
        "anchor_captured_at_ms":h0.captured_at_ms,"retrieved_at_ms":received,
        "start_ms":hourly.open_time_ms,"end_ms":hourly.close_time_ms+1,"rows":rows}}}
    return _canonical({"schema":SCHEMA,"payload":p,
                       "sha256":sha256(_canonical(p)).hexdigest()})


class IntrahourReplayTests(unittest.TestCase):
    def test_explicit_transport_opt_in_and_closed_window(self):
        url=research_five_minute_url("BTCUSDT",END,END+36*HOUR)
        self.assertIn("interval=5",url)
        self.assertTrue(url.endswith("limit=432"))
        wire=lambda *args:b'{"retCode":0,"result":{}}'
        default=BoundedBybitPublicClient(transport=wire)
        with self.assertRaises(J1BybitCaptureError):
            default.get(url)
        self.assertEqual(default.requests_attempted,0)
        client=BoundedBybitPublicClient(transport=wire,allow_five_minute_research=True)
        self.assertEqual(client.get(url)[1]["retCode"],0)
        for invalid in (url+"&api_key=x",url.replace("limit=432","limit=433"),
                        url.replace("interval=5","interval=15")):
            with self.assertRaises(J1BybitCaptureError):
                client.get(invalid)
        with self.assertRaises(J1BybitCaptureError):
            research_five_minute_url("BTCUSDT",END,END+37*HOUR)
        self.assertEqual(client.requests_attempted,1)

    def test_original_membership_plan_and_envelope_identity(self):
        h0,h1=archive(0),archive(1)
        plan=capture_plan((h0,h1))
        self.assertEqual(len(plan),49)
        self.assertEqual(plan["ALT00USDT"],(h0,END,END+HOUR))
        self.assertNotIn("BTCUSDT",plan)
        self.assertNotIn("ALT00USDT",capture_plan((h0,archive(1,drop=True))))
        raw=envelope(h0,h1)
        supplement=decode_intrahour(raw,now_ms=END+10*HOUR)
        index,rejected=index_intrahour((h0,h1),supplement,now_ms=END+10*HOUR)
        self.assertEqual(rejected,0)
        self.assertEqual(len(index["ALT00USDT"]),12)
        self.assertEqual(len(refine_hourly_path((dict(h1.series)["ALT00USDT"][-1],),index)),12)
        self.assertEqual(index_intrahour((h1,),supplement,now_ms=END+10*HOUR),({},1))
        with self.assertRaises(DataValidationError):
            decode_intrahour(raw,now_ms=END+HOUR)
        with self.assertRaises((DataValidationError,DataGapError)):
            decode_intrahour(raw.replace(b'"schema":',b'"other":',1),now_ms=END+10*HOUR)

    def test_subdivision_resolves_order_between_distinct_bars(self):
        h=bar(0)
        original=run((h,))
        self.assertNotEqual(original["adverse_first"],original["favorable_first"])
        for target_first in (True,False):
            small=subdivide(h,target_first=target_first)
            idx={h.symbol:{c.open_time_ms:c for c in small}}
            self.assertEqual(refine_hourly_path((h,),idx),small)
            actual=run(small)
            self.assertEqual(actual["adverse_first"],actual["favorable_first"])
            self.assertEqual(actual["adverse_first"],original[
                "favorable_first" if target_first else "adverse_first"])
            del idx[h.symbol][h.open_time_ms]
            self.assertIsNone(refine_hourly_path((h,),idx))
        broken=tuple(replace(c,high=h.high+D(1)) if i==1 else c
                     for i,c in enumerate(subdivide(h)))
        self.assertIsNone(refine_hourly_path((h,),{h.symbol:{c.open_time_ms:c for c in broken}}))

    @patch("crypto_intelligence_agent.j3_archived_strategy_comparison_d512.evaluate_observed_bybit_research",
           side_effect=known_hypothesis)
    def test_replay_compares_identical_covered_sample_without_new_entries(self, evaluator):
        h0,h1=archive(0),archive(1)
        s=decode_intrahour(envelope(h0,h1),now_ms=END+10*HOUR)
        opts=dict(replay_horizon_hours=1,replay_margin=MARGIN,exit_policy=POLICY)
        hourly=compare((h0,h1),**opts)
        refined=compare((h0,h1),intrahour_supplement=s,**opts)
        self.assertEqual(hourly["results"],refined["results"])
        e=refined["exit_replay"]
        self.assertEqual(e["interval"],"5m")
        self.assertEqual(e["results"]["breakout"]["candidate_count"],49)
        self.assertEqual(e["results"]["breakout"]["complete_path_count"],1)
        self.assertEqual(e["matched_hourly_reference"]["breakout"]["complete_path_count"],1)
        self.assertEqual(e["results"]["ema_cross"]["complete_path_count"],1)
        self.assertFalse(e["intrabar_path_verified"])
        self.assertFalse(e["orders_sent"])
        self.assertFalse(e["liquidation_verified"])


if __name__=="__main__":
    unittest.main()
