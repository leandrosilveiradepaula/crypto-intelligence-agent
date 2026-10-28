"""Local PAPER recovery diagnostic and offline mobile display. No trading.

Default stays JSON:
  python -m scripts.inspect_paper_recovery --orders orders.sqlite --positions positions.sqlite
Optional static PT-BR document:
  python -m scripts.inspect_paper_recovery --orders orders.sqlite --positions positions.sqlite --format html --output recovery.html

Neither mode reads exchange feeds, sends orders, uses credentials or writes
either journal. Output creation, if requested, is exclusive.
"""
from __future__ import annotations

import argparse
from html import escape
import json
from pathlib import Path
import re
import sys

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.paper_operator_status import PaperOperatorStatus
from crypto_intelligence_agent.paper_recovery_status import (
    PaperRecoveryState, PaperRecoveryStatus, inspect_local_paper_recovery_status,
)


_STATE_TEXT = {
    PaperRecoveryState.UNVERIFIED: (
        "Recuperação PAPER não verificada",
        "A leitura local não permite confirmar o estado de recuperação.",
    ),
    PaperRecoveryState.BLOCKED: (
        "Recuperação PAPER bloqueada",
        "Existe uma pausa, pendência ou incompatibilidade que requer revisão local.",
    ),
    PaperRecoveryState.PAPER_FLAT_HYPOTHETICAL_ONLY: (
        "Replay PAPER sem posição aberta",
        "A conclusão vale somente para estes diários sintéticos locais.",
    ),
}
_REASON_TEXT = {
    "paper_journal_unverified": "Diário ausente, inválido ou inconsistente.",
    "paper_replay_not_initialized": "Não existe cursor durável de replay.",
    "paper_snapshot_changed_during_inspection":
        "Foram observadas alterações entre leituras dos diários.",
    "paper_operator_paused": "Pausa local de novas entradas PAPER ativa.",
    "paper_order_reconciliation_required":
        "Existe uma OPEN PAPER pendente ou incerta.",
    "paper_open_unprotected":
        "Há FILL fictício sem posição local correspondente.",
    "paper_open_unverified_protection":
        "Um plano de saída sintético não é stop da corretora.",
    "paper_open_health_unknown":
        "Posições e ordens fictícias exigem reconciliação.",
    "paper_flat_not_live_verified":
        "As posições do replay local estão ausentes ou hipoteticamente encerradas.",
    "paper_health_unverified": "A integridade do replay não foi confirmada.",
}


def _validate_display(status: PaperRecoveryStatus) -> None:
    if (type(status) is not PaperRecoveryStatus
            or type(status.state) is not PaperRecoveryState
            or type(status.reason) is not str
            or re.fullmatch(r"[a-z][a-z0-9_]{0,95}", status.reason) is None):
        raise DataValidationError("invalid PAPER recovery display state")
    for name in (
        "cross_database_atomic_snapshot_available", "native_stop_verified",
        "orders_sent", "live_trading_authorized", "new_open_authorized",
    ):
        if getattr(status, name) is not False:
            raise DataValidationError("PAPER recovery display cannot authorize trading")
    if status.operator is not None and type(status.operator) is not PaperOperatorStatus:
        raise DataValidationError("invalid PAPER operator diagnostic")
    if status.state is PaperRecoveryState.PAPER_FLAT_HYPOTHETICAL_ONLY:
        if (status.reason != "paper_flat_not_live_verified"
                or status.operator is None
                or not status.operator.durable_cursor_present):
            raise DataValidationError("flat PAPER display requires durable replay")
    if status.state is PaperRecoveryState.BLOCKED and status.operator is None:
        raise DataValidationError("blocked PAPER display requires operator evidence")


