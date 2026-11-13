"""J5/D330: offline mobile projection of the existing J1/D323 N50 WS witness.

This is an operator-facing rendering of evidence, not a new health monitor.
It cannot enable trading, prove 24/7 uptime, or authenticate market data.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from html import escape
import os
from pathlib import Path
import re
import stat
from typing import Any

from .j1_n50_ws_24h_witness import _result as _empty_witness
from .j1_n50_ws_epoch_rotation import _OWNER_ROOT

_SHA = re.compile(r"[0-9a-f]{64}\Z")
_HOUR_MS = 3_600_000
_MAX_HTML = 32_768
_STATUSES = {
    "ws_24h_local_evidence_verified": ("24 horas locais auditadas", "local"),
    "accumulating_or_incomplete_ws_24h": ("Janela incompleta — sem aceite 24h", "partial"),
    "awaiting_owner_ws_journal_audit": ("Agendamentos disponíveis; journal ainda não auditado", "waiting"),
    "awaiting_safe_closed_hour_audit_window": ("Aguardando janela segura de auditoria", "waiting"),
    "n2_failback_observed": ("Fallback N2 observado; WebSocket indisponível", "fallback"),
    "ws_systemd_isolation_or_service_not_ready": ("Serviço ou isolamento pendente", "blocked"),
    "owner_active_ws_epoch_unavailable": ("Epoch ativo não verificado", "blocked"),
    "owner_ws_scope_integrity_abstain": ("Escopo N50 não verificado", "blocked"),
    "owner_ws_journal_integrity_abstain": ("Journal WS não verificado", "blocked"),
    "owner_ws_readonly_audit_abstain": ("Auditoria local não concluída", "blocked"),
    "invalid_or_untrusted_witness_input": ("Evidência inválida", "blocked"),
    "owner_optin_required": ("Autorização explícita ausente", "blocked"),
    "owner_environment_abstain": ("Ambiente privado não verificado", "blocked"),
}
_NEGATIVE_FLAGS = (
    "rotation_36h_live_verified",
    "continuous_collector_verified",
    "marketwide_top50_verified",
    "crypto_identity_independently_verified",
    "source_authenticated",
    "approved_for_signals",
    "live_trading_authorized",
    "orders_sent",
    "systemd_modified",
)
_STATE_FLAGS = (
    "ws_timer_active_enabled",
    "rotation_timer_active_enabled",
    "n2_quiesced",
    "old_rest_n50_quiesced",
    "ws_service_not_failed",
    "ws_journal_integrity_verified",
    "ws_closed_24h_local_verified",
)


class InvalidN50OperatorWitness(ValueError):
    """Untrusted or contradictory evidence must not reach an HTML report."""


def _require(ok: bool) -> None:
    if not ok:
        raise InvalidN50OperatorWitness("n50_ws_witness_unverified")


def validate_n50_ws_operator_witness(report: object, *, observed_at_ms: int) -> dict[str, Any]:
    """Validate the exact D323 contract, never infer liveness from timers."""
    _require(type(report) is dict)
    assert isinstance(report, dict)
    _require(set(report) == set(_empty_witness("owner_optin_required")))
    _require(report["schema_version"] == "j1-n50-ws-closed24h-owner-witness-v1")
    status = report["status"]
    _require(type(status) is str and status in _STATUSES)
    _require(type(observed_at_ms) is int and 1_600_000_000_000 <= observed_at_ms < 4_102_444_800_000)
    for key in _NEGATIVE_FLAGS:
        _require(report[key] is False)
    for key in _STATE_FLAGS:
        _require(type(report[key]) is bool)
    for key in ("network_requests", "database_mutation_statements"):
        _require(type(report[key]) is int and report[key] == 0)
    for key, value in (
        ("expected_closed_hours", 24), ("expected_contracts_per_hour", 50),
    ):
        _require(type(report[key]) is int and report[key] == value)
    closed = report["verified_closed_hours"]
    per_hour = report["verified_contracts_per_hour"]
    rows = report["persisted_ws_rows"]
    _require(type(closed) is int and closed in (0, 24))
    _require(type(per_hour) is int and per_hour in (0, 50))
    _require(type(rows) is int and 0 <= rows <= 1_000_000)
    end = report["latest_eligible_closed_end_ms"]
    if end is not None:
        _require(type(end) is int and end % _HOUR_MS == 0)
        _require(0 <= observed_at_ms - end < _HOUR_MS)
    for key in (
        "ranked_scope_sha256", "ws_metadata_sha256",
        "ws_journal_sha256", "last_hour_sha256",
    ):
        value = report[key]
        _require(value is None or (type(value) is str and _SHA.fullmatch(value) is not None))
    if report["ws_journal_integrity_verified"]:
        _require(all(report[k] is not None for k in (
            "ranked_scope_sha256", "ws_metadata_sha256", "ws_journal_sha256",
        )))
    else:
        _require(rows == 0)
        _require(all(report[k] is None for k in (
            "ranked_scope_sha256", "ws_metadata_sha256", "ws_journal_sha256",
        )))
    if status == "ws_24h_local_evidence_verified":
        _require(report["ws_closed_24h_local_verified"] is True)
        _require(closed == 24 and per_hour == 50 and rows >= 1200)
        _require(report["ws_journal_integrity_verified"] is True)
        _require(report["last_hour_sha256"] is not None and end is not None)
        _require(all(report[k] for k in (
            "ws_timer_active_enabled", "rotation_timer_active_enabled",
            "n2_quiesced", "old_rest_n50_quiesced", "ws_service_not_failed",
        )))
    else:
        _require(report["ws_closed_24h_local_verified"] is False)
        _require(closed == 0 and per_hour == 0)
        _require(report["last_hour_sha256"] is None)
    # All values exposed here are derived exclusively from validated D323 fields.
    return {
        "status": status,
        "label": _STATUSES[status][0],
        "severity": _STATUSES[status][1],
        "observed_at_ms": observed_at_ms,
        "latest_closed_end_ms": end,
        "verified_closed_hours": closed,
        "persisted_rows": rows if report["ws_journal_integrity_verified"] else None,
        "ws_timer": report["ws_timer_active_enabled"],
        "rotation_timer": report["rotation_timer_active_enabled"],
        "n2_standby": report["n2_quiesced"],
        "rest_n50_off": report["old_rest_n50_quiesced"],
        "service_not_failed": report["ws_service_not_failed"],
        "journal_integrity": report["ws_journal_integrity_verified"],
        "local24": report["ws_closed_24h_local_verified"],
    }


def _utc(ms: int | None) -> str:
    if ms is None:
        return "Ainda não observado"
    return datetime.fromtimestamp(ms // 1000, tz=timezone.utc).strftime("%d/%m/%Y %H:%M UTC")


def render_n50_ws_operator_html(report: object, *, observed_at_ms: int) -> str:
    """Static PT-BR mobile HTML. No scripts, account data, prices or symbols."""
    view = validate_n50_ws_operator_witness(report, observed_at_ms=observed_at_ms)
    def state(flag: bool, yes: str, no: str) -> str:
        return escape(yes if flag else no, quote=True)

    rows = "—" if view["persisted_rows"] is None else str(view["persisted_rows"])
    status = escape(view["label"], quote=True)
    severity = view["severity"]
    html = f"""<!doctype html>
