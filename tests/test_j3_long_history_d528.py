"""D528 real contracts with injected transport; no network or live writes."""
from pathlib import Path
from decimal import Decimal
import json
import os
import io
from contextlib import redirect_stdout
import tempfile
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_public_j1_transport import (
    BoundedBybitPublicClient, J1BybitCaptureError, research_history_kline_url,
)
from crypto_intelligence_agent.j3_long_history_d528 import (
    HistoryPlan, decode_plan, windows, collect_batch, read_window,
    freeze_cohort, load_plan, PLAN_FILE,
    rank_closed_cohort, DAY, HOUR_MS, QUALITY, EXCHANGE, MARKET,
)
from crypto_intelligence_agent.market_data import ClosedCandle, DataGapError, DataValidationError
from urllib.parse import parse_qs,urlsplit
from test_j2_dynamic_public_n50_d451 import scenario, selected, NOW as D451_NOW
from crypto_intelligence_agent.j2_dynamic_public_n50_d451 import capture_dynamic_public_n50
from crypto_intelligence_agent.bybit_public_j1_transport import instruments_url, tickers_url
from scripts.run_j3_long_history_d528 import main as collector_main

END=20_700*DAY
NOW=END+HOUR_MS
PLAN=HistoryPlan(END,NOW-1000,"a"*64,(("BTCUSDT",END-40*DAY),
    ("ETHUSDT",END-2*HOUR_MS)),"injected_offline_protocol_replay")


def fake(url, limit):
    q=parse_qs(urlsplit(url).query)
    start,end=int(q["start"][0]),int(q["end"][0])+1
    dt=HOUR_MS if q["interval"][0]=="60" else 300_000
    rows=[[str(t),"100","101","99","100","10","1000"]
          for t in reversed(range(start,end,dt))]
    return json.dumps({"retCode":0,"result":{"category":"linear",
        "symbol":q["symbol"][0],"list":rows}}).encode()