def render_recovery_html(status: PaperRecoveryStatus) -> str:
    """Render one static, accessible PT-BR page; never an interactive control."""
    _validate_display(status)
    headline, detail = _STATE_TEXT[status.state]
    reason = _REASON_TEXT.get(
        status.reason, "Este estado requer verificação local.",
    )
    cursor = (
        "Não verificado" if status.operator is None
        else ("Sim" if status.operator.durable_cursor_present else "Não")
    )
    # The technical reason is a constrained code, never a DB row/ID/path.
    state_code = escape(status.state.value, quote=True)
    reason_code = escape(status.reason, quote=True)
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="Content-Security-Policy"
        content="default-src 'none'; style-src 'unsafe-inline'; connect-src 'none'; form-action 'none'; base-uri 'none'">
  <meta name="color-scheme" content="light">
  <title>Recuperação do agente — somente PAPER</title>
  <style>
    :root {{ color-scheme: light; font-family: system-ui, sans-serif; }}
    *, *::before, *::after {{ box-sizing: border-box; }}
    body {{ margin: 0; background: #f5f7fa; color: #182536; }}
    .container {{ max-width: 820px; margin: auto; padding: 16px; }}
    .skip {{ position: absolute; left: 8px; top: -100px; padding: 12px; background: white; }}
    .skip:focus {{ top: 8px; z-index: 10; }}
    h1 {{ font-size: 1.45rem; line-height: 1.25; }}
    h2 {{ font-size: 1.13rem; line-height: 1.35; margin-top: 0; }}
    p {{ line-height: 1.5; overflow-wrap: anywhere; }}
    .eyebrow {{ font-weight: 750; color: #34506d; letter-spacing: .05em; }}
    .summary, .tile, .warning {{ background: white; border: 1px solid #cad5e0; border-radius: 12px; }}
    .summary {{ border-left: 5px solid #8a4e18; padding: 18px; margin: 18px 0; }}
    .summary[data-state="PAPER_FLAT_HYPOTHETICAL_ONLY"] {{ border-left-color: #345e7c; }}
    .summary[data-state="UNVERIFIED"] {{ border-left-color: #8a252b; }}
    .grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }}
    .tile {{ min-width: 0; padding: 14px; }}
    dt {{ font-weight: 650; color: #34506d; font-size: .89rem; }}
    dd {{ margin: 6px 0 0; overflow-wrap: anywhere; font-weight: 600; }}
    code {{ font-size: .88rem; overflow-wrap: anywhere; }}
    .warning {{ margin-top: 18px; padding: 16px; background: #fff8eb; border-color: #ac8c4b; }}
    footer {{ font-size: .9rem; color: #34506d; margin: 20px 0 8px; }}
    @media (max-width: 420px) {{
      .container {{ padding: 12px; }}
      .grid {{ grid-template-columns: minmax(0, 1fr); }}
      .summary {{ padding: 14px; }}
    }}
  </style>
</head>
<body>
  <a class="skip" href="#conteudo">Pular para o conteúdo</a>
  <main class="container" id="conteudo" tabindex="-1">
    <header>
      <p class="eyebrow">CRYPTO INTELLIGENCE AGENT · SIMULAÇÃO OFFLINE</p>
      <h1>Recuperação local do agente PAPER</h1>
      <p>Diagnóstico de dois diários SQLite fictícios; não representa conta ou corretora.</p>
    </header>
    <section class="summary" role="status" aria-label="Estado de recuperação PAPER"
             data-state="{state_code}">
      <h2>{escape(headline, quote=True)}</h2>
      <p>{escape(detail, quote=True)}</p>
      <p>{escape(reason, quote=True)}</p>
      <p>Motivo técnico: <code>{reason_code}</code></p>
    </section>
    <section aria-labelledby="detalhes">
      <h2 id="detalhes">Limites verificados da consulta</h2>
      <dl class="grid">
        <div class="tile"><dt>Cursor durável no diário de ordens</dt><dd>{cursor}</dd></div>
        <div class="tile"><dt>Novas OPEN autorizadas por esta página</dt><dd>NÃO</dd></div>
        <div class="tile"><dt>Stop nativo de corretora</dt><dd>Não verificado</dd></div>
        <div class="tile"><dt>Snapshot atômico entre os dois bancos</dt><dd>Indisponível</dd></div>
        <div class="tile"><dt>Ordens reais enviadas</dt><dd>Não</dd></div>
        <div class="tile"><dt>Execução live autorizada</dt><dd>Não</dd></div>
      </dl>
    </section>
    <aside class="warning" aria-label="Aviso de segurança PAPER">
      <strong>ATENÇÃO: EXCLUSIVAMENTE PAPER</strong>
      <p>Mesmo um estado hipoteticamente encerrado não comprova risco, funding, liquidação, saldo, stop ou PnL de corretora. Este relatório jamais libera novas ordens.</p>
      <p>Os dois arquivos são inspecionados separadamente. Leituras consecutivas iguais não asseguram um snapshot atômico nem excluem mudanças não observadas.</p>
      <p>Esta página é estática: sem JavaScript, rede, controles de execução ou atualização automática.</p>
    </aside>
    <footer>Sem ordens reais, sem dados live e sem autorização para produção.</footer>
  </main>
</body>
</html>
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Diagnóstico local PAPER (sem ordens)")
    parser.add_argument("--orders", type=Path, required=True)
    parser.add_argument("--positions", type=Path, required=True)
    parser.add_argument("--format", choices=("json", "html"), default="json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    status = inspect_local_paper_recovery_status(args.orders, args.positions)
    try:
        if args.format == "html":
            payload = render_recovery_html(status)
        else:
            payload = json.dumps({
                "mode": "offline_paper",
                "state": status.state.value,
                "reason": status.reason,
                "cross_database_atomic_snapshot_available": False,
                "native_stop_verified": False,
                "new_open_authorized": False,
                "orders_sent": False,
                "live_trading_authorized": False,
            }, sort_keys=True) + "\n"
        if args.output is None:
            sys.stdout.write(payload)
        else:
            with args.output.open("x", encoding="utf-8", newline="\n") as out:
                out.write(payload)
    except (OSError, ValueError, DataValidationError):
        # Do not expose private paths, SQLite fragments or credentials.
        print("Diagnóstico PAPER indisponível; saída não produzida.", file=sys.stderr)
        return 2
    return 0 if status.state is PaperRecoveryState.PAPER_FLAT_HYPOTHETICAL_ONLY else 2


if __name__ == "__main__":
    raise SystemExit(main())
