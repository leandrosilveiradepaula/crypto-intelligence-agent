"""J6/PRE5: fully synthetic, finite runner lifecycle demo; NEVER a broker.

Run: python3 -m scripts.demo_paper_runner_close_flow
It creates temporary PAPER journals with invented values, explicitly injects
synthetic fills, tests a crash/restart boundary, and deletes temporary files.
No external market data, order endpoints, keys, HTTP or deploy.
"""
from __future__ import annotations

import argparse
from decimal import Decimal
import json
from pathlib import Path
import tempfile

from crypto_intelligence_agent.paper_position_inspection import inspect_paper_position
from crypto_intelligence_agent.paper_position_reservations import SQLitePaperPositionJournal
from crypto_intelligence_agent.paper_runner_close_step import (
    PaperRunnerCloseStepState, step_durable_paper_runner_close,
)
from crypto_intelligence_agent.paper_runner_journal import (
    start_paper_runner_journal, append_paper_runner_mark,
)
from crypto_intelligence_agent.paper_runner_trailing import (
    PaperRunnerMark, PaperRunnerTrailPolicy, PaperRunnerTrailState,
)
from crypto_intelligence_agent.synthetic_order_lifecycle import (
    PaperOrderEffect, PaperOrderIntent, PaperOrderEvent, PaperOrderEventKind,
    PaperOrderSide, PaperVenue,
)
from crypto_intelligence_agent.synthetic_partial_exits import (
    ExitBasis, SyntheticExitPlan, SyntheticExitTranche,
)
from crypto_intelligence_agent.synthetic_position_state import SyntheticSide
from scripts.inspect_paper_positions import multi_paper_snapshot

D = Decimal
_T = 1792985000000
_POSITION_ID = "fixture_j6_e2e_runner"
_SYMBOL = "BTCUSDT"  # Pure synthetic venue ticker, never queried.


def _plan() -> SyntheticExitPlan:
    return SyntheticExitPlan(
        initial_units=D(100),
        tranches=tuple(
            SyntheticExitTranche(ExitBasis.REMAINING_BALANCE, D(x))
            for x in ("50", "60", "70")
        ),
        residual_floor_percent=D(6),
    )


def _snapshot(path: Path) -> dict[str, object]:
    selected = (inspect_paper_position(path, _POSITION_ID),)
    return multi_paper_snapshot(selected)["positions"][0]


