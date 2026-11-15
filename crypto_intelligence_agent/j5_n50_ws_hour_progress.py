"""J5/PROGRESS1: mobile log-derived hourly N50 status, not a D323 proof.

Consumes only already-sanitized owner-runner reports supplied by the caller.
No journald access, private paths, SQLite, network or order capabilities.
"""
from __future__ import annotations

from datetime import datetime, timezone
from html import escape
import re
from typing import Any, Sequence

from .bybit_closed_stream_cache import HOUR_MS
from .market_data import DataValidationError

_SHA = re.compile(r"[0-9a-f]{64}\Z")
_OK = "ws_owner_hour_50_observed_local_only"
_FAILED = frozenset({
    "ws_owner_hour_audit_abstain",
    "ws_owner_hour_incomplete_no_pit",
    "ws_owner_lease_degraded_abstain",
    "ws_owner_integrity_or_lock_abstain",
    "ws_owner_preflight_abstain",
    "ws_owner_window_integrity_abstain",
    "ws_owner_window_scope_abstain",
})
_MAX_EVENTS = 4_096
_SETTLE_MS = 180_000
_MIN_MS = 1_600_000_000_000
_MAX_MS = 4_102_444_800_000
_LABEL = {
    "ok": "50/50 no relatório",
    "failed": "Falha ou abstenção",
    "missing": "Sem relatório válido",
    "duplicate": "Relatórios duplicados",
}


def _utc(value: int) -> str:
    return datetime.fromtimestamp(value // 1000, tz=timezone.utc).strftime(
        "%d/%m %H:%M UTC"
    )


def _entry(item: object, now_ms: int) -> tuple[int, bool, tuple[str, str] | None]:
    """Reject invalid reports rather than treating appends/ACK as success."""
    if type(item) is not dict or set(item) != {"finished_at_ms", "report"}:
        raise DataValidationError("bounded sanitized service record required")
    finished = item["finished_at_ms"]
    report = item["report"]
    if (type(finished) is not int or not _MIN_MS <= finished <= now_ms
            or type(report) is not dict
            or report.get("schema_version") != "j1-n50-ws-cached-owner-window-v1"
            or type(report.get("status")) is not str
            or report["status"] not in (_FAILED | {_OK})
            or type(report.get("expected_contracts")) is not int
            or report["expected_contracts"] != 50
            or type(report.get("confirmed_contracts")) is not int
            or not 0 <= report["confirmed_contracts"] <= 50
            or type(report.get("missing_contracts")) is not int
            or report["missing_contracts"] != 50-report["confirmed_contracts"]
            or type(report.get("closed_events_appended_to_ws_journal")) is not int
            or not 0 <= report["closed_events_appended_to_ws_journal"] <= 50
            or type(report.get("subscription_acks")) is not int
            or not 0 <= report["subscription_acks"] <= 10
            or report.get("orders_sent") is not False
            or report.get("rest_database_modified") is not False
            or report.get("systemd_modified") is not False
            or type(report.get("http_gets")) is not int
            or report["http_gets"] != 0):
        raise DataValidationError("untrusted N50 count-only service report")
    status = report["status"]
    end = report.get("utc_closed_hour_end_ms")
    if end is None:
        # A failed lease may not have an attested UTC end. Assign it only
        # when its completion is within the bounded postclose window.
        if status == _OK:
            raise DataValidationError("successful report lacks closed hour")
        end = finished - (finished % HOUR_MS)
    if (type(end) is not int or not _MIN_MS <= end <= finished
            or end % HOUR_MS or not 1_000 <= finished - end <= _SETTLE_MS):
        raise DataValidationError("service report not attributable to a closed UTC hour")
    if status == _OK:
        digest = report.get("hour_evidence_sha256")
        if (report["confirmed_contracts"] != 50
                or report["missing_contracts"] != 0
                or type(digest) is not str or _SHA.fullmatch(digest) is None
                or report.get("source_provenance") != "bybit_public_ws_confirmed"
                or report["subscription_acks"] < 1):
            raise DataValidationError("50 appends without valid auditor digest is not success")
    # These digests are hints from service logs, not an audit of private
    # epochs or SQLite. Legacy reports without both remain usable for
    # hourly counts, but never produce same-cohort continuity.
    ranked = report.get("ranked_scope_sha256")
    metadata = report.get("ws_metadata_sha256")
    if ((ranked is None) != (metadata is None)
            or ranked is not None and (
                type(ranked) is not str or _SHA.fullmatch(ranked) is None
                or type(metadata) is not str or _SHA.fullmatch(metadata) is None
            )):
        raise DataValidationError("malformed or partial N50 cohort digests")
    scope = (ranked, metadata) if status == _OK and ranked is not None else None
    return end, status == _OK, scope


