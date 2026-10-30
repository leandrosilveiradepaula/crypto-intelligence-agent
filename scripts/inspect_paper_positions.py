"""J5/PRE5: view explicitly selected saved PAPER positions, never an account.

Run:
  python3 -m scripts.inspect_paper_positions --journal /existing/paper.sqlite \\
    --position-id fixture_first --position-id fixture_second --output /tmp/positions.html

All positions share ONE SQLite mode=ro read snapshot. No wildcard/list all,
external JSON, market feed, money, positions from real accounts, or order API.
"""
from __future__ import annotations

import argparse
from decimal import Decimal
from html import escape
import json
from pathlib import Path
import re
import sys

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.paper_runner_journal import load_paper_runner_journal
from crypto_intelligence_agent.paper_runner_trailing import PaperRunnerTrailPolicy, PaperRunnerTrailReport
from crypto_intelligence_agent.paper_position_inspection import inspect_paper_position
from crypto_intelligence_agent.paper_position_inspection import (
    PaperPositionInspection, inspect_paper_positions,
)
from scripts.inspect_paper_position import paper_position_snapshot
from scripts.render_paper_dashboard import _audit_offline_template


TEMPLATE = Path(__file__).resolve().parent.parent / "web" / "paper-positions-template.html"
_SCHEMA = "paper_positions_snapshot_v1"


_RUNNER_LABELS = {
    "NO_RESIDUAL_RUNNER_CONFIGURED": "Sem runner residual configurado",
    "PENDING_EXIT_RECONCILIATION": "Saída pendente ou incerta — reconciliar",
    "WAITING_FOR_PARTIAL_FILLS": "Aguardando preenchimento das parciais",
    "RUNNER_CONFIRMED_NOT_PROTECTED": "Runner confirmado — stop não instalado",
    "RUNNER_EXIT_PENDING_RECONCILIATION": "Saída final do runner pendente ou incerta — reconciliar",
    "RUNNER_EXIT_PARTIALLY_FILLED": "Saída final do runner parcialmente preenchida (PAPER)",
    "RUNNER_CLOSED_PAPER_ONLY": "Runner encerrado no diário PAPER — sem prova de corretora",
    "RUNNER_EXIT_CANCELLED_REMAINDER": "Saída final cancelada/recusada — saldo residual liberado",
}


def _paper_runner_readiness(item: PaperPositionInspection) -> str:
    """Only the local PAPER fill ledger can confirm a residual balance.

    No mark, stop placement, trailing activation or execution is inferred.
    """
    from crypto_intelligence_agent.paper_position_reservations import PaperPositionBalance
    if (type(item) is not PaperPositionInspection or
            type(item.balance) is not PaperPositionBalance):
        raise DataValidationError("validated PAPER position required for runner status")
    b = item.balance
    runner_orders = tuple(o for o in b.exit_orders if o.tranche_step == 0)
    if runner_orders:
        if (b.runner_reserved_unfilled_units > 0 or
                any(o.snapshot.requires_reconciliation for o in runner_orders)):
            return "RUNNER_EXIT_PENDING_RECONCILIATION"
        if (b.runner_filled_units == b.runner_floor_units and
                b.confirmed_remaining_units == 0):
            return "RUNNER_CLOSED_PAPER_ONLY"
        if b.runner_filled_units > 0:
            return "RUNNER_EXIT_PARTIALLY_FILLED"
        if b.runner_unallocated_units > 0:
            return "RUNNER_EXIT_CANCELLED_REMAINDER"
        raise DataValidationError("runner exit state inconsistent")
    if (b.reserved_unfilled_units > 0 or
            any(o.snapshot.requires_reconciliation for o in b.exit_orders)):
        return "PENDING_EXIT_RECONCILIATION"
    if b.runner_floor_units == 0:
        return "NO_RESIDUAL_RUNNER_CONFIGURED"
    if (b.runner_floor_units > 0 and
            b.confirmed_remaining_units == b.runner_floor_units and
            b.unreserved_units == b.runner_floor_units and
            b.tranches and all(
                row.filled_units == row.target_units and
                row.reserved_unfilled_units == 0 and
                row.unallocated_units == 0 for row in b.tranches
            )):
        return "RUNNER_CONFIRMED_NOT_PROTECTED"
    return "WAITING_FOR_PARTIAL_FILLS"


