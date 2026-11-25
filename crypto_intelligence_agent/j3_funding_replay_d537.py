"""D537 conditional observed funding; not exchange settlement or liquidation."""
from bisect import bisect_left
from dataclasses import dataclass
from decimal import Context, Decimal, ROUND_FLOOR, ROUND_CEILING, localcontext
from hashlib import sha256
import json

from .market_data import DataValidationError, interval_duration_ms
from .synthetic_intrabar_barriers import ResearchDirection

_CTX=Context(prec=128)
_ZERO=Decimal(0)
_ONE=Decimal(1)
_QUANT=Decimal("1e-18")


@dataclass(frozen=True)
class ExposureChange:
    bar_index:int
    before:Decimal
    after:Decimal
    minimum_positive:Decimal | None = None


@dataclass(frozen=True)
class ObservedFundingResult:
    cost_low:Decimal
    cost_high:Decimal
    exposed_event_count:int


class ObservedFundingHistory:
    """Read-only symbol/partition data, conditional on D536 observed events."""
    def __init__(self,*,start,end,resolution,funding,mark):
        self.duration=interval_duration_ms(resolution)
        if (resolution not in ("1h","5m") or type(start) is not int or type(end) is not int
                or not 0<start<end or start%self.duration or end%self.duration
                or type(funding["query_coverage_complete"]) is not bool
                or type(mark["query_coverage_complete"]) is not bool):
            raise DataValidationError("D537 invalid source range")
        self.start,self.end=start,end
        self.query_complete=funding["query_coverage_complete"]
        self.rates=tuple((t,Decimal(v)) for t,v in funding["rows"])
        self.times=tuple(t for t,_ in self.rates)
        if (any(type(t) is not int or not start<=t<end or not v.is_finite() or abs(v)>1
                for t,v in self.rates)
                or any(a>=b for a,b in zip(self.times,self.times[1:]))):
            raise DataValidationError("D537 invalid observed rate sequence")
        self.marks={}
        for t,op,hi,lo,cl in mark["rows"]:
            o,h,l,c=map(Decimal,(op,hi,lo,cl))
            if (type(t) is not int or not start<=t<end or t%self.duration or t in self.marks
                    or any(not v.is_finite() or v<=0 for v in (o,h,l,c))
                    or l>min(o,h,c) or h<max(o,l,c)):
                raise DataValidationError("D537 invalid observed mark")
            self.marks[t]=(l,h)
        def digest(rows):
            return sha256(json.dumps(rows,ensure_ascii=True,separators=(",",":")).encode()).hexdigest()
        self.manifest={"funding_query_coverage_complete":self.query_complete,
            "mark_query_coverage_complete":mark["query_coverage_complete"],
            "funding_row_count":len(self.rates),"mark_row_count":len(self.marks),
            "funding_rows_sha256":digest(funding["rows"]),
            "mark_rows_sha256":digest(mark["rows"]),
            "range_ms":[start,end],"funding_calendar_verified":False}

    @classmethod
    def load(cls,home,plan,symbol,start,end,resolution):
        from .j3_derivatives_history_d536 import read_derivatives_window
        return cls(start=start,end=end,resolution=resolution,
            funding=read_derivatives_window(home,plan,"funding",symbol,start,end),
            mark=read_derivatives_window(home,plan,"mark-"+resolution,symbol,start,end))

    def cost_bounds(self,*,direction,entry_at,end_at,entry_price,notional,changes):
        """Signed cashflow bounds, using quantity before/after the reduction bar.

        Funding at the entry boundary may or may not include the new position.
        Missing query coverage or missing mark for an exposed event is not zero.
        Once fully exited, later events do not contribute. No fill time invented.
        """
        if (type(direction) is not ResearchDirection
                or type(entry_at) is not int or type(end_at) is not int
                or not self.start<=entry_at<end_at<=self.end
                or entry_at%self.duration or end_at%self.duration
                or type(entry_price) is not Decimal or not entry_price.is_finite() or entry_price<=0
                or type(notional) is not Decimal or not notional.is_finite() or notional<=0
                or type(changes) is not tuple):
            raise DataValidationError("D537 invalid conditional exposure request")
        remaining=_ONE
        previous=-1
        for change in changes:
            if (type(change) is not ExposureChange or type(change.bar_index) is not int
                    or not previous<change.bar_index<(end_at-entry_at)//self.duration
                    or type(change.before) is not Decimal or type(change.after) is not Decimal
                    or not change.before.is_finite() or not change.after.is_finite()
                    or change.before!=remaining or not _ZERO<=change.after<change.before
                    or (change.minimum_positive is not None and
                        (type(change.minimum_positive) is not Decimal
                         or not change.minimum_positive.is_finite()
                         or not _ZERO<change.minimum_positive<=change.before
                         or (change.after>0 and change.minimum_positive!=change.after)))):
                raise DataValidationError("D537 nonconserving exposure trace")
            previous=change.bar_index
            remaining=change.after
        if not self.query_complete:
            return None
        remaining=_ONE
        cursor=0
        low=high=_ZERO
        count=0
        sign=_ONE if direction is ResearchDirection.LONG else -_ONE
        with localcontext(_CTX):
            for i in range(bisect_left(self.times,entry_at),bisect_left(self.times,end_at)):
                t,rate=self.rates[i]
                index=(t-entry_at)//self.duration
                while cursor<len(changes) and changes[cursor].bar_index<index:
                    remaining=changes[cursor].after
                    cursor+=1
                if not remaining:
                    break
                qmin=(changes[cursor].after if cursor<len(changes)
                      and changes[cursor].bar_index==index else remaining)
                if t==entry_at:
                    qmin=_ZERO
                mark=self.marks.get(entry_at+index*self.duration)
                if mark is None:
                    return None
                a=sign*rate*qmin*notional*mark[0]/entry_price
                b=sign*rate*remaining*notional*mark[1]/entry_price
                low+=min(a,b).quantize(_QUANT,rounding=ROUND_FLOOR)
                high+=max(a,b).quantize(_QUANT,rounding=ROUND_CEILING)
                count+=1
        return ObservedFundingResult(low,high,count)
