"""D546 campaign: bounded successful batches, no retry or silent gaps."""
import unittest
from unittest.mock import Mock

from crypto_intelligence_agent.j3_history_campaign_d546 import run_campaign,COOLDOWN_SECONDS
from crypto_intelligence_agent.market_data import DataValidationError

DIGEST="a"*64
CUTOFF=1795564800000


def page(saved,new,*,gaps=(),expected=100,gets=1):
    return {"schema_version":"d543-exact-history-coverage-v1","plan_sha256":DIGEST,
            "cutoff_ms":CUTOFF,"requested_days":365,"planned_days":365,
            "interval":"5m","actual_rows_determine_missing_pages":True,
            "orders_sent":False,"j1_touched":False,"profile_modified":False,
            "legacy_checkpoint_modified":False,"status":"coverage_complete" if saved==expected else "coverage_partial",
            "gap_member_shards":list(gaps),"saved_candles":saved,
            "missing_candles":expected-saved,"new_candles_committed":new,
            "expected_candles_after_launch":expected,"public_gets":gets}


class CampaignTests(unittest.TestCase):
    def run_pages(self,pages,**kw):
        now=[0]
        emitted=[]
        pauses=[]
        collect=Mock(side_effect=pages)
        def pause(seconds):
            pauses.append(seconds)
            now[0]+=seconds
        args=dict(days=365,plan_sha256=DIGEST,cutoff_ms=CUTOFF,baseline=40,
                  expected=100,collect=collect,emit=emitted.append,clock=lambda:now[0],sleep=pause)
        args.update(kw)
        result=run_campaign(**args)
        return result,collect.call_count,emitted,pauses

    def test_successful_batches_continue_and_finish_once(self):
        result,n,events,pauses=self.run_pages([page(70,30),page(100,30)])
        self.assertEqual((result["status"],n),("campaign_complete",2))
        self.assertEqual(result["new_candles_confirmed"],60)
        self.assertEqual(result["completed_batch_gets"],2)
        self.assertEqual(pauses,[COOLDOWN_SECONDS])
        self.assertEqual(len(events),2)
        self.assertNotIn("gap_member_shards",events[0])
        self.assertFalse(result["automatic_retry"])

    def test_stops_at_gap_stall_or_zero_gets(self):
        for d,reason in ((page(60,20,gaps=({"example":1},)),"provider_gap"),
                         (page(40,0,gets=0),"no_progress")):
            with self.subTest(reason=reason):
                out,n,_,pauses=self.run_pages([d,page(100,40)])
                self.assertEqual((out["status"],out["reason"],n,pauses),
                                 ("campaign_stopped",reason,1,[]))

    def test_inconsistent_or_failed_batch_is_not_retried(self):
        for d in (page(80,10),{**page(70,30),"plan_sha256":"b"*64},
                  {**page(70,30),"public_gets":51},{**page(70,30),"j1_touched":True}):
            with self.assertRaises(DataValidationError):
                self.run_pages([d])
        collect=Mock(side_effect=RuntimeError("provider failure"))
        with self.assertRaises(RuntimeError):
            self.run_pages([],collect=collect)
        self.assertEqual(collect.call_count,1)

    def test_budget_and_already_complete(self):
        a,n,_,pauses=self.run_pages([page(70,30)],max_batches=1)
        self.assertEqual((a["status"],a["reason"],n,pauses),
                         ("campaign_budget_reached","batch_budget",1,[]))
        a,n,_,pauses=self.run_pages([page(70,30)],wall_seconds=31*60)
        self.assertEqual((a["reason"],n,pauses),("wall_budget",1,[]))
        a,n,_,pauses=self.run_pages([],baseline=100)
        self.assertEqual((a["status"],a["reason"],n,pauses),
                         ("campaign_complete","already_complete",0,[]))


if __name__=="__main__":
    unittest.main()