def multi_paper_snapshot(
    selected: tuple[PaperPositionInspection, ...],
    *, runner_observation: tuple[str, PaperRunnerTrailReport] | None = None,
) -> dict[str, object]:
    if type(selected) is not tuple or not 1 <= len(selected) <= 128:
        raise DataValidationError("1-128 explicitly inspected PAPER positions required")
    if runner_observation is not None:
        if (type(runner_observation) is not tuple or len(runner_observation) != 2
                or type(runner_observation[0]) is not str
                or type(runner_observation[1]) is not PaperRunnerTrailReport):
            raise DataValidationError("invalid recovered PAPER runner")
        runner_id, runner_report = runner_observation
        selected_runner = [item for item in selected if item.balance.position_id == runner_id]
        if (len(selected_runner) != 1 or
                _paper_runner_readiness(selected_runner[0]) != "RUNNER_CONFIRMED_NOT_PROTECTED" or
                runner_report.runner_units != selected_runner[0].balance.runner_floor_units or
                runner_report.state.value not in (
                    "NOT_ACTIVATED", "TRACKING", "TRIGGERED_HYPOTHETICAL_ONLY")):
            raise DataValidationError("recovered runner does not match selected PAPER position")
    positions = []
    seen = set()
    for item in selected:
        single = paper_position_snapshot(item)
        p = single["position"]
        if p["position_id"] in seen:
            raise DataValidationError("duplicate selected PAPER position")
        seen.add(p["position_id"])
        orders = p["exit_orders"]
        positions.append({
            "position_id": p["position_id"],
            "venue_candidate": p["venue_candidate"],
            "symbol_fixture": p["symbol_fixture"],
            "side": p["side"],
            "checkpoint_utc": p["checkpoint_utc"],
            "initial_confirmed_units": p["initial_confirmed_units"],
            "filled_exit_units": p["filled_exit_units"],
            "reserved_unfilled_units": p["reserved_unfilled_units"],
            "confirmed_remaining_units": p["confirmed_remaining_units"],
            "unreserved_units": p["unreserved_units"],
            "runner_floor_units": p["runner_floor_units"],
            "runner_filled_units": str(item.balance.runner_filled_units),
            "runner_reserved_unfilled_units": str(item.balance.runner_reserved_unfilled_units),
            "runner_unallocated_units": str(item.balance.runner_unallocated_units),
            "runner_readiness": _paper_runner_readiness(item),
            "trailing_stop_active": False,
            "native_stop_verified": False,
            "recovered_runner": (
                {"state": runner_report.state.value,
                 "observed_tick_count": runner_report.observed_tick_count,
                 "digest_sha256": runner_report.digest_sha256,
                 "hypothetical_only": True,
                 "native_stop_verified": False,
                 "trailing_stop_active": False}
                if runner_observation is not None and p["position_id"] == runner_id
                else None
            ),
            "margin_intent_requested": p["margin_intent_requested"],
            "opening_order_cross_checked": single["opening_order_cross_checked"],
            "pending_or_unknown_orders": sum(
                1 for order in orders if order["requires_reconciliation"]
            ),
            "unknown_order_count": sum(
                1 for order in orders if order["status"] == "UNKNOWN"
            ),
        })
    return {
        "schema_version": _SCHEMA,
        "mode": "offline_paper",
        "quality": "synthetic_journal_replay_only",
        "source_provenance": "local_sqlite_digest_not_exchange_authenticated",
        "selection": "explicit_ids_same_sqlite_read_transaction",
        "no_cross_instrument_quantity_aggregation": True,
        "orders_sent": False,
        "live_trading_authorized": False,
        "approved_for_live_use": False,
        "financial_pnl_available": False,
        "positions": positions,
    }


def _cell(value: str | int) -> str:
    return escape(str(value), quote=True)