def project_n50_ws_log_progress(
    events: Sequence[object], *, now_ms: int,
) -> dict[str, Any]:
    """Exactly 24 finished hourly slots, no continuation inferred from timers.

    Success here is merely an observation of a sanitised log: it cannot
    certify D323 journal replay, scope lineage or 24h financial readiness.
    """
    if (type(now_ms) is not int or not _MIN_MS <= now_ms < _MAX_MS
            or type(events) not in (list, tuple)
            or len(events) > _MAX_EVENTS):
        raise DataValidationError("bounded UTC log window required")
    phase = now_ms % HOUR_MS
    latest = now_ms - phase - (HOUR_MS if phase < _SETTLE_MS else 0)
    if latest < _MIN_MS:
        raise DataValidationError("no complete closed reporting window")
    by_hour: dict[int, list[tuple[bool, tuple[str, str] | None]]] = {}
    for item in events:
        end, success, scope = _entry(item, now_ms)
        # Validate even records outside the projection window, but do not
        # count historical slots or an unfinished current hour.
        if end > latest:
            raise DataValidationError("future or not-yet-settled reporting hour")
        by_hour.setdefault(end, []).append((success, scope))

    slots = []
    scopes_by_slot: list[tuple[str, str] | None] = []
    for i in range(23, -1, -1):
        end = latest - HOUR_MS * i
        attempts = by_hour.get(end, [])
        state = ("missing" if not attempts else
                 "duplicate" if len(attempts) != 1 else
                 "ok" if attempts[0][0] else "failed")
        slots.append({"closed_end_ms": end, "state": state})
        # Neither hashes nor symbols leave this module: only counters do.
        scopes_by_slot.append(attempts[0][1] if state == "ok" else None)

    streak = 0
    for row in reversed(slots):
        if row["state"] != "ok":
            break
        streak += 1
    counts = {state: sum(row["state"] == state for row in slots) for state in _LABEL}
    latest_scope = scopes_by_slot[-1]
    current_scope_streak = 0
    if latest_scope is not None:
        for slot, scope in zip(reversed(slots), reversed(scopes_by_slot)):
            if slot["state"] != "ok" or scope != latest_scope:
                break
            current_scope_streak += 1
    known_scopes = {
        scope for slot, scope in zip(slots, scopes_by_slot)
        if slot["state"] == "ok" and scope is not None
    }
    return {
        "schema_version": "j5-n50-ws-log-progress-v1",
        "quality": "sanitized_service_log_observation_only",
        "as_of_ms": now_ms,
        "latest_eligible_closed_end_ms": latest,
        "hours_in_window": 24,
        "observed_50_of_50_hours": counts["ok"],
        "consecutive_recent_observed_hours": streak,
        "same_scope_recent_50_of_50_hours": current_scope_streak,
        "scope_evidence_available": latest_scope is not None,
        "scope_changed_in_window": len(known_scopes) > 1,
        "failed_hours": counts["failed"],
        "missing_hours": counts["missing"],
        "duplicate_hours": counts["duplicate"],
        "slots": slots,
        "owner_d323_24h_audit_verified": False,
        "rotation_36h_live_verified": False,
        "continuous_collector_verified": False,
        "marketwide_top50_verified": False,
        "crypto_identity_independently_verified": False,
        "source_authenticated": False,
        "approved_for_signals": False,
        "live_trading_authorized": False,
        "orders_sent": False,
        "network_requests": 0,
        "database_accessed": False,
        "systemd_modified": False,
    }


