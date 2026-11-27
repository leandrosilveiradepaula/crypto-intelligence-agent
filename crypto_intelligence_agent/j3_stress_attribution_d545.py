"""D545 additive risk attribution, not liquidation-adjusted returns.

Keep D538 possible breach separate from mark-only evidence in later bars
with unchanged positive quantity. Split the D537 matched conditional PnL
by D538 status; missing stress remains a separate bucket. Never zero or
remove a trade, invent liquidation cashflows or claim survival.
"""
from decimal import Decimal, Context, localcontext

from .market_data import DataValidationError

ZERO=Decimal(0)
_CTX=Context(prec=128)
STAGES=("entry_bar","reduction_bar","unchanged_bar")
BUCKETS=("possible_breach","no_observed_breach","stress_unavailable")
COUNTS=("fixed_exposure_mark_only_paths",)+tuple("first_breach_"+s+"_paths" for s in STAGES)


def attribution_fields(prefix):
    p=prefix+"attribution_"
    result={p+k:0 for k in COUNTS}
    for b in BUCKETS:
        result[p+b+"_paths"]=0
        result[p+b+"_net_low_quote"]=ZERO
        result[p+b+"_net_high_quote"]=ZERO
    return result


def record_attribution(row,prefix,item,bounds):
    p=prefix+"attribution_"
    if item is not None:
        breached=item.first_possible_breach_bar is not None
        if (breached!=(item.first_breach_stage in STAGES)
                or (item.fixed_exposure_mark_only_breach and not breached)
                or bounds is None):
            raise DataValidationError("D545 inconsistent evaluated stress")
        if breached:
            row[p+"first_breach_"+item.first_breach_stage+"_paths"]+=1
        row[p+"fixed_exposure_mark_only_paths"]+=int(item.fixed_exposure_mark_only_breach)
        bucket="possible_breach" if breached else "no_observed_breach"
    else:
        bucket="stress_unavailable"
    if bounds is not None:
        lo,hi=bounds
        if lo>hi:
            raise DataValidationError("D545 inverted conditional bounds")
        row[p+bucket+"_paths"]+=1
        row[p+bucket+"_net_low_quote"]+=lo
        row[p+bucket+"_net_high_quote"]+=hi


def _validate(row,prefix,read):
    p=prefix+"attribution_"
    keys=attribution_fields(prefix)
    if not any(k in row for k in keys):
        if read:
            return None
        raise DataValidationError("D545 missing attribution")
    def require(ok):
        if not ok:
            raise DataValidationError("D545 inconsistent conditional attribution")
    def count(k):
        n=row[k]
        require(type(n) is int and n>=0)
        return n
    def value(k,n):
        v=row[k]
        if read:
            if not n:
                require(v is None)
                return ZERO
            require(type(v) is str and len(v)<=128)
            v=Decimal(v)
        require(type(v) is Decimal and v.is_finite() and (n>0 or v==ZERO))
        return v
    try:
        matched=count("funding_matched_path_count")
        possible=count(prefix+"possible_breach_count")
        evaluated=count(prefix+"evaluated_count")
        unavailable=count(prefix+"unavailable_count")
        clear=count(prefix+"no_observed_breach_count")
        fixed=count(p+"fixed_exposure_mark_only_paths")
        stages={s:count(p+"first_breach_"+s+"_paths") for s in STAGES}
        require(sum(stages.values())==possible and fixed<=possible and evaluated==possible+clear)
        n={b:count(p+b+"_paths") for b in BUCKETS}
        require(n["possible_breach"]==possible and n["no_observed_breach"]==clear
                and n["stress_unavailable"]<=unavailable and sum(n.values())==matched)
        sums={}
        with localcontext(_CTX):
            for b in BUCKETS:
                lo=value(p+b+"_net_low_quote",n[b])
                hi=value(p+b+"_net_high_quote",n[b])
                require(lo<=hi)
                sums[b]=(lo,hi)
            for i,k in enumerate(("low","high")):
                require(sum((v[i] for v in sums.values()),ZERO)==
                        value("funding_matched_net_"+k+"_quote",matched))
        return {"fixed_exposure_mark_only_paths":fixed,
                "possible_without_fixed_exposure_mark_only_paths":possible-fixed,
                "first_possible_breach_stage_paths":stages,
                "matched_pnl_by_stress_status":{
                    b:{"paths":n[b],"conditional_net_range_quote":
                        [format(v,"f") for v in sums[b]] if n[b] else [None,None]}
                    for b in BUCKETS}}
    except (KeyError,TypeError,ValueError,ArithmeticError) as exc:
        raise DataValidationError("D545 malformed conditional attribution") from exc


def format_attribution(row,prefix):
    _validate(row,prefix,False)
    p=prefix+"attribution_"
    for b in BUCKETS:
        for k in ("low","high"):
            key=p+b+"_net_"+k+"_quote"
            row[key]=format(row[key],"f") if row[p+b+"_paths"] else None


def decode_attribution(row,prefix):
    """Return None for old reports; never fabricate new metrics for D544."""
    return _validate(row,prefix,True)
