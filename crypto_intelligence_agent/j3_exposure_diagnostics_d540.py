"""D540: overlap and concentration of independent complete research paths.

This is NOT a portfolio, capital allocation, order or market-valued exposure.
Count full fractions at bar starts and apply all reductions at the next bar
boundary. Censor an unclosed residual at its own observation end; do not
invent an exit fill. Equal-time event deltas are combined before measuring.
"""
from __future__ import annotations

from decimal import Decimal, Context, localcontext
from heapq import heappush, heapreplace

from .j3_funding_replay_d537 import ExposureChange
from .market_data import DataValidationError
from .synthetic_intrabar_barriers import ResearchDirection

D=Decimal
ZERO=D(0)
ONE=D(1)
HOUR=3_600_000
MAX_SCENARIOS=300
MAX_TRACED_PATHS=1_000_000
_CTX=Context(prec=128)


class ExposureDiagnostics:
    """Sparse event sweep; keep only current symbol's path-count events."""
    def __init__(self,duration):
        if type(duration) is not int or duration not in (300_000,HOUR):
            raise DataValidationError("D540 invalid observation grid")
        self.duration=duration
        # [long paths, short paths, long fractions, short fractions,
        #  distinct symbols, symbols with >1 simultaneous path]
        self.events={}
        self.symbol_events={}
        self.current=None
        self.symbol_nets={}
        self.current_net=ZERO
        self.net=ZERO
        self.gain=ZERO
        self.top=[]
        self.count=0
        self.censored=0
        self.finished=False

    def _event(self,t):
        return self.events.setdefault(t,[0,0,ZERO,ZERO,0,0])

    def _delta(self,t,side,paths,fraction):
        event=self._event(t)
        event[side]+=paths
        event[2+side]+=fraction
        if paths:
            self.symbol_events[t]=self.symbol_events.get(t,0)+paths

    def _finish_symbol(self):
        if self.current is None:
            return
        active=0
        for t,delta in sorted(self.symbol_events.items()):
            previous=active
            active+=delta
            if active<0:
                raise DataValidationError("D540 inconsistent symbol exposure")
            event=self._event(t)
            event[4]+=int(active>0)-int(previous>0)
            event[5]+=int(active>1)-int(previous>1)
        if active:
            raise DataValidationError("D540 symbol exposure not conserved")
        self.symbol_nets[self.current]=self.current_net
        self.current=None
        self.current_net=ZERO
        self.symbol_events.clear()

    def record(self,*,symbol,direction,start,end,changes,residual,net):
        if (self.finished or type(symbol) is not str or not symbol
                or type(direction) is not ResearchDirection
                or type(start) is not int or type(end) is not int
                or not 0<start<end or start%self.duration or end%self.duration
                or type(changes) is not tuple or type(residual) is not D
                or type(net) is not D or not residual.is_finite() or not net.is_finite()
                or not ZERO<=residual<=ONE):
            raise DataValidationError("D540 invalid independent path")
        remaining=ONE
        last=-1
        for c in changes:
            if (type(c) is not ExposureChange or type(c.bar_index) is not int
                    or not last<c.bar_index<(end-start)//self.duration
                    or type(c.before) is not D or type(c.after) is not D
                    or not c.before.is_finite() or not c.after.is_finite()
                    or c.before!=remaining or not ZERO<=c.after<c.before):
                raise DataValidationError("D540 nonconserving path")
            remaining=c.after
            last=c.bar_index
        if remaining!=residual:
            raise DataValidationError("D540 residual and trace disagree")
        if symbol!=self.current and symbol in self.symbol_nets:
            raise DataValidationError("D540 symbol must be processed in one block")
        with localcontext(_CTX):
            if symbol!=self.current:
                self._finish_symbol()
                self.current=symbol
            side=0 if direction is ResearchDirection.LONG else 1
            self._delta(start,side,1,ONE)
            for c in changes:
                t=start+(c.bar_index+1)*self.duration
                self._delta(t,side,-int(c.after==ZERO),c.after-c.before)
            if residual:
                self._delta(end,side,-1,-residual)
                self.censored+=1
            self.count+=1
            self.net+=net
            self.current_net+=net
            if net>0:
                self.gain+=net
                if len(self.top)<5:
                    heappush(self.top,net)
                elif net>self.top[0]:
                    heapreplace(self.top,net)

    def summary(self,*,expected_count,expected_net):
        if self.finished:
            raise DataValidationError("D540 report already finalized")
        if type(expected_count) is not int or expected_count!=self.count:
            raise DataValidationError("D540 path count mismatch")
        if expected_count==0:
            if expected_net is not None:
                raise DataValidationError("D540 empty path result mismatch")
        elif type(expected_net) is not str or D(expected_net)!=self.net:
            raise DataValidationError("D540 pre-funding net mismatch")
        with localcontext(_CTX):
            self._finish_symbol()
            self.finished=True
            if sum(self.symbol_nets.values(),ZERO)!=self.net:
                raise DataValidationError("D540 symbol net mismatch")
            state=[0,0,ZERO,ZERO,0,0]
            peaks={"paths":0,"assets":0,"overlapping_assets":0,"duplicate_paths":0,
                   "long_paths":0,"short_paths":0,"gross":ZERO,"absolute_net":ZERO}
            path_ms=0
            gross_ms=ZERO
            overlap_ms=0
            previous=None
            for t,event in sorted(self.events.items()):
                if previous is not None:
                    dt=t-previous
                    path_ms+=(state[0]+state[1])*dt
                    gross_ms+=(state[2]+state[3])*dt
                    if state[5]:
                        overlap_ms+=dt
                previous=t
                state=[a+b for a,b in zip(state,event)]
                if (any(x<0 for x in state) or state[4]>state[0]+state[1]
                        or state[5]>state[4] or state[2]>state[0] or state[3]>state[1]):
                    raise DataValidationError("D540 inconsistent simultaneous exposure")
                values={"paths":state[0]+state[1],"assets":state[4],
                        "overlapping_assets":state[5],"duplicate_paths":state[0]+state[1]-state[4],
                        "long_paths":state[0],"short_paths":state[1],
                        "gross":state[2]+state[3],"absolute_net":abs(state[2]-state[3])}
                for key,value in values.items():
                    peaks[key]=max(peaks[key],value)
            if any(state):
                raise DataValidationError("D540 final exposure not conserved")
            self.events.clear()
            wins=[n for n in self.symbol_nets.values() if n>0]
            best_symbol=max(wins,default=ZERO)
            positive_symbol_net=sum(wins,ZERO)
            best_path=max(self.top,default=ZERO)
            best_five=sum(self.top,ZERO)
            def money(x):
                return format(x,"f")
            def share(x,y):
                return format((100*x/y).quantize(D("0.01")),"f") if y else None
            def hours(x):
                return format((D(x)/HOUR).quantize(D("0.000001")),"f")
            return {"path_count":self.count,"censored_open_paths":self.censored,
                    "distinct_assets_with_paths":len(self.symbol_nets),
                    "peak_concurrent_paths":peaks["paths"],
                    "peak_concurrent_assets":peaks["assets"],
                    "peak_assets_with_overlapping_paths":peaks["overlapping_assets"],
                    "peak_duplicate_paths":peaks["duplicate_paths"],
                    "peak_long_paths":peaks["long_paths"],
                    "peak_short_paths":peaks["short_paths"],
                    "peak_gross_initial_notional_equivalents":money(peaks["gross"]),
                    "peak_absolute_net_initial_notional_equivalents":money(peaks["absolute_net"]),
                    "path_hours":hours(path_ms),
                    "gross_initial_notional_equivalent_hours":hours(gross_ms),
                    "hours_with_same_asset_overlap":hours(overlap_ms),
                    "pre_funding_positive_path_sum_quote":money(self.gain),
                    "top_1_positive_path_share_percent":share(best_path,self.gain),
                    "top_5_positive_path_share_percent":share(best_five,self.gain),
                    "pre_funding_net_without_top_5_positive_paths_quote":money(self.net-best_five),
                    "positive_net_assets":len(wins),
                    "negative_net_assets":sum(n<0 for n in self.symbol_nets.values()),
                    "top_positive_asset_share_of_positive_asset_net_percent":share(best_symbol,positive_symbol_net),
                    "pre_funding_net_without_top_positive_asset_quote":money(self.net-best_symbol)}
