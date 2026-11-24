"""D511: aggregate existing J5 PAPER projections without another financial ledger.

The window is the visible last 50 journal entries plus any pinned active
positions. All monetary outcomes come from D454 priced, hypothetical FILLs;
funding and actual exchange outcomes remain unknown. No mark-to-market,
capital return, OOS validity or live risk protections are inferred.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, localcontext

from .market_data import DataValidationError

SCHEMA = "d511-observed-paper-closed-scorecard-v1"


def _money(value: object, field: str) -> Decimal | None:
    if value is None:
        return None
    if type(value) is not str or not 1 <= len(value) <= 100:
        raise DataValidationError("D511 invalid PAPER decimal: " + field)
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise DataValidationError("D511 invalid PAPER decimal: " + field) from exc
    if not number.is_finite() or number.adjusted() > 30:
        raise DataValidationError("D511 nonfinite/out-of-bounds PAPER value")
    return number


def paper_closed_scorecard(
    positions: list[dict], *, total_positions: int, total_closed_positions: int,
) -> dict:
    """Summarize ONLY existing owner-checked J5 projected positions.

    Results for OPEN/PARTIAL positions are never counted as fully realized.
    Older history outside the screen is explicitly excluded. Drawdown is
    based on the sequence of CLOSED trade results, not intrabar equity.
    """
    if (type(positions) is not list or len(positions) > 100
            or type(total_positions) is not int or total_positions < 0
            or type(total_closed_positions) is not int
            or not 0 <= total_closed_positions <= total_positions
            or len(positions) > total_positions):
        raise DataValidationError("D511 impossible PAPER scorecard cohort")
    closed = []
    active = 0
    with localcontext() as ctx:
        ctx.prec = 50
        for p in positions:
            if (type(p) is not dict
                    or p.get("status") not in ("OPEN", "PARTIAL", "CLOSED")
                    or p.get("real_orders_sent") is not False
                    or p.get("funding_not_verified") is not True
                    or p.get("native_stop_verified") is not False
                    or type(p.get("opened_at_ms")) is not int
                    or type(p.get("as_of_ms")) is not int
                    or not 0 < p["opened_at_ms"] <= p["as_of_ms"]
                    or type(p.get("side")) is not str
                    or p["side"] not in ("LONG", "SHORT")
                    or type(p.get("symbol")) is not str
                    or not p["symbol"]):
                raise DataValidationError("D511 invalid projected PAPER position")
            margin = _money(p.get("requested_margin_quote"), "margin")
            if margin is not None and margin <= 0:
                raise DataValidationError("D511 invalid requested PAPER margin")
            leverage = p.get("leverage_at_intent")
            if leverage is not None and (type(leverage) is not int or leverage <= 0):
                raise DataValidationError("D511 invalid PAPER opening leverage")
            value = _money(p.get("conditional_result_before_funding_quote"), "pnl")
            if p["status"] != "CLOSED":
                active += 1
                continue
            closed.append((p["as_of_ms"], p["opened_at_ms"], p["symbol"],
                           p["side"], value))
        if len(closed) > total_closed_positions:
            raise DataValidationError("D511 CLOSED count exceeds owner journal")
        priced = sorted((r for r in closed if r[4] is not None),
                        key=lambda r: r[:4])
        positives = [r[4] for r in priced if r[4] > 0]
        negatives = [r[4] for r in priced if r[4] < 0]
        wins, losses = len(positives), len(negatives)
        flat = len(priced) - wins - losses
        cumulative = peak = max_drawdown = Decimal(0)
        for record in priced:
            cumulative += record[4]
            peak = max(peak, cumulative)
            max_drawdown = max(max_drawdown, peak - cumulative)
        net = cumulative if priced else None
        win_rate = (format((Decimal(100) * wins / len(priced))
                           .quantize(Decimal("0.01")), "f")
                    if priced else None)
        profit_factor = (
            format(sum(positives, Decimal(0)) /
                   -sum(negatives, Decimal(0)), "f") if losses else None
        )
    return {
        "schema_version": SCHEMA,
        "status": "priced_closed_sample" if priced else "no_priced_closed_positions",
        "source": "owner_only_local_paper_sqlite_d454_priced_fills",
        "sample_positions": len(positions),
        "sample_active_positions": active,
        "sample_closed_positions": len(closed),
        "total_closed_positions_in_journal": total_closed_positions,
        "sample_closed_priced": len(priced),
        "sample_closed_unpriced": len(closed) - len(priced),
        "sample_winning_closed": wins,
        "sample_losing_closed": losses,
        "sample_flat_closed": flat,
        "conditional_closed_net_before_funding_quote": (
            format(net, "f") if net is not None else None),
        "conditional_closed_winners_quote": format(sum(positives, Decimal(0)), "f")
            if priced else None,
        "conditional_closed_losers_quote": format(sum(negatives, Decimal(0)), "f")
            if priced else None,
        "max_drawdown_closed_trade_sequence_quote": (
            format(max_drawdown, "f") if priced else None),
        "priced_closed_win_rate_percent": win_rate,
        "priced_closed_profit_factor": profit_factor,
        "window_covers_every_closed_position": len(closed) == total_closed_positions,
        "priced_covers_every_closed_position": (
            total_closed_positions > 0 and len(priced) == total_closed_positions),
        "intrabar_drawdown_or_liquidation_verified": False,
        "funding_settlement_verified": False,
        "exchange_execution_verified": False,
        "performance_out_of_sample_verified": False,
        "real_account_pnl_available": False,
        "orders_sent": False,
        "approved_for_live_use": False,
    }
