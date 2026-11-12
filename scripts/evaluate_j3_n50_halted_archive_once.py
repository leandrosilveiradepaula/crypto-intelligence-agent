"""J3/D305: count-only ex-post archived N50 HALT research, never an order.

Run only as the private data owner. This uses the immutable D304 forensic
contract and the J3/D302 24bar-prefix-versus-next-close calculation.
"""
from __future__ import annotations

import argparse
from decimal import Decimal, ROUND_HALF_EVEN, localcontext, Context
import json

from crypto_intelligence_agent.j3_n50_expost_onehour import evaluate_n50_expost_marks

_DEC = Decimal("0.01")


def main(argv: list[str] | None = None) -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--allow-private-readonly-audit",action="store_true")
    p.add_argument("--enable-archived-halted-research",action="store_true")
    args=p.parse_args(argv)
    report={
        "schema_version":"j3-n50-halted-archive-count-only-v1",
        "status":"optin_required",
        "archived_halt_source_verified":False,
        "audited_contracts":0,
        "prior_closed_end_ms":None,
        "outcome_closed_end_ms":None,
        "hypothetical_notional_per_asset_quote":None,
        "hypothetical_total_cost_per_asset_quote":None,
        "top_five_long_net_mark_sum_quote":None,
        "bottom_five_short_net_mark_sum_quote":None,
        "all_fifty_long_net_mark_sum_quote":None,
        "financial_backtest_approved":False,
        "out_of_sample_results_validated":False,
        "trading_enabled":False,
        "orders_sent":False,
        "network_requests":0,
        "database_mutation_statements":0,
        "systemd_modified":False,
    }
    if args.allow_private_readonly_audit and args.enable_archived_halted_research:
        result=evaluate_n50_expost_marks(
            allow_private_readonly_audit=True,
            allow_archived_halted_research=True,
            include_private_symbols=False,
        )
        report["status"]=result["status"]
        if (result["status"]=="archived_halted_expost_reference_only"
                and result.get("halted_archive_source_verified") is True
                and result.get("audited_contracts")==50
                and result.get("orders_sent") is False
                and result.get("network_requests")==0
                and result.get("database_mutation_statements")==0
                and result.get("financial_backtest_approved") is False
                and result.get("out_of_sample_results_validated") is False):
            report["archived_halt_source_verified"]=True
            report["audited_contracts"]=50
            report["prior_closed_end_ms"]=result["prior_closed_end_ms"]
            report["outcome_closed_end_ms"]=result["outcome_closed_end_ms"]
            def rounded(key: str) -> str:
                with localcontext(Context(prec=700)):
                    return format(
                        Decimal(result[key]).quantize(
                            _DEC,rounding=ROUND_HALF_EVEN,
                        ),"f",
                    )
            for output_key,raw_key in (
                ("hypothetical_notional_per_asset_quote",
                 "hypothetical_notional_per_asset_quote"),
                ("hypothetical_total_cost_per_asset_quote",
                 "hypothetical_total_cost_per_asset_quote"),
                ("top_five_long_net_mark_sum_quote",
                 "top_tail_long_expost_net_mark_sum_quote"),
                ("bottom_five_short_net_mark_sum_quote",
                 "bottom_tail_short_expost_net_mark_sum_quote"),
                ("all_fifty_long_net_mark_sum_quote",
                 "all50_long_expost_net_mark_sum_quote"),
            ):
                report[output_key]=rounded(raw_key)
        else:
            report["status"]="unverified_halted_archive"
    print(json.dumps(report,sort_keys=True,separators=(",",":"),ensure_ascii=True))
    return 0 if report["archived_halt_source_verified"] else 65


if __name__=="__main__":
    raise SystemExit(main())
