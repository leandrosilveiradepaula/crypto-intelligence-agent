"""J5: gerar painel local responsivo de STATUS de ordens PAPER, sem HTTP.

Exemplos (apenas arquivo ficticio/local):
  python3 -m scripts.render_paper_operator_status --journal /privado/orders.sqlite
  python3 -m scripts.render_paper_operator_status --journal /privado/orders.sqlite --format json
  python3 -m scripts.render_paper_operator_status --journal /privado/orders.sqlite --output /tmp/estado.html

Nao faz envios, nao controla corretoras, nao recebe endpoints/keys/contas e
nao altera o diario. O bot REAL nao existe no modo desta pagina.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
from html import escape
import json
from pathlib import Path
import sys

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.paper_operator_status import (
    PaperOperatorStatus, inspect_local_paper_operator_status,
)


def _clock(ms: int | None) -> str:
    if ms is None or ms == 0:
        return "Não registrado"
    if type(ms) is not int or not 0 < ms <= 253_402_300_799_999:
        raise DataValidationError("invalid PAPER display timestamp")
    return datetime.fromtimestamp(ms // 1000, tz=timezone.utc).strftime(
        "%d/%m/%Y %H:%M:%S UTC"
    )


def render_local_paper_status(status: PaperOperatorStatus) -> str:
    """No JavaScript, no form/buttons, no links/assets/network, only local HTML."""
    if (type(status) is not PaperOperatorStatus
            or type(status.new_paper_open_paused) is not bool
            or type(status.durable_cursor_present) is not bool
            or type(status.unknown_open_requires_reconciliation) is not bool):
        raise DataValidationError("invalid PAPER read-only display status")
    for count in (
        status.pause_sequence, status.cursor_sequence,
        status.accepted_candle_count, status.reserved_open_intent_count,
        status.pending_or_unresolved_open_count,
    ):
        if type(count) is not int or not 0 <= count <= 1_000_000_000:
            raise DataValidationError("invalid PAPER display count")
    if (status.reserved_open_intent_count > status.cursor_sequence
            or status.pending_or_unresolved_open_count >
            status.reserved_open_intent_count
            or status.durable_cursor_present is not (status.cursor_sequence > 0)
            or (not status.durable_cursor_present and
                (status.accepted_candle_count != 0 or
                 status.last_closed_candle_at_ms is not None))):
        raise DataValidationError("inconsistent PAPER operator snapshot")

    headline = (
        "Novas entradas PAPER pausadas" if status.new_paper_open_paused
        else "Pausa local desativada"
    )
    detail = (
        "A reserva de novas OPEN PAPER está bloqueada neste diário."
        if status.new_paper_open_paused
        else "O robô ainda depende dos demais bloqueios de risco, dados e proteção."
    )
    state_label = "Pausadas" if status.new_paper_open_paused else "Não pausadas"
    unknown = (
        "SIM — requer reconciliação" if status.unknown_open_requires_reconciliation
        else "Não identificado"
    )
    checkpoint = _clock(status.last_closed_candle_at_ms)
    switched_at = _clock(status.pause_changed_at_ms)
    # All dynamic textual values are created from trusted enums/booleans,
    # formatted integers and timestamps, and still escaped defensively.
    def safe(value: object) -> str:
        return escape(str(value), quote=True)

    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light">
  <title>Estado do agente — simulação PAPER</title>
  <style>
    :root {{ color-scheme: light; font-family: system-ui, sans-serif; }}
    *, *::before, *::after {{ box-sizing: border-box; }}
    body {{ margin: 0; padding: 0; background: #f5f7fa; color: #182536; }}
    .container {{ width: min(100%, 860px); margin-inline: auto; padding: 16px; }}
    .skip {{ position: absolute; top: -80px; left: 8px; padding: 10px; }}
    .skip:focus {{ top: 8px; background: #fff; z-index: 10; }}
    h1 {{ font-size: 1.45rem; line-height: 1.25; margin: 12px 0; }}
    h2 {{ font-size: 1.06rem; margin: 0 0 8px; }}
    p {{ line-height: 1.5; overflow-wrap: anywhere; }}
    .eyebrow {{ font-weight: 750; letter-spacing: .07em; color: #354f68; }}
    .summary, .tile, .warning {{ border: 1px solid #ced8e2; border-radius: 12px; background: #fff; }}
    .summary {{ padding: 18px; margin: 20px 0; border-left: 5px solid #395d84; }}
    .summary[data-paused="true"] {{ border-left-color: #934d16; }}
    .summary strong {{ display: block; font-size: 1.25rem; margin-bottom: 6px; }}
    .grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }}
    .tile {{ padding: 16px; min-width: 0; }}
    dt {{ font-size: .88rem; color: #34506d; font-weight: 600; }}
    dd {{ margin: 7px 0 0; font-size: 1.2rem; overflow-wrap: anywhere; font-variant-numeric: tabular-nums; }}
    .fine {{ font-size: .88rem; }}
    .warning {{ margin-top: 22px; padding: 14px 17px; background: #fbfcfe; }}
    footer {{ margin: 20px 0 8px; color: #34506d; font-size: .85rem; }}
    @media (max-width: 420px) {{
      .container {{ padding: 12px; }}
      .grid {{ grid-template-columns: minmax(0, 1fr); }}
      .summary {{ padding: 14px; }}
      dd {{ font-size: 1.15rem; }}
    }}
  </style>
</head>
<body>
  <a class="skip" href="#conteudo">Ir para o conteúdo</a>
  <main class="container" id="conteudo" tabindex="-1">
    <header>
      <p class="eyebrow">CRYPTO INTELLIGENCE AGENT · SOMENTE SIMULAÇÃO</p>
      <h1>Estado local do agente PAPER</h1>
      <p class="fine">Leitura do diário SQLite de ordens fictícias. Não é conta, corretora ou mercado ao vivo.</p>
    </header>
    <section class="summary" role="status" aria-label="Estado das novas entradas PAPER"
             data-paused="{str(status.new_paper_open_paused).lower()}">
      <strong>{safe(headline)}</strong>
      <p>{safe(detail)}</p>
      <p class="fine">Última alteração do controle: {safe(switched_at)} · sequência {status.pause_sequence}</p>
    </section>
    <section aria-labelledby="titulo-detalhes">
      <h2 id="titulo-detalhes">Acompanhamento do replay local</h2>
      <dl class="grid">
        <div class="tile"><dt>Entradas novas PAPER</dt><dd>{safe(state_label)}</dd></div>
        <div class="tile"><dt>Candles sintéticos processados</dt><dd>{status.accepted_candle_count}</dd></div>
        <div class="tile"><dt>Sequência do checkpoint</dt><dd>{status.cursor_sequence}</dd></div>
        <div class="tile"><dt>OPENs PAPER registradas</dt><dd>{status.reserved_open_intent_count}</dd></div>
        <div class="tile"><dt>OPENs pendentes ou incertas</dt><dd>{status.pending_or_unresolved_open_count}</dd></div>
        <div class="tile"><dt>Alguma OPEN UNKNOWN?</dt><dd>{safe(unknown)}</dd></div>
        <div class="tile"><dt>Fechamento da última vela de fixture</dt><dd class="fine">{safe(checkpoint)}</dd></div>
        <div class="tile"><dt>Checkpoint persistente</dt><dd>{'Sim' if status.durable_cursor_present else 'Não'}</dd></div>
      </dl>
    </section>
    <aside class="warning" aria-label="Aviso de segurança">
      <strong>ATENÇÃO · exclusivamente PAPER</strong>
      <p>Pausar novas OPENs não cancela ordens, não fecha posições e não instala stop nativo. Dados de mercado reais, risco financeiro, PnL e proteção da corretora NÃO foram verificados.</p>
      <p class="fine">Esta página é estática, somente leitura, sem controles de execução, JavaScript, rede ou atualização automática. Para alterar a pausa local, use o comando de operador autorizado no próprio ambiente privado.</p>
    </aside>
    <footer>Sem ordens reais. Sem autorização para testnet ou produção.</footer>
  </main>
</body>
</html>
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--format", choices=("html", "json"), default="html")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        status = inspect_local_paper_operator_status(args.journal)
        payload = (
            render_local_paper_status(status)
            if args.format == "html"
            else json.dumps({
                "schema_version": "paper_operator_read_only_status_v1",
                **asdict(status),
                "mode": status.mode,
                "live_trading_authorized": False,
                "orders_sent": False,
                "order_submission_enabled": False,
                "native_stop_verified": False,
            }, sort_keys=True, ensure_ascii=False) + "\n"
        )
        if args.output is None:
            sys.stdout.write(payload)
        else:
            with args.output.open("x", encoding="utf-8", newline="\n") as out:
                out.write(payload)
        return 0
    except Exception:
        # Fail closed and do not leak a private journal path or SQLite values.
        print("Leitura de estado PAPER indisponível ou arquivo inválido.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
