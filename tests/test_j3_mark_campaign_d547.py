"""D547 uses immutable D536 mark coverage; no retries or manufactured readiness."""
import unittest
from unittest.mock import Mock

from crypto_intelligence_agent.j3_mark_campaign_d547 import run_mark_campaign,replay_readiness
from crypto_intelligence_agent.market_data import DataValidationError

DIGEST="a"*64


def mark(complete,missing,gaps,saved,gets=0):
    return {"schema_version":"d536-derivatives-coverage-v1","dataset":"mark-5m",
            "requested_days":365,"planned_days":390,"plan_sha256":DIGEST,
            "planned_windows":3,"query_complete_windows":complete,
            "missing_windows":missing,"mark_gap_windows":gaps,
            "saved_rows":saved,"expected_mark_rows":300,"public_gets":gets,
            "status":"query_coverage_complete" if complete==3 else "query_coverage_partial",
            "orders_sent":False,"j1_touched":False,"funding_calendar_verified":False,
            "historical_risk_tiers_verified":False,"liquidation_verified":False}


class MarkCampaignTests(unittest.TestCase):
    def run_pages(self,pages,baseline=None,**kw):
        callback=Mock(side_effect=pages)
        pauses=[]
        args=dict(digest=DIGEST,baseline=baseline or mark(1,2,0,100),
                  collect=callback,emit=lambda d:None,clock=lambda:0,sleep=pauses.append)
        args.update(kw)
        out=run_mark_campaign(**args)
        return out,callback.call_count,pauses

    def test_progress_and_complete(self):
        d,n,p=self.run_pages([mark(2,1,0,200,1),mark(3,0,0,300,1)])
        self.assertEqual((d["status"],d["new_rows_confirmed"],n,p),
                         ("campaign_complete",200,2,[300]))

    def test_gap_stop_and_no_retry(self):
        d,n,p=self.run_pages([mark(1,1,1,140,1),mark(2,0,1,240,1)])
        self.assertEqual((d["reason"],n,p),("provider_gap",1,[]))
        d,n,p=self.run_pages([],baseline=mark(1,1,1,140))
        self.assertEqual((d["reason"],n,p),("existing_provider_gap",0,[]))
        bad=Mock(side_effect=RuntimeError("provider failure"))
        with self.assertRaises(RuntimeError):
            self.run_pages([],collect=bad)
        self.assertEqual(bad.call_count,1)

    def test_no_progress_and_budget(self):
        d,n,p=self.run_pages([mark(1,2,0,100)])
        self.assertEqual((d["reason"],n,p),("no_progress",1,[]))
        d,n,p=self.run_pages([mark(2,1,0,200,1)],max_batches=1)
        self.assertEqual((d["reason"],n,p),("batch_budget",1,[]))
        with self.assertRaises(DataValidationError):
            self.run_pages([mark(2,1,0,200,2)])

    def test_preflight_requires_trade_and_observed_query_coverage(self):
        t={"dataset":"trade-5m","requested_days":365,"public_gets":0,
           "saved_candles":300,"expected_candles":300,"missing_candles":0}
        f={"schema_version":"d536-derivatives-coverage-v1","dataset":"funding",
           "requested_days":365,"plan_sha256":DIGEST,"public_gets":0,
           "funding_calendar_verified":False,"planned_windows":2,"query_complete_windows":2,
           "status":"query_coverage_complete"}
        def check(trade=t,m=mark(3,0,0,300),funding=f):
            return replay_readiness(digest=DIGEST,trade=trade,mark=m,funding=funding)
        self.assertEqual(check()["status"],"ready")
        self.assertEqual(check(m=mark(2,1,0,200))["status"],"incomplete")
        self.assertEqual(check(trade={**t,"saved_candles":299,"missing_candles":1})["status"],"incomplete")
        self.assertEqual(check(funding={**f,"query_complete_windows":1})["status"],"incomplete")
        # Queried provider gap is explicit; never represented as verified liquidation.
        d=check(m=mark(2,0,1,250))
        self.assertEqual((d["status"],d["mark_gap_windows"],d["liquidation_verified"]),("ready",1,False))


if __name__=="__main__":
    unittest.main()
