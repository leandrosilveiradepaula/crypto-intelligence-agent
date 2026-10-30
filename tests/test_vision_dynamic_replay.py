"""Offline dynamic ranking must be deterministic and fail closed."""
from dataclasses import replace
from decimal import Decimal
import unittest
from crypto_intelligence_agent.offline_vision_month import OfflineVisionCandle, OfflineVisionMonth
from crypto_intelligence_agent.vision_dynamic_replay import replay_offline_vision_dynamic_ranking,HOUR_MS
from crypto_intelligence_agent.market_data import DataValidationError
from test_offline_vision_month import synthetic_zip
from crypto_intelligence_agent.offline_vision_month import inspect_offline_vision_month


def fixture(symbol):
    months=[]
    for y,m in ((2026,8),(2026,9)):
        blob,name,digest,end=synthetic_zip(year=y,month=m,symbol=symbol)
        months.append(inspect_offline_vision_month(
            blob,archive_name=name,expected_sha256=digest,as_of_ms=end+HOUR_MS))
    return tuple(months)


class VisionDynamicReplayTests(unittest.TestCase):
    def test_aligned_two_assets_and_future_mutation(self):
        a,b=fixture("BTCUSDT"),fixture("ETHUSDT")
        at=a[0].first_open_ms+30*HOUR_MS
        end=at+48*HOUR_MS
        cutoff=b[-1].end_open_exclusive_ms+HOUR_MS
        baseline=replay_offline_vision_dynamic_ranking((a,b),as_of_ms=cutoff,
                 first_decision_ms=at,last_decision_ms=end)
        self.assertEqual((baseline.asset_count,baseline.decisions_count),(2,3))
        self.assertEqual(baseline,replay_offline_vision_dynamic_ranking((b,a),
                 as_of_ms=cutoff,first_decision_ms=at,last_decision_ms=end))
        v=baseline.sanitized_report()
        self.assertFalse(v["marketwide_top50_verified"])
        self.assertFalse(v["orders_sent"])
        self.assertNotIn("BTCUSDT",str(v))
        future=list(b[-1].candles)
        future[-1]=replace(future[-1],documented_quote_volume=Decimal("999"))
        changed=b[:-1]+(replace(b[-1],candles=tuple(future)),)
        newer=replay_offline_vision_dynamic_ranking((a,changed),as_of_ms=cutoff,
                 first_decision_ms=at,last_decision_ms=end)
        self.assertEqual(baseline.ranking_digest_sha256,newer.ranking_digest_sha256)

    def test_invalid_schedule_and_duplicate_fail_closed(self):
        a,b=fixture("BTCUSDT"),fixture("ETHUSDT")
        at=a[0].first_open_ms+30*HOUR_MS
        cutoff=b[-1].end_open_exclusive_ms+HOUR_MS
        def run(groups=(a,b),**kw):
            return replay_offline_vision_dynamic_ranking(groups,as_of_ms=cutoff,
                 first_decision_ms=at,last_decision_ms=at+24*HOUR_MS,**kw)
        for bad in (dict(step_hours=0),dict(step_hours=True),
                    dict(step_hours=25),dict(max_candidates=51)):
            with self.subTest(bad=bad),self.assertRaises(DataValidationError):run(**bad)
        with self.assertRaises(DataValidationError):run((a,a))
        with self.assertRaises(DataValidationError):
            replay_offline_vision_dynamic_ranking((a,b),as_of_ms=cutoff,
                first_decision_ms=at,last_decision_ms=cutoff+HOUR_MS)
