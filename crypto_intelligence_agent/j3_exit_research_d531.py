"""D531 explicit alternative partial-exit plans, research only."""
from __future__ import annotations
from dataclasses import replace,asdict
from decimal import Decimal
import json
import re

from .j3_combination_research_d520 import _unique,_decimal
from .j3_observed_exit_scenarios_d517 import ResearchStopManagement
from .j4_automatic_entry_materializer_d448 import PaperEntryExitPolicy
from .synthetic_partial_exits import ExitBasis,SyntheticExitTranche,SyntheticExitPlan,plan_synthetic_partial_exits
from .market_data import DataValidationError

SCHEMA="d531-exit-experiments-v1"
MAX_BYTES=16384


def _fingerprint(p,management):
    return (p.target_distances_bps,p.tranches,p.runner_floor_percent,management)


def parse_exit_experiments(raw,base):
    if type(base) is not PaperEntryExitPolicy or type(raw) is not bytes or not 2<=len(raw)<=MAX_BYTES:
        raise DataValidationError("D531 bounded exit experiments and typed base policy required")
    try:
        doc=json.loads(raw.decode("utf-8"),object_pairs_hook=_unique)
    except (ValueError,UnicodeError,TypeError) as exc:
        raise DataValidationError("D531 invalid exit experiment JSON") from exc
    if (type(doc) is not dict or set(doc)!={"schema","profiles"} or doc["schema"]!=SCHEMA
            or type(doc["profiles"]) is not list or not 1<=len(doc["profiles"])<=5):
        raise DataValidationError("D531 explicit exit profile matrix")
    out={"owner_baseline":(base,None,"Perfil de saídas de referência")}
    seen={_fingerprint(base,None)}
    for row in doc["profiles"]:
        if (type(row) is not dict or set(row)!={"name","label","targets_bps","tranches",
                                              "runner_floor_percent","management"}):
            raise DataValidationError("D531 explicit exit profile fields")
        name,label=row["name"],row["label"]
        if (type(name) is not str or re.fullmatch(r"[a-z][a-z0-9_]{1,39}",name) is None
                or name in out or type(label) is not str or not 1<=len(label)<=100
                or any(ord(c)<32 for c in label)):
            raise DataValidationError("D531 invalid exit profile identity")
        if (type(row["targets_bps"]) is not list or type(row["tranches"]) is not list
                or not 1<=len(row["targets_bps"])<=8
                or len(row["targets_bps"])!=len(row["tranches"])):
            raise DataValidationError("D531 target/tranche mismatch")
        targets=tuple(_decimal(v) for v in row["targets_bps"])
        tranches=[]
        for t in row["tranches"]:
            if (type(t) is not dict or set(t)!={"basis","percent"}
                    or type(t["basis"]) is not str):
                raise DataValidationError("D531 explicit tranche")
            try:
                basis=ExitBasis(t["basis"])
            except ValueError as exc:
                raise DataValidationError("D531 tranche basis") from exc
            tranches.append(SyntheticExitTranche(basis,_decimal(t["percent"])))
        policy=replace(base,target_distances_bps=targets,tranches=tuple(tranches),
                       runner_floor_percent=_decimal(row["runner_floor_percent"]))
        plan_synthetic_partial_exits(SyntheticExitPlan(Decimal(1),policy.tranches,
                                                        policy.runner_floor_percent))
        m=row["management"]
        if m is not None:
            if type(m) is not dict or set(m)!={"protect_after_targets","trail_after_targets","trail_distance_bps"}:
                raise DataValidationError("D531 explicit management fields")
            m=ResearchStopManagement(m["protect_after_targets"],m["trail_after_targets"],
                      None if m["trail_distance_bps"] is None else _decimal(m["trail_distance_bps"]))
            if any(n is not None and n>len(targets) for n in
                   (m.protect_after_targets,m.trail_after_targets)):
                raise DataValidationError("D531 target trigger exceeds target count")
        fingerprint=_fingerprint(policy,m)
        if fingerprint in seen:
            raise DataValidationError("D531 duplicate exit profile")
        seen.add(fingerprint)
        out[name]=(policy,m,label)
    return out


def describe_exit_experiments(variants):
    return {name:{"label":label,"target_distances_bps":[str(x) for x in p.target_distances_bps],
                  "tranches":[{"basis":t.basis.value,"percent":str(t.percent)} for t in p.tranches],
                  "runner_floor_percent":str(p.runner_floor_percent),
                  "management":asdict(m) if m is not None else None}
            for name,(p,m,label) in variants.items()}