def render_position_card_markup(p: dict[str, object]) -> str:
    """Render one card from a validated multi_paper_snapshot.

    Shared by the existing multi-position HTML and the operator overview.
    The caller must first validate all selected positions.
    """
    runner_code = p["runner_readiness"]
    if runner_code not in _RUNNER_LABELS or p["trailing_stop_active"] is not False:
        raise DataValidationError("invalid PAPER runner UI state")
    pending = p["pending_or_unknown_orders"]
    unknown = p["unknown_order_count"]
    margin = p["margin_intent_requested"]
    crosscheck_html = (
        '<p class="details" data-field="opening-crosscheck">'
        + ('Conferido entre diários locais; não é prova da corretora.'
           if p["opening_order_cross_checked"] else
           'Não cruzado com AUTO2; dados apenas do diário local AUTO4.')
        + '</p>'
    )
    if margin is None:
        margin_html = (
            '<p class="details" data-field="margin-intent">'
            'Alavancagem/margem solicitadas (PAPER): não registradas. '
            'Nunca presumir alavancagem padrão.</p>'
        )
    else:
        margin_html = (
            '<p class="details" data-field="margin-intent">'
            'Alavancagem solicitada (PAPER): '
            + _cell(margin["leverage_at_intent"]) + 'x · '
            'Margem solicitada (PAPER): '
            + _cell(margin["requested_margin_quote"]) + ' '
            + _cell(margin["quote_currency"])
            + ' · Apenas intenção simulada, sem comprovar saldo ou margem da corretora.</p>'
        )
    recovered = p.get("recovered_runner")
    recovered_html = ""
    if recovered is not None:
        labels = {
            "NOT_ACTIVATED": "Monitor PAPER recuperado, ainda não ativado",
            "TRACKING": "Monitor PAPER recuperado, trailing hipotético em acompanhamento",
            "TRIGGERED_HYPOTHETICAL_ONLY": "Monitor PAPER recuperado, gatilho apenas hipotético",
        }
        code = recovered["state"]
        if code not in labels or recovered["native_stop_verified"] is not False:
            raise DataValidationError("unsafe recovered runner state")
        recovered_html = (
            '<p class="details" data-field="runner-recovery" data-runner-observation="'
            + _cell(code) + '">' + _cell(labels[code]) + ' · '
            + _cell(recovered["observed_tick_count"])
            + ' marcas fictícias; nenhum stop nativo ou fill.</p>'
        )
    return (
        '<article class="position-card" data-position="' + _cell(p["position_id"]) + '">'
        + '<h3>' + _cell(p["position_id"]) + '</h3>'
        + '<p class="meta">' + _cell(p["venue_candidate"]) + ' · '
        + _cell(p["symbol_fixture"]) + ' · ' + _cell(p["side"]) + '</p>'
        + '<dl class="balances">'
        + '<div><dt>Abertura confirmada</dt><dd>' + _cell(p["initial_confirmed_units"]) + '</dd></div>'
        + '<div><dt>Saídas preenchidas</dt><dd>' + _cell(p["filled_exit_units"]) + '</dd></div>'
        + '<div><dt>Reservado/pedidos incertos</dt><dd>' + _cell(p["reserved_unfilled_units"]) + '</dd></div>'
        + '<div><dt>Disponível não reservado</dt><dd class="accent">' + _cell(p["unreserved_units"]) + '</dd></div>'
        + '</dl>'
        + margin_html + crosscheck_html + recovered_html
        + '<p class="details" data-field="runner-readiness" data-runner-state="'
        + _cell(runner_code) + '">' + _cell(_RUNNER_LABELS[runner_code])
        + ' · Somente PAPER; trailing não ativo e stop nativo não verificado.</p>'
        + '<p class="details" data-field="runner-exit-quantities">'
        + 'Runner PAPER — preenchido: ' + _cell(p["runner_filled_units"])
        + ' · reservado: ' + _cell(p["runner_reserved_unfilled_units"])
        + ' · disponível: ' + _cell(p["runner_unallocated_units"])
        + ' (unidades do próprio instrumento, sem valor monetário).</p>'
        + '<p class="details">Saldo confirmado: ' + _cell(p["confirmed_remaining_units"])
        + ' · piso residual: ' + _cell(p["runner_floor_units"])
        + ' · pendentes: ' + _cell(pending)
        + ' · <span class="' + ('unknown' if unknown else 'meta') + '">UNKNOWN: '
        + _cell(unknown) + '</span></p>'
        + '<p class="details">Checkpoint UTC: ' + _cell(p["checkpoint_utc"])
        + ' · somente eventos de fixture.</p></article>'
    )


