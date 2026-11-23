"""D453: explicitly opted-in owner CLI for a resident Bybit PUBLIC/PAPER watcher.

It never sets up a service, reads private exchange credentials, touches J1 or
sends a venue order. A systemd unit/release requires a separate approval.
Config is an owner-only local research JSON, NOT an exchange trading profile.
"""
from __future__ import annotations

import argparse
from decimal import Decimal
import json
import os
from pathlib import Path
import signal

from crypto_intelligence_agent.bybit_public_ticker_supervisor_d386 import TickerLeaseBudget
from crypto_intelligence_agent.bybit_ws_supervisor import (
    MAX_FRAMES as MAX_KLINE_WS_FRAMES, WSRunBudget,
)
from crypto_intelligence_agent.j2_j4_dual_public_supervisor_d450 import DualPaperLeaseBudget
from crypto_intelligence_agent.j2_j4_public_paper_cycle_d449 import PaperPublicCycleConfig
from crypto_intelligence_agent.j2_j4_resident_paper_operator_d453 import (
    ResidentPaperRunPolicy, run_resident_paper_observer,
)
from crypto_intelligence_agent.j2_observed_paper_entry_d447 import ObservedPaperEntryPolicy
from crypto_intelligence_agent.j4_automatic_entry_materializer_d448 import PaperEntryExitPolicy
from crypto_intelligence_agent.j4_private_paper_ws_operator_d425 import (
    _private_directory, _owner_file,
)
from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.paper_risk_gate import PaperRiskLimits
from crypto_intelligence_agent.synthetic_entry_hypotheses import CompressionBreakoutConfig
from crypto_intelligence_agent.synthetic_feature_engine import FeatureConfig
from crypto_intelligence_agent.synthetic_partial_exits import ExitBasis, SyntheticExitTranche
from crypto_intelligence_agent.synthetic_position_state import SyntheticLeverageSettings


def _unique_pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise DataValidationError("D453 duplicate owner policy JSON key")
        out[key] = value
    return out


def _exact_keys(value, keys: set[str], label: str):
    if type(value) is not dict or set(value) != keys:
        raise DataValidationError("D453 invalid " + label + " policy structure")
    return value


def _d(value, label: str) -> Decimal:
    if type(value) is not str or len(value) > 64:
        raise DataValidationError("D453 " + label + " must be an exact decimal string")
    try:
        number = Decimal(value)
    except ArithmeticError as exc:
        raise DataValidationError("D453 invalid Decimal " + label) from exc
    if not number.is_finite():
        raise DataValidationError("D453 nonfinite Decimal " + label)
    return number


