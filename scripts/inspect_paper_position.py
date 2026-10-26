"""J5/PRE4: export ONE locally persisted PAPER position as JSON or HTML.

Run:
  python3 -m scripts.inspect_paper_position --journal /path/existing.sqlite \\
      --position-id fixture_position_A --format html --output /tmp/inspection.html

No external JSON, HTTP, accounts, market data, trade intents or DDL. SQLite is
opened in mode=ro and all quantities come from verified local fixture events.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from html import escape
import json
from pathlib import Path
import re
import sys

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.paper_position_inspection import (
    PaperPositionInspection, inspect_paper_position,
)
from crypto_intelligence_agent.synthetic_order_lifecycle import PaperOrderStatus
from scripts.render_paper_dashboard import _audit_offline_template


TEMPLATE = Path(__file__).resolve().parent.parent / "web" / "paper-position-template.html"
_SCHEMA = "paper_position_snapshot_v1"
_STATUS_LABELS = {
    PaperOrderStatus.PENDING: "Pendente",
    PaperOrderStatus.ACKNOWLEDGED: "Confirmada, sem fill",
    PaperOrderStatus.UNKNOWN: "UNKNOWN — resultado incerto",
    PaperOrderStatus.PARTIALLY_FILLED: "Parcialmente preenchida",
    PaperOrderStatus.FILLED: "Preenchida",
    PaperOrderStatus.CANCELLED: "Cancelada",
    PaperOrderStatus.REJECTED: "Rejeitada",
}


def _units(value: Decimal) -> str:
    # Display preserves the original exact Decimal; no trade lot rounding.
    return format(value, "f")


def _utc(value: int) -> str:
    # Do not convert to local time or lose millisecond provenance.
    stamp = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(milliseconds=value)
    return stamp.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def paper_position_snapshot(value: PaperPositionInspection) -> dict[str, object]:
    """Allowlisted output; no account IDs, API keys, mark prices or real PnL."""
    if type(value) is not PaperPositionInspection:
        raise DataValidationError("verified read-only PAPER inspection required")
    v = value.balance
    if (not v.position_id.startswith("fixture_")
            or v.orders_sent or v.live_trading_authorized
            or value.orders_sent or value.live_trading_authorized
            or value.approved_for_live_use or value.financial_pnl_available
            or value.mode != "offline_paper"):
        raise DataValidationError("non-PAPER or unverified state cannot be presented")
    return {
        "schema_version": _SCHEMA,
        "mode": value.mode,
        "quality": value.quality,
        "source_provenance": value.source_provenance,
        "orders_sent": False,
        "approved_for_live_use": False,
        "live_trading_authorized": False,
        "financial_pnl_available": False,
        "opening_order_cross_checked": value.opening_order_cross_checked,
        "position": {
            "position_id": v.position_id,
            "venue_candidate": v.venue.value,
            "symbol_fixture": v.symbol,
            "side": v.side.value,
            "plan_version": v.plan_version,
            "opened_at_utc": _utc(v.opened_at_ms),
            "checkpoint_utc": _utc(v.as_of_ms),
            "initial_confirmed_units": _units(v.initial_confirmed_units),
            "filled_exit_units": _units(v.filled_exit_units),
            "reserved_unfilled_units": _units(v.reserved_unfilled_units),
            "confirmed_remaining_units": _units(v.confirmed_remaining_units),
            "unreserved_units": _units(v.unreserved_units),
            "runner_floor_units": _units(v.runner_floor_units),
            "exit_orders": [
                {
                    "tranche_step": x.tranche_step,
                    "status": x.snapshot.status.value,
                    "requested_units": _units(x.intent.requested_units),
                    "filled_units": _units(x.snapshot.filled_total_units),
                    "reserved_unfilled_units": _units(x.reserved_unfilled_units),
                    "requires_reconciliation": x.snapshot.requires_reconciliation,
                }
                for x in v.exit_orders
            ],
            "tranches": [
                {
                    "step": x.step, "basis": x.basis.value,
                    "target_units": _units(x.target_units),
                    "filled_units": _units(x.filled_units),
                    "reserved_unfilled_units": _units(x.reserved_unfilled_units),
                    "unallocated_units": _units(x.unallocated_units),
                }
                for x in v.tranches
            ],
        },
    }


def render_paper_position(value: PaperPositionInspection, template: str) -> str:
    """Render a validated local PAPER snapshot, never HTML from external input."""
    snap = paper_position_snapshot(value)
    if type(template) is not str or not template.lstrip().lower().startswith("<!doctype html>"):
        raise DataValidationError("standalone local PAPER HTML required")
    if ("default-src 'none'" not in template or "connect-src 'none'" not in template
            or 'data-mode="offline_paper"' not in template
            or "SIMULADO" not in template):
        raise DataValidationError("PAPER position template missing required safety labels")
    # Reuse PRE3's strict allowlist: a single local skip link, no outbound URLs,
    # no JS, no forms, one keyboard-focusable scrollable table.
    try:
        _audit_offline_template(template)
    except ValueError as exc:
        raise DataValidationError("unsafe local PAPER position template") from exc
    p = snap["position"]
    status_by_value = {key.value: value for key, value in _STATUS_LABELS.items()}
    exit_markup = []
    for row in p["exit_orders"]:
        label = status_by_value[row["status"]]
        status_css = " class=\"status-unknown\"" if row["status"] == "UNKNOWN" else ""
        value_cells = (
            str(row["tranche_step"]), label, row["requested_units"],
            row["filled_units"], row["reserved_unfilled_units"],
        )
        cells = [
            f"<td{status_css if idx == 1 else ''}>{escape(str(cell), quote=True)}</td>"
            for idx, cell in enumerate(value_cells)
        ]
        exit_markup.append("<tr>" + "".join(cells) + "</tr>")
    if not exit_markup:
        exit_markup = [
            '<tr><td colspan="5">Nenhuma ordem de saída PAPER registrada nesta posição.</td></tr>',
        ]
    tranche_markup = [
        "<li>Parcial " + escape(str(row["step"]))
        + " · " + escape(str(row["basis"]))
        + " · meta " + escape(row["target_units"])
        + " · preenchido " + escape(row["filled_units"])
        + " · reservado " + escape(row["reserved_unfilled_units"])
        + " · ainda não alocado " + escape(row["unallocated_units"])
        + " unidades</li>"
        for row in p["tranches"]
    ]
    replacement = {
        "initial": p["initial_confirmed_units"],
        "filled": p["filled_exit_units"],
        "reserved": p["reserved_unfilled_units"],
        "available": p["unreserved_units"],
        "remaining": p["confirmed_remaining_units"],
        "floor": p["runner_floor_units"],
        "position_id": p["position_id"],
        "venue": p["venue_candidate"],
        "symbol": p["symbol_fixture"],
        "side": p["side"],
        "checkpoint": p["checkpoint_utc"],
        "checkpoint_iso": p["checkpoint_utc"],
        "opened": p["opened_at_utc"],
        "crosscheck": (
            "Abertura conferida também no journal AUTO2"
            if snap["opening_order_cross_checked"]
            else "Abertura não cruzada com journal AUTO2"
        ),
        "plan_version": p["plan_version"],
        "exit_rows": "\n            ".join(exit_markup),
        "tranche_rows": "\n        ".join(tranche_markup),
    }
    matches = re.findall(r"\{\{([a-z_]+)\}\}", template)
    if len(matches) != len(replacement) or set(matches) != set(replacement):
        raise DataValidationError("PAPER position template markers missing/duplicated")
    result = template
    for key, raw in replacement.items():
        text = (raw if key in ("exit_rows", "tranche_rows")
                else escape(str(raw), quote=True))
        result = result.replace("{{" + key + "}}", text)
    if "{{" in result or "}}" in result:
        raise DataValidationError("unresolved PAPER HTML interpolation")
    try:
        _audit_offline_template(result)
    except ValueError as exc:
        raise DataValidationError("rendered PAPER HTML violates strict offline policy") from exc
    return result


def main(argv: list[str] | None = None) -> None:
    cli = argparse.ArgumentParser(
        description="Inspeciona UMA posição fictícia existente, sem modificar SQLite ou negociar."
    )
    cli.add_argument("--journal", type=Path, required=True,
                     help="Banco SQLite PAPER de posição existente; aberto somente leitura.")
    cli.add_argument("--position-id", required=True,
                     help="Identidade explícita fixture_... da posição.")
    cli.add_argument("--opening-order-journal", type=Path,
                     help="Banco AUTO2 opcional para conferir exclusivamente a abertura PAPER.")
    cli.add_argument("--format", choices=("html", "json"), default="html")
    cli.add_argument("--output", type=Path,
                     help="Novo arquivo HTML/JSON; nunca sobrescreve arquivos existentes.")
    args = cli.parse_args(argv)
    position = inspect_paper_position(
        args.journal, args.position_id, opening_order_path=args.opening_order_journal,
    )
    data = (
        render_paper_position(position, TEMPLATE.read_text(encoding="utf-8"))
        if args.format == "html" else
        json.dumps(paper_position_snapshot(position), ensure_ascii=False,
                   sort_keys=True, indent=2) + "\n"
    )
    if args.output is None:
        sys.stdout.write(data)
    else:
        # No --input, remote URL or implicit writes; exclusive output creation.
        with args.output.open("x", encoding="utf-8") as f:
            f.write(data)


if __name__ == "__main__":
    main()