def run_demo() -> dict[str, object]:
    """Run exactly one deterministic, isolated PAPER scenario; no network."""
    stages = []
    with tempfile.TemporaryDirectory(prefix="cia_j6_runner_demo_") as folder:
        root = Path(folder)
        position_path = root / "positions.sqlite"
        runner_path = root / "runner.sqlite"
        store = SQLitePaperPositionJournal(position_path)
        opening = PaperOrderIntent(
            intent_id="fixture_j6_e2e_open",
            fixture_signal_id="fixture_j6_e2e_signal",
            venue=PaperVenue.BINANCE_USDM, symbol=_SYMBOL,
            position_side=SyntheticSide.LONG, side=PaperOrderSide.BUY,
            effect=PaperOrderEffect.OPEN, requested_units=D(100),
            created_at_ms=_T,
        )
        opened = PaperOrderEvent(
            "fixture_j6_e2e_open_fill",PaperOrderEventKind.FILL,_T+1,D(100))
        current = store.create_position(
            position_id=_POSITION_ID, opening_intent=opening,
            opening_events=(opened,), exit_plan=_plan(),
            plan_version="fixture_j6_e2e_v1",
            synthetic_lot_step_units=D(1), as_of_ms=_T+1,
        )
        for index, units in enumerate((50, 30, 14), start=1):
            partial = PaperOrderIntent(
                intent_id=f"fixture_j6_e2e_exit_{index}",
                fixture_signal_id=f"fixture_j6_e2e_exit_signal_{index}",
                venue=opening.venue, symbol=opening.symbol,
                position_side=SyntheticSide.LONG, side=PaperOrderSide.SELL,
                effect=PaperOrderEffect.REDUCE_ONLY, requested_units=D(units),
                max_reducible_units=current.confirmed_remaining_units,
                created_at_ms=current.as_of_ms,
            )
            current = store.reserve_exit(
                _POSITION_ID, index, partial, as_of_ms=current.as_of_ms)
            fill = PaperOrderEvent(
                f"fixture_j6_e2e_partial_fill_{index}",
                PaperOrderEventKind.FILL, current.as_of_ms + 1, D(units))
            current = store.append_exit_events(
                _POSITION_ID, partial.intent_id, (fill,),
                as_of_ms=current.as_of_ms + 1)
        before = _snapshot(position_path)
        if (before["runner_readiness"] != "RUNNER_CONFIRMED_NOT_PROTECTED"
                or before["confirmed_remaining_units"] != "6"):
            raise RuntimeError("synthetic partial exit conservation failed")
        stages.append("partials_confirmed_paper_only")

        policy = PaperRunnerTrailPolicy(D(100), D(50), 5000, 5000)
        first_mark = PaperRunnerMark(_SYMBOL, _T+100, D(100))
        start_paper_runner_journal(
            runner_path, position_path, _POSITION_ID,
            policy=policy, first_mark=first_mark, as_of_ms=_T+100)
        for n, price in enumerate((D(102), D(103), D(102)), start=1):
            trigger = append_paper_runner_mark(
                runner_path, position_path, _POSITION_ID,
                PaperRunnerMark(_SYMBOL, _T+100+1000*n, price),
                policy=policy, as_of_ms=_T+100+1000*n)
        if trigger.state is not PaperRunnerTrailState.TRIGGERED_HYPOTHETICAL_ONLY:
            raise RuntimeError("synthetic trailing trigger not observed")
        stages.append("trailing_trigger_hypothetical_only")

        reserved = step_durable_paper_runner_close(
            runner_path, position_path, _POSITION_ID,
            policy=policy, as_of_ms=_T+3100)
        if (reserved.state is not PaperRunnerCloseStepState.RESERVED_PAPER_ONLY
                or reserved.runner_order_count != 1
                or reserved.runner_reserved_unfilled_units != D(6)):
            raise RuntimeError("synthetic runner reservation failed")
        pending = _snapshot(position_path)
        if (pending["runner_readiness"] != "RUNNER_EXIT_PENDING_RECONCILIATION"
                or pending["runner_reserved_unfilled_units"] != "6"
                or pending["confirmed_remaining_units"] != "6"):
            raise RuntimeError("PAPER pending runner UI differs from ledger")
        stages.append("runner_exit_reserved_no_fill")

        # Recover from the same durable SQLite file, as after process restart.
        replay = step_durable_paper_runner_close(
            runner_path, position_path, _POSITION_ID,
            policy=policy, as_of_ms=_T+3200)
        if (replay.state is not
                PaperRunnerCloseStepState.PENDING_RECONCILIATION_PAPER_ONLY
                or replay.runner_order_count != 1
                or replay.created_intent_id is not None):
            raise RuntimeError("restart duplicated synthetic runner reservation")
        stages.append("restart_without_duplicate")

        # Deliberately insert a synthetic FILL for demonstration only;
        # the automatic step above does NOT generate fills or exchange orders.
        simulated_fill = PaperOrderEvent(
            "fixture_j6_e2e_runner_explicit_fill",
            PaperOrderEventKind.FILL, _T+3201, D(6))
        store.append_exit_events(
            _POSITION_ID, reserved.created_intent_id, (simulated_fill,),
            as_of_ms=_T+3201)
        terminal = step_durable_paper_runner_close(
            runner_path, position_path, _POSITION_ID,
            policy=policy, as_of_ms=_T+3202)
        final = _snapshot(position_path)
        if (terminal.state is not PaperRunnerCloseStepState.CLOSED_PAPER_ONLY
                or terminal.runner_order_count != 1
                or final["runner_readiness"] != "RUNNER_CLOSED_PAPER_ONLY"
                or final["confirmed_remaining_units"] != "0"
                or final["filled_exit_units"] != "100"
                or final["native_stop_verified"] or final["trailing_stop_active"]):
            raise RuntimeError("PAPER closing ledger and UI disagree")
        stages.append("runner_closed_by_explicit_synthetic_fill")

    return {
        "modalidade": "offline_paper",
        "cenario": "simulacao_ficticia_j6_runner",
        "etapas": stages,
        "posicao_inicial_unidades_ficticias": "100",
        "parciais_preenchidas_unidades_ficticias": "94",
        "runner_fechado_unidades_ficticias": "6",
        "saldo_final_unidades_ficticias": "0",
        "intencoes_runner_distintas": 1,
        "fill_runner_injetado_explicitamente_em_fixture": True,
        "dados_de_mercado_reais": False,
        "ordens_reais_enviadas": False,
        "stop_nativo_verificado": False,
        "trading_live_autorizado": False,
        "lucro_financeiro_calculado": False,
        "rede_utilizada": False,
        "arquivos_persistentes_criados": False,
    }


def main(argv: list[str] | None = None) -> None:
    argparse.ArgumentParser(
        description="Demonstra fechamento residual PAPER, sem corretora ou rede."
    ).parse_args(argv)
    print(json.dumps(run_demo(), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