def read_owner_paper_policy(path: Path) -> PaperPublicCycleConfig:
    """No defaults or float conversion for financial settings; 0600 only."""
    if (not isinstance(path, Path) or not path.is_absolute()
            or path.name.startswith(".") or path.suffix != ".json"):
        raise DataValidationError("D453 absolute ordinary owner JSON policy required")
    if path.is_symlink():
        raise DataValidationError("D453 owner policy symlink forbidden")
    home = _private_directory(path.parent)
    try:
        fd = _owner_file(home, path.name)
    except OSError:
        raise DataValidationError("D453 owner policy missing or unsafe") from None
    with os.fdopen(fd, "rb") as stream:
        data = stream.read(8193)
    if not 2 <= len(data) <= 8192:
        raise DataValidationError("D453 owner policy size exceeds bound")
    try:
        document = json.loads(
            data.decode("ascii"), object_pairs_hook=_unique_pairs,
            parse_float=lambda _: (_ for _ in ()).throw(DataValidationError("D453 float JSON forbidden")),
            parse_constant=lambda _: (_ for _ in ()).throw(DataValidationError("D453 nonfinite JSON forbidden")),
        )
    except (ValueError, UnicodeDecodeError, TypeError) as exc:
        raise DataValidationError("D453 malformed owner PAPER policy") from exc
    root = _exact_keys(
        document, {"schema_version", "research", "paper", "risk"},
        "root",
    )
    if root["schema_version"] != "d453-public-paper-research-policy-v1":
        raise DataValidationError("D453 unknown owner policy version")
    required_research_keys = {
        "ema_period", "atr_period", "extrema_period", "quote_volume_period",
        "compression_bars", "baseline_bars", "max_atr_ratio",
        "min_quote_volume_ratio", "cooldown_bars",
    }
    r = root["research"]
    optional_research_keys = {
        "experimental_paper_relaxation", "entry_mode", "ema_cross_periods",
    }
    if (type(r) is not dict
            or not required_research_keys.issubset(r)
            or set(r) - required_research_keys - optional_research_keys):
        raise DataValidationError("D453 invalid research policy structure")
    paper_relaxed = r.get("experimental_paper_relaxation", False)
    if type(paper_relaxed) is not bool:
        raise DataValidationError("D485 paper relaxation must be explicit boolean")
    features = FeatureConfig(
        r["ema_period"], r["atr_period"],
        r["extrema_period"], r["quote_volume_period"],
    )
    research = CompressionBreakoutConfig(
        features, r["compression_bars"], r["baseline_bars"],
        _d(r["max_atr_ratio"], "ATR ratio"),
        _d(r["min_quote_volume_ratio"], "volume ratio"),
        r["cooldown_bars"],
        experimental_paper_relaxation=paper_relaxed,
        entry_mode=r.get("entry_mode", "breakout"),
        ema_cross_periods=(
            tuple(r["ema_cross_periods"])
            if type(r.get("ema_cross_periods")) is list else
            r.get("ema_cross_periods")
        ),
    )
    p = _exact_keys(root["paper"], {
        "leverage", "margin_quote", "stop_distance_bps",
        "target_distances_bps", "tranches", "runner_floor_percent",
        "synthetic_lot_step_units", "entry_fee_bps", "exit_fee_bps",
        "entry_adverse_slippage_bps", "exit_adverse_slippage_bps",
        "max_spread_bps", "max_book_participation_bps",
        "min_fill_latency_ms", "max_fill_wait_ms",
    }, "paper")
    if (type(p["tranches"]) is not list
            or type(p["target_distances_bps"]) is not list
            or not 1 <= len(p["tranches"]) == len(p["target_distances_bps"]) <= 64):
        raise DataValidationError("D453 one exit tranche per explicitly declared target required")
    tranche = []
    for step in p["tranches"]:
        _exact_keys(step, {"basis", "percent"}, "exit tranche")
        tranche.append(SyntheticExitTranche(
            ExitBasis(step["basis"]),
            _d(step["percent"], "tranche percent"),
        ))
    targets = tuple(_d(v, "target bps") for v in p["target_distances_bps"])
    exits = PaperEntryExitPolicy(
        stop_distance_bps=_d(p["stop_distance_bps"], "stop bps"),
        target_distances_bps=targets, tranches=tuple(tranche),
        runner_floor_percent=_d(p["runner_floor_percent"], "runner percent"),
        synthetic_lot_step_units=_d(p["synthetic_lot_step_units"], "lot step"),
        entry_fee_bps=_d(p["entry_fee_bps"], "entry fee"),
        exit_fee_bps=_d(p["exit_fee_bps"], "exit fee"),
        entry_adverse_slippage_bps=_d(p["entry_adverse_slippage_bps"], "entry slippage"),
        exit_adverse_slippage_bps=_d(p["exit_adverse_slippage_bps"], "exit slippage"),
        max_spread_bps=_d(p["max_spread_bps"], "max spread"),
        max_book_participation_bps=_d(p["max_book_participation_bps"], "book participation"),
        min_fill_latency_ms=p["min_fill_latency_ms"],
        max_fill_wait_ms=p["max_fill_wait_ms"],
    )
    entry = ObservedPaperEntryPolicy(
        target_distance_bps=targets[0],
        stop_distance_bps=exits.stop_distance_bps,
        first_tranche_fraction=tranche[0].percent / Decimal(100),
        entry_fee_bps=exits.entry_fee_bps,
        exit_fee_bps=exits.exit_fee_bps,
        entry_adverse_slippage_bps=exits.entry_adverse_slippage_bps,
        exit_adverse_slippage_bps=exits.exit_adverse_slippage_bps,
    )
    risk = _exact_keys(root["risk"], {
        "max_order_notional_quote", "max_symbol_exposure_quote",
        "max_portfolio_exposure_quote", "max_realized_loss_today_quote",
        "max_pending_open_orders", "max_market_age_ms",
    }, "risk")
    limits = PaperRiskLimits(
        max_order_notional_quote=_d(risk["max_order_notional_quote"], "order cap"),
        max_symbol_exposure_quote=_d(risk["max_symbol_exposure_quote"], "symbol cap"),
        max_portfolio_exposure_quote=_d(risk["max_portfolio_exposure_quote"], "portfolio cap"),
        max_realized_loss_today_quote=_d(risk["max_realized_loss_today_quote"], "daily loss cap"),
        max_pending_open_orders=risk["max_pending_open_orders"],
        max_market_age_ms=risk["max_market_age_ms"],
    )
    return PaperPublicCycleConfig(
        research=research, entry=entry, exits=exits, limits=limits,
        leverage=SyntheticLeverageSettings(p["leverage"]),
        margin_quote=_d(p["margin_quote"], "margin quote"),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Observe public Bybit candles + ticker and hypothetical PAPER only",
    )
    parser.add_argument("--j2-directory", required=True, type=Path)
    parser.add_argument("--paper-directory", required=True, type=Path)
    parser.add_argument("--policy-file", required=True, type=Path)
    parser.add_argument("--rest-warmup-filename", type=str)
    parser.add_argument("--auto-capture-rest-warmup", action="store_true")
    parser.add_argument("--lease-seconds", type=int, default=60)
    parser.add_argument("--public-ws-sessions", type=int, default=3,
                        help="1..3 bounded public WSS transport attempts per lease")
    parser.add_argument("--max-cycles", type=int, default=None)
    parser.add_argument("--pause-seconds", type=float, default=1.0)
    parser.add_argument(
        "--paper-demo-ignore-book-depth", action="store_true",
        help="PAPER DEMO ONLY: assume full fill at public BBO despite displayed size; no broker orders",
    )
    for flag in (
        "allow-public-network", "allow-public-websocket",
        "confirm-personal-readonly-research", "confirm-region-eligible",
        "confirm-public-data-rights", "enable-hypothetical-paper-cycle",
    ):
        parser.add_argument("--" + flag, action="store_true")
    args = parser.parse_args(argv)
    if not all((
        args.allow_public_network, args.allow_public_websocket,
        args.confirm_personal_readonly_research, args.confirm_region_eligible,
        args.confirm_public_data_rights, args.enable_hypothetical_paper_cycle,
    )):
        print(json.dumps({
            "status": "six_explicit_paper_public_data_optins_required",
            "orders_sent": False,
        }, sort_keys=True))
        return 2
    config = read_owner_paper_policy(args.policy_file)
    if args.paper_demo_ignore_book_depth:
        from dataclasses import replace
        config = replace(config, paper_demo_ignore_book_depth=True)
    stopping = {"requested": False}
    def graceful_stop(_signal, _frame):
        stopping["requested"] = True
    signal.signal(signal.SIGINT, graceful_stop)
    signal.signal(signal.SIGTERM, graceful_stop)
    report = run_resident_paper_observer(
        private_j2_directory=args.j2_directory,
        private_paper_directory=args.paper_directory,
        config=config, policy=ResidentPaperRunPolicy(
            DualPaperLeaseBudget(
                # D478: real D476 hour-long leases exhausted the previous
                # fixed 50k kline-frame cap before the hourly close. Scale
                # for 50 topics, without exceeding the supervisor hard cap.
                WSRunBudget(
                    max_sessions=args.public_ws_sessions,
                    max_frames=min(
                        MAX_KLINE_WS_FRAMES,
                        max(50_000, args.lease_seconds * 64),
                    ),
                    max_seconds=args.lease_seconds,
                ),
                # A 50-symbol ticker stream can produce >150 market
                # frames/sec. Keeping the default 50k cap for a 25min
                # public lease would end before the hourly candle close.
                # Scale the bounded ticker frame budget with requested
                # seconds, never above D386's five-million hard limit.
                TickerLeaseBudget(
                    max_sessions=args.public_ws_sessions,
                    max_frames=min(
                        5_000_000,
                        max(50_000, args.lease_seconds * 1000),
                    ),
                    max_seconds=args.lease_seconds,
                ),
            ),
            restart_pause_seconds=args.pause_seconds,
            max_cycles=args.max_cycles,
        ),
        allow_public_network=True, allow_public_websocket=True,
        confirm_personal_readonly_research=True,
        confirm_region_eligible=True, confirm_public_data_rights=True,
        enable_hypothetical_paper_cycle=True,
        should_stop=lambda: stopping["requested"],
        rest_warmup_filename=args.rest_warmup_filename,
        auto_capture_rest_warmup=args.auto_capture_rest_warmup,
    )
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report["status"] == "bounded_run_completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
