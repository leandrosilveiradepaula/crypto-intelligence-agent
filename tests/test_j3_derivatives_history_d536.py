"""D536 deterministic derivatives history, resume, and conditional funding costs."""
from decimal import Decimal as D
import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import parse_qs,urlsplit
from unittest.mock import patch

from crypto_intelligence_agent.bybit_public_j1_transport import (
    BoundedBybitPublicClient,J1BybitCaptureError,research_funding_url,research_mark_url,
)
from crypto_intelligence_agent.j3_derivatives_history_d536 import (
    collect_derivatives,normalize_page,FundingExposure,funding_cost_bounds,trade_coverage,
)
from crypto_intelligence_agent.j3_long_history_d528 import HistoryPlan,DAY,HOUR_MS
from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.synthetic_intrabar_barriers import ResearchDirection

END=20_700*DAY
PLAN=HistoryPlan(END,END+HOUR_MS,"a"*64,(("BTCUSDT",END-30*DAY),),
                 "injected_offline_protocol_replay")
NOW=END+2*HOUR_MS


def fake(url,limit):
    p=urlsplit(url)
    q=parse_qs(p.query)
    s=q["symbol"][0]
    if p.path.endswith("funding/history"):
        start,end=int(q["startTime"][0]),int(q["endTime"][0])+1
        rows=[{"symbol":s,"fundingRate":"0.0001","fundingRateTimestamp":str(t)}
              for t in range(((start+HOUR_MS-1)//HOUR_MS)*HOUR_MS,end,HOUR_MS)][-200:]
    else:
        start,end=int(q["start"][0]),int(q["end"][0])+1
        dt=HOUR_MS if q["interval"][0]=="60" else 300000
        rows=[[str(t),"100","102","99","101"] for t in reversed(range(start,end,dt))]
    return json.dumps({"retCode":0,"result":{"category":"linear","symbol":s,"list":rows}}).encode()


class DerivativesTests(unittest.TestCase):
    def test_routes_opt_in_only(self):
        for u in (research_funding_url("BTCUSDT",END-DAY,END),
                  research_mark_url("BTCUSDT","1h",END-DAY,END)):
            with self.assertRaises(J1BybitCaptureError):
                BoundedBybitPublicClient(transport=fake,allow_long_history_research=True).get(u)
            client=BoundedBybitPublicClient(transport=fake,allow_derivatives_history_research=True)
            self.assertEqual(len(client.get(u)[1]["result"]["list"]),24)
            with self.assertRaises(J1BybitCaptureError):
                client.get(u+"&limit=1")
        with self.assertRaises(J1BybitCaptureError):
            research_funding_url("BTCUSDT",END-31*DAY,END)

    def test_funding_resume_saturation_and_zero_get_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp)
            def collect(n,network=True):
                c=BoundedBybitPublicClient(transport=fake,allow_derivatives_history_research=True) if network else None
                return collect_derivatives(home=home,plan=PLAN,days=30,kind="funding",
                    client=c,wall_ms=lambda:NOW,budget=n)
            first=collect(1)
            self.assertEqual(first["public_gets"],1)
            self.assertEqual(first["saved_rows"],0)
            self.assertEqual(first["funding_saturated_pages"],1)
            done=collect(30)
            self.assertEqual(done["public_gets"],6)
            self.assertEqual(done["status"],"query_coverage_complete")
            self.assertEqual(done["saved_rows"],720)
            self.assertFalse(done["funding_calendar_verified"])
            self.assertEqual(collect(30)["public_gets"],0)
            self.assertEqual(collect(30,False)["saved_rows"],720)
            page=next(home.glob("d536-*.json"))
            page.write_bytes(page.read_bytes().replace(b'"raw_sha256":',b'"bad_sha256":'))
            with self.assertRaises(DataValidationError):
                collect(30,False)

    def test_mark_is_separate_and_reports_gap(self):
        def gap(url,limit):
            d=json.loads(fake(url,limit))
            d["result"]["list"].pop()
            return json.dumps(d).encode()
        with tempfile.TemporaryDirectory() as tmp:
            c=BoundedBybitPublicClient(transport=gap,allow_derivatives_history_research=True)
            result=collect_derivatives(home=Path(tmp),plan=PLAN,days=30,kind="mark-1h",
                client=c,wall_ms=lambda:NOW)
            self.assertEqual(result["saved_rows"],719)
            self.assertEqual(result["expected_mark_rows"],720)
            self.assertEqual(result["mark_gap_windows"],1)
            self.assertEqual(result["status"],"query_coverage_partial")

    def test_duplicate_and_wrong_symbol_rejected(self):
        payload=json.loads(fake(research_funding_url("BTCUSDT",END-DAY,END),100000))
        payload["result"]["list"].append(payload["result"]["list"][0])
        with self.assertRaises(DataValidationError):
            normalize_page(payload,"funding","BTCUSDT",END-DAY,END)
        payload["result"]["list"].pop()
        payload["result"]["list"][0]["symbol"]="ETHUSDT"
        with self.assertRaises(DataValidationError):
            normalize_page(payload,"funding","BTCUSDT",END-DAY,END)

    def test_cost_uses_remaining_quantity_and_signed_rate(self):
        a=FundingExposure(1000,D(".001"),D(1),D(1),D(100),D(100))
        b=FundingExposure(2000,D(".001"),D(".25"),D(".5"),D(100),D(120))
        c=FundingExposure(3000,D("-.001"),D(".25"),D(".25"),D(100),D(100))
        args=dict(events=(a,b,c),expected_timestamps=(1000,2000,3000))
        self.assertEqual(funding_cost_bounds(ResearchDirection.LONG,**args),(D(".100"),D(".135")))
        self.assertEqual(funding_cost_bounds(ResearchDirection.SHORT,**args),(D("-.135"),D("-.100")))
        with self.assertRaises(DataValidationError):
            funding_cost_bounds(ResearchDirection.LONG,(a,c),expected_timestamps=(1000,2000,3000))

    @patch("crypto_intelligence_agent.j3_derivatives_history_d536.read_window")
    def test_trade_coverage_exact_requested_not_rounded_shards(self,read):
        read.return_value=(object(),)
        out=trade_coverage(Path("."),PLAN,15,"5m")
        self.assertEqual(out["expected_candles"],15*288)
        self.assertEqual(out["saved_candles"],1)
        self.assertEqual(out["public_gets"],0)


if __name__=="__main__":
    unittest.main()
