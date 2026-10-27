"""Runnable J6 offline-only automatic PAPER batch and crash/restart demo.

Run: python3 -m scripts.demo_durable_offline_paper_batch
Optional: --demonstrar-pausa  (shows operator kill-switch suppressing OPEN)

Uses deterministic MADE-UP candles and fictional account risk. No external
files, market access, credentials, real broker orders or persistent deployment.
The temporary SQLite files are destroyed when this command exits.
"""
from __future__ import annotations

import argparse
from decimal import Decimal
import json
from pathlib import Path
import tempfile

from crypto_intelligence_agent.market_data import ClosedCandle, MARKET
from crypto_intelligence_agent.offline_paper_batch import run_durable_offline_paper_batch
from crypto_intelligence_agent.paper_order_store import SQLitePaperOrderJournal
from crypto_intelligence_agent.paper_position_reservations import SQLitePaperPositionJournal
from crypto_intelligence_agent.paper_risk_gate import PaperRiskLimits, PaperRiskObservation
from crypto_intelligence_agent.synthetic_entry_hypotheses import CompressionBreakoutConfig
from crypto_intelligence_agent.synthetic_feature_engine import FeatureConfig
from crypto_intelligence_agent.synthetic_order_lifecycle import PaperVenue

D = Decimal
HOUR_MS = 3_600_000
ROWS = (
    ("100", "110", "90", "10"),
    ("101", "111", "91", "10"),
    ("101", "102", "100", "10"),
    ("101", "102", "100", "10"),
    ("101", "102", "100", "10"),
    ("105", "106", "101", "50"),
    ("111", "112", "104", "100"),
    ("111", "112", "110", "10"),
    ("111", "112", "110", "10"),
    ("111", "112", "110", "10"),
)


def _fixture_inputs():
    rows = tuple(
        ClosedCandle(
            "fixture_exchange", MARKET, "BTCUSDT", "1h",
            (10 + i) * HOUR_MS, (11 + i) * HOUR_MS - 1,
            D(close), D(high), D(low), D(close),
            D(1), D(volume), "synthetic_fixture",
        )
        for i, (close, high, low, volume) in enumerate(ROWS)
    )
    observations = tuple(
        PaperRiskObservation(
            venue=PaperVenue.BINANCE_USDM,
            symbol="BTCUSDT", quote_currency="USDT",
            observed_at_ms=c.close_time_ms + 1_000,
            mark_price_quote=D(100),  # deliberately not any real BTC price
            symbol_exposure_quote=D(0),
            portfolio_exposure_quote=D(0),
            realized_loss_today_quote=D(0),
            pending_open_orders=0,
            unresolved_open_exists=False,
            kill_switch_active=False,
        )
        for c in rows
    )
    return rows, observations


def run_demo(*, demonstrar_pausa: bool = False) -> dict[str, object]:
    if type(demonstrar_pausa) is not bool:
        raise ValueError("only an explicit synthetic pause switch is supported")
    candles, observations = _fixture_inputs()
    strategy = CompressionBreakoutConfig(
        features=FeatureConfig(2, 2, 2, 2),
        compression_bars=2,
        baseline_bars=2,
        max_atr_ratio=D("0.6"),
        min_quote_volume_ratio=D(2),
        cooldown_bars=1,
    )
    limits = PaperRiskLimits(
        max_order_notional_quote=D(400),
        max_symbol_exposure_quote=D(1000),
        max_portfolio_exposure_quote=D(2000),
        max_realized_loss_today_quote=D(50),
        max_pending_open_orders=1,
        max_market_age_ms=1000,
    )
    with tempfile.TemporaryDirectory(prefix="cia_j6_synthetic_batch_") as root:
        base = Path(root)
        orders = SQLitePaperOrderJournal(base / "orders.sqlite")
        positions_path = base / "positions.sqlite"
        SQLitePaperPositionJournal(positions_path)
        common = dict(
            observations=observations, strategy=strategy,
            venue=PaperVenue.BINANCE_USDM, requested_units=D(2),
            limits=limits, position_journal_path=positions_path,
            bootstrap_candles=5, max_candles=20,
        )
        bootstrap = run_durable_offline_paper_batch(
            candles, journal=orders, max_new_steps=1, **common,
        )
        if demonstrar_pausa:
            orders.set_local_kill_switch(
                pause=True, expected_sequence=0,
                changed_at_ms=candles[4].close_time_ms + 1001,
            )
        # Re-open journal object to mimic a process restart; same SQLite file.
        orders = SQLitePaperOrderJournal(base / "orders.sqlite")
        middle = run_durable_offline_paper_batch(
            candles, journal=orders, max_new_steps=1, **common,
        )
        if demonstrar_pausa:
            orders.set_local_kill_switch(
                pause=False, expected_sequence=1,
                changed_at_ms=candles[5].close_time_ms + 1001,
                acknowledge_resume=True,
            )
        final = run_durable_offline_paper_batch(
            candles, journal=orders, max_new_steps=64, **common,
        )
        noop = run_durable_offline_paper_batch(
            candles, journal=SQLitePaperOrderJournal(base / "orders.sqlite"),
            max_new_steps=64, **common,
        )
        expected = 0 if demonstrar_pausa else 1
        if (bootstrap.processed_steps != 1
                or middle.starting_checkpoint_count != 5
                or middle.final_checkpoint_count != 6
                or middle.reserved_open_intents != expected
                or final.final_checkpoint_count != len(candles)
                or not final.all_supplied_candles_processed
                or noop.processed_steps != 0
                or middle.orders_sent or final.orders_sent):
            raise RuntimeError("synthetic J6 batch, pause or recovery invariant violated")
    return {
        "modalidade": "simulacao_paper_totalmente_offline",
        "base": "candles_e_risco_100_por_cento_ficticios",
        "ciclos_iniciais": bootstrap.processed_steps + middle.processed_steps,
        "ciclos_restantes": final.processed_steps,
        "velas_avaliadas": len(candles),
        "checkpoint_final_candles": final.final_checkpoint_count,
        "retomada_apos_reabertura_sqlite": middle.recovered_prior_checkpoint,
        "reservas_open_paper_pendentes": middle.reserved_open_intents,
        "pausa_paper_demonstrada": demonstrar_pausa,
        "reprocessamento_seguro_sem_novas_reservas": noop.processed_steps == 0,
        "dados_de_mercado_reais": False,
        "ordens_reais_enviadas": False,
        "resultado_financeiro_validado": False,
        "aprovado_para_producao": False,
        "persistencia": "sqlite_temporario_eliminado_ao_sair",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demonstrar-pausa", action="store_true")
    args = parser.parse_args(argv)
    print(json.dumps(
        run_demo(demonstrar_pausa=args.demonstrar_pausa),
        sort_keys=True, ensure_ascii=False,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