<html lang="pt-BR"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; connect-src 'none'; object-src 'none'">
<meta name="color-scheme" content="dark">
<title>N50 · Estado operacional privado</title>
<style>
:root{{color-scheme:dark;font-family:system-ui,-apple-system,sans-serif;background:#0d1722;color:#f3f7fb}}
*{{box-sizing:border-box}} body{{margin:0;line-height:1.5}}
main,header,footer{{max-width:980px;margin:auto;padding:20px}}
h1{{font-size:clamp(1.8rem,5vw,2.6rem);line-height:1.15}}
h2{{font-size:1.13rem}} p{{color:#c1cfda}} .top{{color:#90e0d0;font-size:.83rem;font-weight:750}}
.box{{background:#172a3c;border:1px solid #435c70;border-radius:15px;padding:20px;margin-top:15px}}
.banner{{border-left:5px solid #f5cd78}} .local{{border-left-color:#86dbb7}}
.fallback,.blocked{{border-left-color:#f2a7a7}}
.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}}
dt{{color:#c1cfda;font-size:.84rem}} dd{{margin:8px 0 0;font-weight:750;font-size:1.2rem;overflow-wrap:anywhere}}
.value{{font-variant-numeric:tabular-nums}} .note{{font-size:.86rem;color:#c1cfda}}
.skip{{position:absolute;top:-70px;left:8px;background:#f6e2a6;color:#071522;padding:10px}}
.skip:focus{{top:8px}} :focus-visible{{outline:3px solid #f6e2a6;outline-offset:3px}}
@media(max-width:560px){{.grid{{grid-template-columns:1fr}}main,header,footer{{padding:16px}}}}
</style></head><body>
<a class="skip" href="#conteudo">Pular para o conteúdo</a>
<header><div class="top">CRYPTO INTELLIGENCE AGENT · J5/D330</div></header>
<main id="conteudo" tabindex="-1" data-mode="offline_readonly" data-trading="disabled">
<h1>Coleta N50: estado operacional</h1>
<p>Leitura local do auditor D323. Não envia ordens nem liga serviços.</p>
<section class="box banner {severity}" aria-label="Estado da auditoria">
<h2>Estado verificado pelo auditor</h2><strong>{status}</strong>
<p class="note">Timer habilitado não significa candle recebido. Evidência de 24h só existe após auditoria integral de 50 contratos por hora.</p>
</section>
<div class="grid" aria-label="Indicadores de operação">
<dl class="box"><dt>Horas integralmente comprovadas</dt><dd class="value">{view["verified_closed_hours"]} / 24</dd></dl>
<dl class="box"><dt>Registros WS com integridade verificada</dt><dd class="value">{rows}</dd></dl>
<dl class="box"><dt>Agendamento N50</dt><dd>{state(view["ws_timer"],"Ativo e habilitado","Não confirmado")}</dd></dl>
<dl class="box"><dt>Rotação agendada</dt><dd>{state(view["rotation_timer"],"Ativa e habilitada","Não confirmada")}</dd></dl>
<dl class="box"><dt>Fallback REST N2</dt><dd>{state(view["n2_standby"],"Em espera","Verificar / pode ter sido acionado")}</dd></dl>
<dl class="box"><dt>Integridade SQLite WS</dt><dd>{state(view["journal_integrity"],"Journal auditado","Ainda não comprovada")}</dd></dl>
</div>
<section class="box" aria-labelledby="limites">
<h2 id="limites">Limites desta evidência</h2>
<p>Mesmo com 24 horas locais aprovadas, isso não comprova operação contínua 24/7, rotação real de 36h, identidade global dos 50 ativos, retorno financeiro, disponibilidade para negociação nem autorização de sinais.</p>
<p class="note">Serviço sem falha detectada: {state(view["service_not_failed"],"sim","não comprovado")}. REST N50 antigo desativado: {state(view["rest_n50_off"],"sim","não comprovado")}.</p>
</section>
<p class="note">Auditoria realizada: {_utc(view["observed_at_ms"])}. Último fechamento elegível: {_utc(view["latest_closed_end_ms"])}.</p>
<p class="note">Arquivo estático privado; não atualiza sozinho, não abre WebSocket e não está publicado na internet.</p>
</main><footer>Somente pesquisa e diagnóstico · Sem credenciais, ordens ou recomendações.</footer>
</body></html>"""
    encoded = html.encode("utf-8")
    _require(2000 <= len(encoded) <= _MAX_HTML)
    _require("<script" not in html.lower() and "<form" not in html.lower()
             and "http://" not in html.lower() and "https://" not in html.lower())
    return html


def write_n50_ws_operator_html_once(
    report: object, *, observed_at_ms: int,
    root_directory: Path = _OWNER_ROOT,
    allow_private_report_write: bool = False,
    owner_ok: bool | None = None,
) -> dict[str, Any]:
    """Save a private, immutable 0600 HTML under an already owned 0700 directory."""
    out = {
        "schema_version": "j5-n50-ws-operator-html-save-v1",
        "status": "optin_required", "file_name": None,
        "digest_sha256": None, "orders_sent": False,
        "network_requests": 0, "systemd_modified": False,
        "ws_database_modified": False,
    }
    if allow_private_report_write is not True:
        return out
    out["status"] = "blocked"
    permitted = ((os.name == "posix" and os.getuid() == os.geteuid()
                  and os.geteuid() != 0) if owner_ok is None else owner_ok)
    if (permitted is not True or type(root_directory) is not Path
            or not root_directory.is_absolute() or root_directory.is_symlink()):
        return out
    try:
        html = render_n50_ws_operator_html(report, observed_at_ms=observed_at_ms)
        root_stat = root_directory.lstat()
        if (root_directory.resolve(strict=True) != root_directory
                or not stat.S_ISDIR(root_stat.st_mode)
                or root_stat.st_uid != os.geteuid()
                or stat.S_IMODE(root_stat.st_mode) != 0o700):
            return out
        parent = root_directory / "operator-reports"
        if not parent.exists() and not parent.is_symlink():
            parent.mkdir(mode=0o700)
        parent_stat = parent.lstat()
        if (parent.is_symlink() or not stat.S_ISDIR(parent_stat.st_mode)
                or parent_stat.st_uid != os.geteuid()
                or stat.S_IMODE(parent_stat.st_mode) != 0o700):
            return out
        body = html.encode("utf-8")
        digest = sha256(body).hexdigest()
        name = f"n50-ws-ops-{observed_at_ms}.html"
        dest = parent / name
        if dest.exists() or dest.is_symlink():
            old = dest.lstat()
            if (dest.is_symlink() or not stat.S_ISREG(old.st_mode)
                    or old.st_uid != os.geteuid() or old.st_nlink != 1
                    or stat.S_IMODE(old.st_mode) != 0o600
                    or dest.read_bytes() != body):
                return out
            out.update(status="identical_private_report_exists",
                       file_name=name, digest_sha256=digest)
            return out
        fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                     getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            with os.fdopen(fd, "wb", closefd=False) as stream:
                stream.write(body)
                stream.flush()
                os.fsync(fd)
        finally:
            os.close(fd)
        saved = dest.lstat()
        if (not stat.S_ISREG(saved.st_mode) or saved.st_uid != os.geteuid()
                or saved.st_nlink != 1 or stat.S_IMODE(saved.st_mode) != 0o600):
            return out
        dfd = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
        out.update(status="private_report_saved",
                   file_name=name, digest_sha256=digest)
        return out
    except (OSError, ValueError, TypeError, OverflowError, UnicodeError):
        return out
