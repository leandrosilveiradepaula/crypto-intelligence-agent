import gzip
import unittest
from datetime import date, datetime, timedelta, timezone
from crypto_intelligence_agent.bybit_archive_week import inspect_seven_daily_archives
from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.bybit_public_trade_archive import FIELDS

def samples():
    out=[]
    for i in range(7):
        day=date(2020,4,5)+timedelta(days=i)
        stamp=str(int(datetime(day.year,day.month,day.day,tzinfo=timezone.utc).timestamp()))
        fields=(stamp,"BTCUSDT","Buy","1.25","9000.5","PlusTick",
                "fixture","1125062500000","1.25","11250.625")
        csv=",".join(FIELDS)+"\n"+",".join(fields)+"\n"
        out.append(("BTCUSDT"+day.isoformat()+".csv.gz",gzip.compress(csv.encode(),mtime=0)))
    return tuple(out)

class WeeklyTests(unittest.TestCase):
    def test_one_week(self):
        result=inspect_seven_daily_archives(samples())
        self.assertEqual((result.days,result.trades,result.observed_hour_total,result.missing_hour_total),(7,7,7,161))
        self.assertFalse(result.financial_backtest_approved)
        self.assertFalse(result.orders_sent)
        self.assertEqual(result,inspect_seven_daily_archives(samples()))
    def test_gaps_and_corruption(self):
        archive=samples()
        for entries in (archive[:6],archive[::-1],archive[:2]+archive[3:]+archive[2:3],
                        archive[:2]+((archive[2][0],b"bad"),)+archive[3:]):
            with self.assertRaises(DataValidationError):
                inspect_seven_daily_archives(entries)
if __name__=="__main__":
    unittest.main()
