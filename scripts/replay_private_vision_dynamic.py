"""Read-only, owner-only replay of PRE-EXISTING private Vision manifests.

No network, no market data output, no writes or trading. Not a live feed.
"""
from __future__ import annotations
import argparse
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path
import re

from crypto_intelligence_agent.offline_vision_month import inspect_offline_vision_month
from crypto_intelligence_agent.synthetic_margin_envelope import SyntheticMarginBasis
from crypto_intelligence_agent.vision_intrabar_stress import VisionStressAssumptions
from crypto_intelligence_agent.vision_stress_oos import audit_costed_vision_intrabar_oos
from crypto_intelligence_agent.vision_costed_oos import costed_vision_monthly_oos
from crypto_intelligence_agent.vision_dynamic_replay import replay_offline_vision_dynamic_ranking,HOUR_MS
from scripts.audit_private_vision_multiasset import audit_private_vision_multiasset_coverage
from scripts.audit_private_bybit_json import _read_private_file

NAME=re.compile(r"[A-Z0-9]{2,20}USDT-1h-20[0-9]{2}-(0[1-9]|1[0-2])\.zip\Z")
MAX_INPUT_BYTES=192_000_000


class VisionReplayPrivateError(ValueError):
    """Never include private paths or archive contents."""


def private_vision_dynamic_replay(*,manifest_paths:tuple[str,...],
    allow_personal_nonproduction_research:bool=False,
    first_decision_ms:int,last_decision_ms:int,
    step_hours:int=24,max_candidates:int=50,
    stress_assumptions:VisionStressAssumptions|None=None,
    stress_selection_cost_bps:Decimal=Decimal(0),
    costed_oos_bps:Decimal|None=None)->dict:
    if allow_personal_nonproduction_research is not True or os.name!="posix":
        raise VisionReplayPrivateError("owner_only_research_opt_in_required")
    if type(manifest_paths) is not tuple or not 2<=len(manifest_paths)<=50:
        raise VisionReplayPrivateError("bounded_manifest_count_required")
    # Validate all private path, ZIP, checksum sidecars and shared month range
    # BEFORE any ranking or emitting results. Auditor does not write.
    try:
        checked=audit_private_vision_multiasset_coverage(
            manifest_paths=manifest_paths,allow_personal_nonproduction_research=True)
        if checked["observed_symbol_count"] != len(manifest_paths):
            raise VisionReplayPrivateError("coverage_mismatch")
        data=[]
        total=0
        for filename in manifest_paths:
            path=Path(filename)
            manifest=json.loads(_read_private_file(str(path),max_bytes=16_384))
            if (type(manifest) is not dict or set(manifest)!={"schema_version","as_of_ms","archives"}
                    or manifest["schema_version"]!="vision-local-series-v1"):
                raise VisionReplayPrivateError("manifest_rejected")
            months=[]
            for archive in manifest["archives"]:
                name,digest=archive["name"],archive["sha256"]
                if type(name) is not str or NAME.fullmatch(name) is None:
                    raise VisionReplayPrivateError("archive_name_rejected")
                blob=_read_private_file(str(path.parent/name),max_bytes=8_000_000)
                total+=len(blob)
                if total>MAX_INPUT_BYTES or sha256(blob).hexdigest()!=digest:
                    raise VisionReplayPrivateError("archive_input_budget_or_hash_failed")
                months.append(inspect_offline_vision_month(
                    blob,archive_name=name,expected_sha256=digest,
                    as_of_ms=manifest["as_of_ms"]))
            data.append(tuple(months))
        result=replay_offline_vision_dynamic_ranking(
            tuple(data),as_of_ms=min(
                checked["end_open_exclusive_ms"]+HOUR_MS,
                min(m[0].first_open_ms+1000*24*HOUR_MS for m in data)),
            first_decision_ms=first_decision_ms,
            last_decision_ms=last_decision_ms,
            step_hours=step_hours,max_candidates=max_candidates)
        report=result.sanitized_report()
        if costed_oos_bps is not None:
            costed=costed_vision_monthly_oos(tuple(data),
                as_of_ms=checked["end_open_exclusive_ms"]+HOUR_MS,
                cost_bps_per_side=costed_oos_bps)
            report["hypothetical_costed_oos"]=costed.sanitized_report()
        if stress_assumptions is not None:
            stress=audit_costed_vision_intrabar_oos(
                tuple(data),as_of_ms=checked["end_open_exclusive_ms"]+HOUR_MS,
                cost_bps_per_side=stress_selection_cost_bps,
                assumptions=stress_assumptions)
            report["hypothetical_intrabar_oos"]=stress.sanitized_report()
        report["local_archives_audited"]=checked["archive_count"]
        report["coverage_manifest_digest_sha256"]=checked["observed_sample_identity_sha256"]
        return report
    except Exception:
        raise VisionReplayPrivateError("private_vision_dynamic_replay_rejected") from None


