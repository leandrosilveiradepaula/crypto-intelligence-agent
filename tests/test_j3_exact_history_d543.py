"""D543 exact range, reuse disjoint rows and preserve D528 checkpoints."""
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs,urlsplit
from unittest.mock import patch
import json
import unittest

from crypto_intelligence_agent.bybit_public_j1_transport import BoundedBybitPublicClient,J1BybitCaptureError
from crypto_intelligence_agent.j3_long_history_d528 import (
    collect_batch,read_window,shard_path,_store,EXCHANGE,DAY,HOUR_MS,
)
from crypto_intelligence_agent.j3_exact_history_d543 import collect_exact_batch,exact_windows
from test_j3_long_history_d528 import END,NOW,PLAN,fake


class ExactHistoryTests(unittest.TestCase):
    @patch("crypto_intelligence_agent.j3_long_history_d528.MIN_FREE_BYTES",0)
    @patch("crypto_intelligence_agent.j3_exact_history_d543.MIN_FREE_BYTES",0)
    def test_legacy_resume_exact_extend_without_redownload(self):
        with TemporaryDirectory() as d:
            home=Path(d)
            seen=[]
            def transport(url,limit):
                q=parse_qs(urlsplit(url).query)
                seen.append((q["symbol"][0],int(q["start"][0]),int(q["end"][0])+1))
                return fake(url,limit)
            def run(fn,days,budget=20):
                return fn(home=home,plan=PLAN,days=days,interval="1h",
                    client=BoundedBybitPublicClient(transport=transport,allow_long_history_research=True),
                    wall_ms=lambda:NOW,max_gets=budget)
            run(collect_batch,30)
            store=_store(shard_path(home,PLAN,END-30*DAY,"1h"))
            args=dict(data_type="closed_candle",exchange=EXCHANGE,symbol="BTCUSDT",interval="1h")
            before=store.latest_checkpoint(**args)
            seen.clear()
            first=run(collect_exact_batch,35)
            self.assertEqual(first["status"],"coverage_complete")
            self.assertEqual(first["planned_days"],35)
            self.assertEqual(first["saved_candles"],35*24+2)
            self.assertEqual(first["new_candles_committed"],5*24)
            self.assertEqual(seen,[("BTCUSDT",END-35*DAY,END-30*DAY)])
            seen.clear()
            second=run(collect_exact_batch,40)
            self.assertEqual(second["new_candles_committed"],5*24)
            self.assertEqual(seen,[("BTCUSDT",END-40*DAY,END-35*DAY)])
            self.assertEqual(len(read_window(home,PLAN,"BTCUSDT","1h",END-40*DAY,END)),40*24)
            self.assertEqual(store.latest_checkpoint(**args),before)
            self.assertEqual(run(collect_exact_batch,40)["public_gets"],0)
            old=_store(shard_path(home,PLAN,END-60*DAY,"1h"))
            self.assertIsNone(old.latest_checkpoint(**args))

    @patch("crypto_intelligence_agent.j3_long_history_d528.MIN_FREE_BYTES",0)
    @patch("crypto_intelligence_agent.j3_exact_history_d543.MIN_FREE_BYTES",0)
    def test_rate_limit_stops_and_previous_page_survives(self):
        with TemporaryDirectory() as d:
            home=Path(d)
            seen=[]
            def limited(url,limit):
                seen.append(url)
                if len(seen)==2:
                    return json.dumps({"retCode":10006,"retMsg":"Too many visits!"}).encode()
                return fake(url,limit)
            args=dict(home=home,plan=PLAN,days=30,interval="5m",
                      wall_ms=lambda:NOW,max_gets=10)
            c=BoundedBybitPublicClient(transport=limited,allow_long_history_research=True)
            with self.assertRaises(J1BybitCaptureError):
                collect_exact_batch(**args,client=c)
            self.assertEqual(len(seen),2)
            self.assertEqual(len(read_window(home,PLAN,"BTCUSDT","5m",END-30*DAY,
                                    END-30*DAY+1000*300000)),1000)
            resumed=[]
            def capture(url,limit):
                resumed.append(url)
                return fake(url,limit)
            result=collect_exact_batch(**args,client=BoundedBybitPublicClient(
                                transport=capture,allow_long_history_research=True))
            self.assertEqual(result["status"],"coverage_complete")
            self.assertNotIn(seen[0],resumed)
            self.assertEqual(result["saved_candles"],30*288+24)

    def test_no_extra_25_days_and_same_shard(self):
        from dataclasses import replace
        p=replace(PLAN,members=(("BTCUSDT",END-800*DAY),))
        jobs=exact_windows(p,365,"5m")
        oldest=jobs[-1]
        self.assertEqual(oldest[0],END-390*DAY)
        self.assertEqual(oldest[3],END-365*DAY)
        self.assertEqual(sum((e-f)//300000 for _,e,_,f in jobs),365*288)


if __name__=="__main__":
    unittest.main()