def render_paper_positions(selected: tuple[PaperPositionInspection, ...],
                           template: str, *,
                           runner_observation: tuple[str, PaperRunnerTrailReport] | None = None) -> str:
    snap = multi_paper_snapshot(selected, runner_observation=runner_observation)
    if (type(template) is not str
            or not template.lstrip().lower().startswith("<!doctype html>")
            or "default-src 'none'" not in template
            or "connect-src 'none'" not in template
            or 'data-mode="offline_paper"' not in template
            or "SIMULADO" not in template):
        raise DataValidationError("insecure PAPER portfolio HTML template")
    try:
        _audit_offline_template(template)
    except ValueError as exc:
        raise DataValidationError("unsafe PAPER portfolio template") from exc

    cards, rows = [], []
    for p in snap["positions"]:
        cards.append(render_position_card_markup(p))
        unknown = p["unknown_order_count"]
        fields = (
            p["position_id"], p["venue_candidate"] + " · " + p["symbol_fixture"]
            + " · " + p["side"], p["initial_confirmed_units"],
            p["filled_exit_units"], p["reserved_unfilled_units"],
            p["unreserved_units"], unknown, _RUNNER_LABELS[p["runner_readiness"]] +
            " · runner preenchido " + p["runner_filled_units"] +
            " / reservado " + p["runner_reserved_unfilled_units"] +
            " / disponível " + p["runner_unallocated_units"] + (
                " · " + p["recovered_runner"]["state"] + " (somente hipotético)"
                if p["recovered_runner"] is not None else ""),
        )
        rows.append("<tr>" + "".join("<td>" + _cell(x) + "</td>" for x in fields)
                    + "</tr>")
    replacements = {
        "count": str(len(snap["positions"])),
        "position_cards": "\n        ".join(cards),
        "position_rows": "\n            ".join(rows),
    }
    matches = re.findall(r"\{\{([a-z_]+)\}\}", template)
    if len(matches) != len(replacements) or set(matches) != set(replacements):
        raise DataValidationError("missing, duplicate or unknown PAPER view markers")
    result = template
    for key, value in replacements.items():
        result = result.replace("{{" + key + "}}", value)
    if "{{" in result or "}}" in result:
        raise DataValidationError("unresolved PAPER view marker")
    try:
        _audit_offline_template(result)
    except ValueError as exc:
        raise DataValidationError("rendered PAPER view violates no-network policy") from exc
    return result


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Inspeciona IDs explícitos de posições PAPER, sem consolidação financeira."
    )
    parser.add_argument("--journal", type=Path, required=True,
                        help="UM diário SQLite de posições fictícias já existente.")
    parser.add_argument("--position-id", action="append", required=True,
                        help="ID fictício fixture_...; repetir apenas para outras posições escolhidas.")
    parser.add_argument("--opening-order-journal", type=Path,
                        help="Diário AUTO2 opcional para conferir todas as aberturas PAPER.")
    parser.add_argument("--format", choices=("html", "json"), default="html")
    parser.add_argument("--output", type=Path,
                        help="Arquivo NOVO; nunca substituir resultado ou diário existente.")
    parser.add_argument("--runner-journal", type=Path)
    parser.add_argument("--runner-position-id")
    parser.add_argument("--runner-activation-bps")
    parser.add_argument("--runner-trail-distance-bps")
    parser.add_argument("--runner-max-tick-gap-ms", type=int)
    parser.add_argument("--runner-max-last-tick-age-ms", type=int)
    parser.add_argument("--runner-as-of-ms", type=int)
    args = parser.parse_args(argv)
    runner_options = (args.runner_journal, args.runner_position_id,
                      args.runner_activation_bps, args.runner_trail_distance_bps,
                      args.runner_max_tick_gap_ms, args.runner_max_last_tick_age_ms,
                      args.runner_as_of_ms)
    if any(v is not None for v in runner_options) and not all(v is not None for v in runner_options):
        parser.error("RUNNER2 exige journal, ID, política e cutoff completos")
    if args.runner_position_id is not None and args.runner_position_id not in args.position_id:
        parser.error("RUNNER2 exige posição explicitamente selecionada")
    selected = inspect_paper_positions(
        args.journal, tuple(args.position_id),
        opening_order_path=args.opening_order_journal,
    )
    runner_observation = None
    if args.runner_journal is not None:
        try:
            policy = PaperRunnerTrailPolicy(
                Decimal(args.runner_activation_bps), Decimal(args.runner_trail_distance_bps),
                args.runner_max_tick_gap_ms, args.runner_max_last_tick_age_ms,
            )
        except (ValueError, ArithmeticError) as exc:
            raise DataValidationError("invalid RUNNER2 policy") from exc
        report = load_paper_runner_journal(
            args.runner_journal, args.journal, args.runner_position_id,
            policy=policy, as_of_ms=args.runner_as_of_ms,
        )
        refreshed = inspect_paper_position(
            args.journal, args.runner_position_id,
            opening_order_path=args.opening_order_journal,
        )
        previous = next(x for x in selected if x.balance.position_id == args.runner_position_id)
        if refreshed != previous:
            raise DataValidationError("PAPER position changed during RUNNER2 read")
        runner_observation = (args.runner_position_id, report)
    payload = (
        render_paper_positions(
            selected, TEMPLATE.read_text(encoding="utf-8"),
            runner_observation=runner_observation,
        )
        if args.format == "html" else
        json.dumps(multi_paper_snapshot(selected, runner_observation=runner_observation), sort_keys=True,
                   ensure_ascii=False, indent=2) + "\n"
    )
    if args.output is None:
        sys.stdout.write(payload)
    else:
        with args.output.open("x", encoding="utf-8") as output:
            output.write(payload)


if __name__ == "__main__":
    main()