def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest",action="append",required=True)
    parser.add_argument("--allow-personal-nonproduction-research",action="store_true")
    parser.add_argument("--first-decision-ms",type=int,required=True)
    parser.add_argument("--last-decision-ms",type=int,required=True)
    parser.add_argument("--step-hours",type=int,default=24)
    parser.add_argument("--max-candidates",type=int,default=50)
    parser.add_argument("--audit-intrabar-stress",action="store_true")
    parser.add_argument("--costed-oos",action="store_true")
    parser.add_argument("--oos-cost-bps",type=Decimal)
    parser.add_argument("--stress-margin-quote",type=Decimal)
    parser.add_argument("--stress-leverage",type=int)
    parser.add_argument("--stress-stop-fraction",type=Decimal)
    parser.add_argument("--stress-target-fraction",type=Decimal)
    parser.add_argument("--stress-maintenance-bps",type=Decimal)
    parser.add_argument("--stress-fee-bps",type=Decimal)
    parser.add_argument("--stress-slippage-bps",type=Decimal)
    parser.add_argument("--stress-funding-bps",type=Decimal)
    parser.add_argument("--stress-selection-cost-bps",type=Decimal)
    args=parser.parse_args(argv)
    try:
        stress=None
        cost=Decimal(0)
        raw=(args.stress_margin_quote,args.stress_leverage,args.stress_stop_fraction,
             args.stress_target_fraction,args.stress_maintenance_bps,
             args.stress_fee_bps,args.stress_slippage_bps,args.stress_funding_bps,
             args.stress_selection_cost_bps)
        if args.audit_intrabar_stress:
            if any(x is None for x in raw):
                raise VisionReplayPrivateError("all explicit stress inputs required")
            stress=VisionStressAssumptions(
                SyntheticMarginBasis(args.stress_margin_quote,args.stress_leverage,
                    args.stress_margin_quote*args.stress_leverage,"SYNTHETIC_USDT"),
                args.stress_stop_fraction,args.stress_target_fraction,
                args.stress_maintenance_bps,args.stress_fee_bps,args.stress_fee_bps,
                args.stress_slippage_bps,args.stress_slippage_bps,
                args.stress_funding_bps)
            cost=args.stress_selection_cost_bps
        elif any(x is not None for x in raw):
            raise VisionReplayPrivateError("stress fields without opt-in")
        if args.costed_oos != (args.oos_cost_bps is not None):
            raise VisionReplayPrivateError("explicit costed OOS opt-in and cost required")
        report=private_vision_dynamic_replay(
            manifest_paths=tuple(args.manifest),
            allow_personal_nonproduction_research=args.allow_personal_nonproduction_research,
            first_decision_ms=args.first_decision_ms,
            last_decision_ms=args.last_decision_ms,
            step_hours=args.step_hours,max_candidates=args.max_candidates,
            stress_assumptions=stress,stress_selection_cost_bps=cost,
            costed_oos_bps=args.oos_cost_bps if args.costed_oos else None)
    except Exception:
        report={"schema_version":"vision-private-dynamic-replay-v1",
                "status":"private_vision_dynamic_replay_rejected",
                "marketwide_top50_verified":False,"live_trading_authorized":False,
                "orders_sent":False,"network_requests":0,"data_stored":False}
    print(json.dumps(report,sort_keys=True,separators=(",",":")))
    return int(report["status"]!="offline_research_sample_replayed")


if __name__=="__main__":
    raise SystemExit(main())
