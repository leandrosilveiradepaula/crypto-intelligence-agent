"""Finite, owner-local PAPER operator observation. No daemon or real orders.

Examples:
  python -m scripts.observe_paper_operator --orders orders.sqlite --positions positions.sqlite
  python -m scripts.observe_paper_operator --orders orders.sqlite --positions positions.sqlite --samples 3 --interval-ms 1000 --format html --output status.html

Only existing local synthetic SQLite fixtures. No accounts, API keys, market
data, cron, network, remote URLs, price/PnL export or trade controls.
"""
from __future__ import annotations

import argparse
from html import escape
import json
from pathlib import Path
import sys
import time

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.paper_operator_alerts import (
    PaperAlertKind, PaperAlertReport, summarize_paper_observations,
)
from crypto_intelligence_agent.paper_operator_overview import (
    inspect_local_paper_operator_overview,
)
from crypto_intelligence_agent.paper_recovery_status import (
    PaperRecoveryState, inspect_local_paper_recovery_status,
)
from scripts.inspect_paper_recovery import render_recovery_html


_KIND_LABELS = {
    PaperAlertKind.INITIAL: "Primeira leitura",
    PaperAlertKind.STATUS_CHANGED: "Estado alterado",
    PaperAlertKind.SELECTED_POSITIONS_CHANGED: "Posições selecionadas alteradas",
}
_SEVERITY_LABELS = {
    "CRITICAL": "CRÍTICO · VERIFICAÇÃO FALHOU",
    "WARNING": "ATENÇÃO · PAPER BLOQUEADO",
    "INFO_HYPOTHETICAL_ONLY": "INFORMATIVO · SOMENTE SIMULAÇÃO",
}


def paper_alert_report_json(report: PaperAlertReport) -> dict[str, object]:
    """Only allowlisted, sanitized codes and counts. Never fixture IDs."""
    if type(report) is not PaperAlertReport:
        raise DataValidationError("validated PAPER alert report required")
    return {
        "schema_version": "paper_operator_alerts_v1",
        "mode": "offline_paper",
        "sample_count": report.sample_count,
        "alert_count": len(report.events),
        "had_degraded_state": report.had_degraded_state,
        "final_state": report.final.state.value,
        "events": [
            {
                "sample": event.sample,
                "kind": event.kind.value,
                "severity": event.severity.value,
                "state": event.state.value,
                "reason": event.reason,
            }
            for event in report.events
        ],
        "selection": {
            "explicit_only": report.final_selected is not None,
            "selected_count": len(report.final_selected or ()),
            "all_positions_enumerated": False,
            "no_cross_instrument_quantity_aggregation": True,
        },
        "cross_database_atomic_snapshot_available": False,
        "financial_pnl_available": False,
        "orders_sent": False,
        "new_open_authorized": False,
        "native_stop_verified": False,
        "live_trading_authorized": False,
    }


def render_paper_alert_report_html(report: PaperAlertReport) -> str:
    """Reuse PRE8 static recovery layout, prepend only verified status events."""
    payload = paper_alert_report_json(report)
    page = render_recovery_html(
        report.final, selected=report.final_selected,
    )
    rows = []
    for event in report.events:
        label = _KIND_LABELS[event.kind]
        priority = _SEVERITY_LABELS[event.severity.value]
        rows.append(
            '<li data-observation="' + str(event.sample) + '">'
            + '<strong>' + escape(label) + '</strong> · '
            + escape(priority) + ' · '
            + escape(event.state.value) + ' · '
            + escape(event.reason) + '</li>'
        )
    report_section = (
        '<section class="selected" aria-labelledby="alert-heading">'
        '<h2 id="alert-heading">Alertas da janela PAPER</h2>'
        '<p>Leitura finita: ' + str(payload["sample_count"])
        + ' amostras. Alertas repetidos foram omitidos; ausência de alerta '
        'não comprova segurança nem estado de corretora.</p>'
        '<ol class="alert-list">' + "\n".join(rows) + '</ol>'
        '<p>Não há monitoramento contínuo, notificações push ou execução live.</p>'
        '</section>'
    )
    anchor = '    <aside class="warning" aria-label="Aviso de segurança PAPER">'
    if page.count(anchor) != 1:
        raise DataValidationError("unsafe PAPER alert display marker")
    return page.replace(anchor, report_section + "\n" + anchor)


def run_observations(
    orders: Path, positions: Path,
    *, position_ids: tuple[str, ...] | None = None,
    samples: int = 1, interval_ms: int = 0,
) -> PaperAlertReport:
    """Explicit finite owner run, never a background/continuous task."""
    if (type(samples) is not int or not 1 <= samples <= 16
            or type(interval_ms) is not int or not 0 <= interval_ms <= 10_000
            or (samples - 1) * interval_ms > 60_000):
        raise DataValidationError("PAPER observation count or delay exceeds bound")
    if position_ids is not None and (
        type(position_ids) is not tuple or not 1 <= len(position_ids) <= 128
    ):
        raise DataValidationError("explicit 1..128 fixture positions required")
    observations = []
    started = time.monotonic()
    for tick in range(samples):
        if time.monotonic() - started > 60:
            raise DataValidationError("PAPER observation deadline exceeded")
        if tick:
            time.sleep(interval_ms / 1000)
        status = (
            inspect_local_paper_recovery_status(orders, positions)
            if position_ids is None else
            inspect_local_paper_operator_overview(orders, positions, position_ids)
        )
        observations.append(status)
    return summarize_paper_observations(tuple(observations))


def main(argv: list[str] | None = None) -> int:
    cli = argparse.ArgumentParser(description="Supervisor PAPER local de janela finita")
    cli.add_argument("--orders", type=Path, required=True)
    cli.add_argument("--positions", type=Path, required=True)
    cli.add_argument("--position-id", action="append")
    cli.add_argument("--samples", type=int, default=1)
    cli.add_argument("--interval-ms", type=int, default=0)
    cli.add_argument("--format", choices=("json", "html"), default="json")
    cli.add_argument("--output", type=Path)
    args = cli.parse_args(argv)
    try:
        report = run_observations(
            args.orders, args.positions,
            position_ids=(tuple(args.position_id) if args.position_id else None),
            samples=args.samples, interval_ms=args.interval_ms,
        )
        text = (
            render_paper_alert_report_html(report)
            if args.format == "html" else
            json.dumps(paper_alert_report_json(report),
                       sort_keys=True, ensure_ascii=False) + "\n"
        )
        if args.output is None:
            sys.stdout.write(text)
        else:
            with args.output.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
        return 2 if report.had_degraded_state else 0
    except (DataValidationError, OSError, ValueError):
        print("Observação PAPER indisponível; nenhuma autorização emitida.",
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