def render_n50_ws_log_progress_html(events: Sequence[object], *, now_ms: int) -> str:
    """Static, accessible mobile timeline. Nothing from log payload is echoed."""
    summary = project_n50_ws_log_progress(events, now_ms=now_ms)
    cohort = summary["same_scope_recent_50_of_50_hours"]
    cohort_text = f"{cohort} / 24" if summary["scope_evidence_available"] else "indisponível"
    scope_note = ("Mudança de coorte observada nos digests dos logs; não é falha de coleta."
                  if summary["scope_changed_in_window"] else
                  "Coorte observada apenas nos logs; a SQLite exige auditoria D323."
                  if summary["scope_evidence_available"] else
                  "Digests de coorte indisponíveis; não inferir continuidade.")
    cells = "".join(
        '<li class="slot ' + row["state"] + '" aria-label="' +
        escape(_utc(row["closed_end_ms"]), quote=True) + ": " +
        escape(_LABEL[row["state"]], quote=True) + '">' +
        '<time>' + escape(_utc(row["closed_end_ms"]), quote=True) + '</time>' +
        '<strong>' + escape(_LABEL[row["state"]], quote=True) + '</strong></li>'
        for row in summary["slots"]
    )
    html = f"""<!doctype html>
<html lang="pt-BR">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; connect-src 'none'; object-src 'none'">
<meta name="color-scheme" content="dark">
<title>N50 · Histórico de horas observadas</title>
<style>
:root{{font:16px system-ui,-apple-system,sans-serif;color-scheme:dark;background:#0c1622;color:#e9f1f6}}
*{{box-sizing:border-box}}body{{margin:0;line-height:1.45}}main{{max-width:980px;padding:18px;margin:auto}}
h1{{font-size:clamp(1.5rem,4vw,2.3rem)}}p{{color:#c1cfdc}}.warning{{padding:14px;border:1px solid #e6c879;border-radius:12px;background:#263039}}
.metrics{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin:16px 0}}
.metrics div,.slot{{background:#172b3a;border:1px solid #456176;border-radius:10px;padding:12px}}
.metrics strong{{display:block;font-size:1.5rem;font-variant-numeric:tabular-nums}}
.metrics span,.slot time{{color:#c1cfdc;font-size:.83rem}}
.timeline{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;padding:0;list-style:none}}
.slot{{min-width:0;border-left:5px solid #e3bf7b}}.slot.ok{{border-left-color:#80d7ae}}
.slot.failed,.slot.duplicate{{border-left-color:#efaaaa}}
.slot strong{{display:block;overflow-wrap:anywhere;margin-top:6px}}
@media(max-width:570px){{.timeline{{grid-template-columns:repeat(2,minmax(0,1fr))}}}}
</style></head><body>
<main data-mode="offline_readonly" data-trading="disabled">
<h1>N50 · últimas 24 horas elegíveis</h1>
<div class="warning" role="note"><strong>Acompanhamento preliminar, não homologação.</strong>
<p>Os números vêm de relatórios sanitizados do serviço WS. Apenas a auditoria privada D323 pode comprovar a janela contínua de 24h no journal SQLite. Timer ativo ou 50 gravações sem auditoria não contam como 50/50.</p></div>
<section class="metrics" aria-label="Resumo das observações">
<div><span>Horas 50/50 observadas nos logs</span><strong>{summary["observed_50_of_50_hours"]} / 24</strong></div>
<div><span>Sequência recente sem lacunas</span><strong>{summary["consecutive_recent_observed_hours"]}</strong></div>
<div><span>Sequência da mesma coorte (somente logs)</span><strong>{cohort_text}</strong></div>
<div><span>Falhas ou abstenções</span><strong>{summary["failed_hours"]}</strong></div>
<div><span>Ausências e duplicatas</span><strong>{summary["missing_hours"] + summary["duplicate_hours"]}</strong></div>
</section>
<p>{escape(scope_note)}</p>
<h2>Fechamentos UTC, mais antigos primeiro</h2><ol class="timeline">{cells}</ol>
<p>Atualizado em {_utc(summary["as_of_ms"])}. O fechamento elegível mais recente é {_utc(summary["latest_eligible_closed_end_ms"])}.</p>
<p>Arquivo local estático: não atualiza automaticamente; não consulta exchange, lê banco nem envia ordens. Nenhum ativo, preço, digest ou credencial é exibido. A rotação 36h e a identidade crypto-only exigem verificações separadas.</p>
</main></body></html>"""
    if (len(html.encode("utf-8")) > 32768
            or "<script" in html.lower() or "<form" in html.lower()
            or "https://" in html.lower() or "http://" in html.lower()):
        raise DataValidationError("unsafe mobile report output")
    return html