class LongHistoryTests(unittest.TestCase):
    def test_freeze_actual_d451_snapshot(self):
        # Regress the real AttributeError: exercise the real D451 dataclass,
        # not a prebuilt HistoryPlan or a mock with permissive attributes.
        snapshot=selected()
        plan=freeze_cohort(snapshot)
        self.assertEqual(plan.observed_at_ms,snapshot.ticker_received_ms)
        self.assertEqual(plan.cohort_sha256,snapshot.fingerprint_sha256)
        self.assertEqual(plan.members,tuple(sorted(
            (m.symbol,m.launch_time_ms) for m in snapshot.ranked)))
        self.assertEqual(plan.cutoff_ms,((D451_NOW-2000)//DAY)*DAY)
        self.assertEqual(len(plan.members),50)
        self.assertEqual(decode_plan(plan.encode()),plan)

    @unittest.skipUnless(os.name=="posix" and hasattr(os,"geteuid")
                         and os.geteuid()!=0,"real POSIX private owner CLI")
    @patch("crypto_intelligence_agent.j3_long_history_d528.MIN_FREE_BYTES",0)
    def test_cli_init_real_d451_capture_then_resume(self):
        # Use real D451 selection, real D528 plan publication, lock, transport
        # parsing, SQLite/checkpoint writes and readback. Inject only network
        # payloads and time. The second invocation must not recapture D451.
        pages,tick=scenario()
        replies={instruments_url():pages[0],
                 instruments_url(cursor="cursor2"):pages[1],tickers_url():tick}
        cohort_client=BoundedBybitPublicClient(
            transport=lambda url,limit:json.dumps(replies[url]).encode())
        snapshot=capture_dynamic_public_n50(client=cohort_client,wall_ms=lambda:D451_NOW,
            allow_public_network=True,confirm_personal_readonly_research=True,
            confirm_region_eligible=True,confirm_public_data_rights=True)
        self.assertEqual(cohort_client.requests_attempted,3)
        with tempfile.TemporaryDirectory(prefix="d528-history-test-") as d:
            home=Path(d)
            home.chmod(0o700)
            args=["--directory",str(home),"--days","90","--interval","1h","--max-gets","1",
                  "--allow-public-network","--confirm-personal-readonly-research",
                  "--confirm-region-eligible","--confirm-public-data-rights"]
            clients=[]
            def bounded(**kwargs):
                c=BoundedBybitPublicClient(transport=fake,**kwargs)
                clients.append(c)
                return c
            with patch("scripts.run_j3_long_history_d528.capture_dynamic_public_n50",
                       return_value=snapshot) as capture, \
                 patch("scripts.run_j3_long_history_d528.BoundedBybitPublicClient",side_effect=bounded), \
                 patch("scripts.run_j3_long_history_d528.time.time_ns",return_value=(D451_NOW+1000)*1000000), \
                 patch("scripts.run_j3_long_history_d528.time.sleep"):
                stream=io.StringIO()
                with redirect_stdout(stream):
                    self.assertEqual(collector_main(args+["--init"]),0)
                first=json.loads(stream.getvalue())
                plan=load_plan(home)
                self.assertEqual(plan,freeze_cohort(snapshot))
                raw=(home/PLAN_FILE).read_bytes()
                self.assertEqual(first["public_gets"],1)
                self.assertGreater(first["saved_candles"],0)
                stream=io.StringIO()
                with redirect_stdout(stream):
                    self.assertEqual(collector_main(args),0)
                second=json.loads(stream.getvalue())
                self.assertEqual(capture.call_count,1)
                self.assertEqual(second["public_gets"],1)
                self.assertGreater(second["saved_candles"],first["saved_candles"])
                self.assertEqual((home/PLAN_FILE).read_bytes(),raw)
                self.assertEqual(len(clients),2)

    def test_transport_is_opt_in_and_bounded(self):
        url=research_history_kline_url("BTCUSDT","1h",END-1000*HOUR_MS,END)
        with self.assertRaises(J1BybitCaptureError):
            BoundedBybitPublicClient(transport=fake).get(url)
        client=BoundedBybitPublicClient(transport=fake,allow_long_history_research=True)
        self.assertEqual(len(client.get(url)[1]["result"]["list"]),1000)
        five=research_history_kline_url("BTCUSDT","5m",END-1000*300_000,END)
        self.assertEqual(len(client.get(five)[1]["result"]["list"]),1000)
        with self.assertRaises(J1BybitCaptureError):
            research_history_kline_url("BTCUSDT","5m",END-1001*300_000,END)
        with self.assertRaises(J1BybitCaptureError):
            client.get(url+"&limit=1000")

    def test_plan_fixed_shards_extend_and_launch_clip(self):
        self.assertEqual(decode_plan(PLAN.encode()),PLAN)
        a=tuple(windows(PLAN,90,"1h"))
        b=tuple(windows(PLAN,365,"1h"))
        self.assertEqual(b[:len(a)],a)
        self.assertEqual(a[1][3],END-2*HOUR_MS)
        full=HistoryPlan(END,NOW-1000,"a"*64,(("BTCUSDT",END-800*DAY),),
                        "injected_offline_protocol_replay")
        self.assertEqual(min(row[0] for row in windows(full,730,"5m")),END-730*DAY)
        with self.assertRaises(DataValidationError):
            decode_plan(PLAN.encode().replace(b'"cutoff_ms":',b'"cutoff_ms":1,"cutoff_ms":'))

    @patch("crypto_intelligence_agent.j3_long_history_d528.MIN_FREE_BYTES",0)
    def test_resume_without_redownload_and_cross_shard_read(self):
        with tempfile.TemporaryDirectory() as d:
            home=Path(d)
            def run(budget):
                c=BoundedBybitPublicClient(transport=fake,allow_long_history_research=True)
                return collect_batch(home=home,plan=PLAN,days=40,interval="1h",
                                     client=c,wall_ms=lambda:NOW,max_gets=budget)
            first=run(1)
            self.assertEqual(first["public_gets"],1)
            self.assertEqual(first["status"],"coverage_partial")
            second=run(10)
            self.assertEqual(second["public_gets"],2)
            self.assertEqual(second["status"],"coverage_complete")
            self.assertEqual(second["saved_candles"],40*24+2)
            third=run(10)
            self.assertEqual(third["public_gets"],0)
            self.assertFalse(third["historical_marketwide_top50_verified"])
            rows=read_window(home,PLAN,"BTCUSDT","1h",END-31*DAY,END-29*DAY)
            self.assertEqual(len(rows),48)
            self.assertEqual(rows[0].quality,QUALITY)
            with self.assertRaises(DataGapError):
                read_window(home,PLAN,"ETHUSDT","1h",END-DAY,END)

    @patch("crypto_intelligence_agent.j3_long_history_d528.MIN_FREE_BYTES",0)
    def test_provider_gap_does_not_create_candles_or_block_other_symbol(self):
        def gap(url,limit):
            d=json.loads(fake(url,limit))
            if d["result"]["symbol"]=="BTCUSDT":
                d["result"]["list"].pop()
            return json.dumps(d).encode()
        with tempfile.TemporaryDirectory() as d:
            c=BoundedBybitPublicClient(transport=gap,allow_long_history_research=True)
            out=collect_batch(home=Path(d),plan=PLAN,days=30,interval="1h",
                              client=c,wall_ms=lambda:NOW,max_gets=10)
            self.assertEqual(out["saved_candles"],2)
            self.assertEqual(out["by_symbol"]["BTCUSDT"]["gap_shards"],1)
            self.assertEqual(out["status"],"coverage_partial")

    def test_rank_uses_only_previous_closed_hours(self):
        p=HistoryPlan(END,NOW-1000,"a"*64,
            (("BTCUSDT",END-40*DAY),("ETHUSDT",END-40*DAY)),
            "injected_offline_protocol_replay")
        decision=END-HOUR_MS
        def bar(s,t,v):
            return ClosedCandle(EXCHANGE,MARKET,s,"1h",t,t+HOUR_MS-1,
                Decimal(100),Decimal(101),Decimal(99),Decimal(100),Decimal(1),Decimal(v),QUALITY)
        b=tuple(bar("BTCUSDT",t,1) for t in range(decision-DAY,decision,HOUR_MS))
        e=tuple(bar("ETHUSDT",t,2) for t in range(decision-DAY,decision,HOUR_MS))
        self.assertEqual(rank_closed_cohort(p,decision,{"BTCUSDT":b+(bar("BTCUSDT",decision,100000),),
                                                      "ETHUSDT":e})[0][0],"ETHUSDT")
        with self.assertRaises(DataGapError):
            rank_closed_cohort(p,decision,{"BTCUSDT":b,"ETHUSDT":e[:-1]})


if __name__=="__main__":
    unittest.main()
