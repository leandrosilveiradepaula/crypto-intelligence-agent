"""J1 #250: seven fixed public Bybit archive GETs, private ephemeral research."""
from __future__ import annotations
import argparse
import json
from datetime import date, timedelta
from urllib.error import HTTPError
from urllib.request import Request
from crypto_intelligence_agent.bybit_archive_week import inspect_seven_daily_archives
from crypto_intelligence_agent.bybit_public_trade_archive import MAX_GZIP_BYTES
from scripts.probe_bybit_public_trade_archive import _open

FIRST_DAY = date(2020, 3, 25)
ORIGIN = "https://public.bybit.com/trading/BTCUSDT/"

def probe_week(*, allow_public_network=False, allow_weekly_archive_probe=False, opened=None):
    report = {
        "status": "explicit_opt_in_required", "requests_attempted": 0,
        "data_stored": False, "orders_sent": False, "rights_authorized": False,
        "canonical_ohlcv_approved": False, "financial_backtest_approved": False,
        "historical_top50_approved": False, "live_trading_authorized": False,
    }
    if allow_public_network is not True or allow_weekly_archive_probe is not True:
        return report
    results=[]
    for i in range(7):
        name="BTCUSDT"+(FIRST_DAY+timedelta(days=i)).isoformat()+".csv.gz"
        url=ORIGIN+name
        report["requests_attempted"]+=1
        try:
            with (opened or _open)(Request(url,method="GET"),timeout=10) as response:
                if response.getcode()!=200 or response.geturl()!=url:
                    report["status"]="http_or_redirect_rejected_no_retry"
                    return report
                blob=response.read(MAX_GZIP_BYTES+1)
            # Validate immediately before retaining bounded bytes in RAM.
            from crypto_intelligence_agent.bybit_public_trade_archive import inspect_trade_archive
            inspect_trade_archive(blob,archive_name=name)
            results.append((name,blob))
        except HTTPError as exc:
            report["status"]=("access_restricted_no_retry"
                              if exc.code in (401,403,418,429,451)
                              else "http_error_no_retry")
            return report
        except Exception:
            report["status"]="unavailable_or_schema_rejected_no_retry"
            return report
    result=inspect_seven_daily_archives(tuple(results))
    report.update({
        "status":"unverified_historical_week_observed",
        "archive_count": result.days,
        "trades": result.trades,
        "observed_hour_total": result.observed_hour_total,
        "hours_without_trades_in_archives":result.missing_hour_total,
        "partial_days": result.partial_days,
        "manifest_sha256":result.manifest_sha256,
    })
    return report

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-public-network",action="store_true")
    parser.add_argument("--allow-weekly-archive-probe",action="store_true")
    args=parser.parse_args(argv)
    report=probe_week(allow_public_network=args.allow_public_network,
                      allow_weekly_archive_probe=args.allow_weekly_archive_probe)
    print(json.dumps(report,sort_keys=True,separators=(",",":")))
    return int(report["status"]!="unverified_historical_week_observed")

if __name__=="__main__":
    raise SystemExit(main())
