"""J1/OPS1: strictly read-only status of an owner-operated EXIT5 worker.

This intentionally does not inspect SQLite while a writer might be running.
It summarizes ONLY existing, owner-private, bounded JSON artifacts and never
claims that a log entry proves the worker's process is still running. No
network, database writes, credentials, symbols, URLs or market values.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat
from typing import Any

_MAX_LOG_BYTES = 1_048_576
_MAX_JSON_BYTES = 65_536
_MAX_LOG_LINES = 2_000
_MAX_GETS = 500
_MAX_PITS = 50
_SUCCESS = "private_j1_two_distinct_updates_verified_not_top50"
_PROGRESS_PHASES = frozenset({
    "current_pit_verified", "waiting_for_next_closed_hour",
    "hourly_pit_verified", "initial_private_state_verified",
})
_FAILURE_CODES = frozenset({
    "provider_rate_limit_no_retry", "provider_region_restriction",
    "provider_http_error_no_retry", "access_region_or_rate_limit_no_retry",
    "network_error_no_retry", "resume_hourly_observation_window_missed",
    "resume_get_budget_exceeded_before_fetch", "resume_52_get_time_budget_exceeded",
    "resume_pit_hour_expired_before_write", "private_resume_failed_sanitized",
    "resume_catchup_exceeds_144h_safety_limit",
})
_ALLOWED_NAMES = (
    "exit5-result.json", "exit5-audit.json", "exit5-resume.log",
)


class PrivateJ1StatusError(ValueError):
    """Always report sanitized fixed error categories, never path/payload."""


def _strict_object_pairs(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _decode(raw: bytes) -> dict:
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_strict_object_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise PrivateJ1StatusError("status_artifact_invalid_json") from None
    if type(value) is not dict:
        raise PrivateJ1StatusError("status_artifact_not_object")
    return value


def _private_directory(directory: str | Path) -> Path:
    if os.name != "posix" or not isinstance(directory, (str, Path)):
        raise PrivateJ1StatusError("owner_private_posix_directory_required")
    path = Path(directory).expanduser()
    if (not path.is_absolute()
            or any(part.is_symlink() for part in (path, *path.parents))):
        raise PrivateJ1StatusError("owner_private_absolute_directory_required")
    try:
        metadata = path.lstat()
    except OSError:
        raise PrivateJ1StatusError("owner_private_directory_unavailable") from None
    if (not stat.S_ISDIR(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o700
            or metadata.st_uid != os.getuid()):
        raise PrivateJ1StatusError("owner_private_directory_permissions_rejected")
    return path


def _read_private_file(directory: Path, name: str) -> bytes | None:
    if name not in _ALLOWED_NAMES:
        raise PrivateJ1StatusError("status_artifact_name_rejected")
    path = directory / name
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(path, flags)
    except FileNotFoundError:
        return None
    except OSError:
        raise PrivateJ1StatusError("status_artifact_unavailable_or_symlink") from None
    try:
        metadata = os.fstat(fd)
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid()
                or stat.S_IMODE(metadata.st_mode) != 0o600
                or metadata.st_nlink != 1):
            raise PrivateJ1StatusError("status_artifact_permissions_rejected")
        size_limit = _MAX_LOG_BYTES if name.endswith(".log") else _MAX_JSON_BYTES
        if not 1 <= metadata.st_size <= size_limit:
            raise PrivateJ1StatusError("status_artifact_size_rejected")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            content = stream.read(size_limit + 1)
        if not 1 <= len(content) <= size_limit:
            raise PrivateJ1StatusError("status_artifact_size_rejected")
        return content
    finally:
        os.close(fd)


def _valid_counter(value: Any, minimum: int = 0, maximum: int = 1_000_000) -> int | None:
    return value if type(value) is int and minimum <= value <= maximum else None


def _last_progress(raw: bytes | None) -> dict:
    if raw is None:
        return {"phase": None, "network_gets": None, "pit_updates": None,
                "worker_final_status": None, "provider_ret_code": None}
    lines = raw.splitlines()
    if len(lines) > _MAX_LOG_LINES:
        raise PrivateJ1StatusError("status_worker_log_line_budget_exceeded")
    out = {"phase": None, "network_gets": None, "pit_updates": None,
           "worker_final_status": None, "provider_ret_code": None}
    for line in lines:
        item = _decode(line)
        if item.get("event") == "private_j1_resume_progress":
            phase = item.get("phase")
            count = _valid_counter(item.get("network_gets_attempted"), 0, _MAX_GETS)
            updates = _valid_counter(
                item.get("distinct_pit_updates_after_initial"), 0, _MAX_PITS)
            if phase not in _PROGRESS_PHASES or count is None or updates is None:
                raise PrivateJ1StatusError("status_worker_progress_invalid")
            # Status is read in chronological order, never extrapolated.
            if out["network_gets"] is not None and count < out["network_gets"]:
                raise PrivateJ1StatusError("status_worker_get_counter_rewound")
            if out["pit_updates"] is not None and updates < out["pit_updates"]:
                raise PrivateJ1StatusError("status_worker_pit_counter_rewound")
            out.update(phase=phase, network_gets=count, pit_updates=updates)
        elif "status" in item:
            value = item["status"]
            out["worker_final_status"] = (
                value if type(value) is str and
                value in _FAILURE_CODES | {_SUCCESS}
                else "worker_unclassified_status"
            )
            code = _valid_counter(item.get("provider_ret_code"), 0, 100_000)
            out["provider_ret_code"] = code
        else:
            # Unknown progress objects cannot grant success or expose content.
            continue
    return out


def _exit_codes(raw: bytes | None) -> tuple[int | None, int | None]:
    if raw is None:
        return None, None
    item = _decode(raw)
    if set(item) != {"resume_exit_code", "audit_exit_code"}:
        raise PrivateJ1StatusError("status_exit_receipt_invalid")
    capture = _valid_counter(item["resume_exit_code"], 0, 255)
    audit = _valid_counter(item["audit_exit_code"], 0, 255)
    if capture is None or audit is None:
        raise PrivateJ1StatusError("status_exit_receipt_invalid")
    return capture, audit


def _audit_summary(raw: bytes | None) -> dict:
    if raw is None:
        return {"available": False, "valid": False, "pits": None,
                "assets": None, "candles": None, "consecutive": None}
    report = _decode(raw)
    pits = _valid_counter(report.get("immutable_pit_snapshots"), 0, _MAX_PITS)
    assets = _valid_counter(report.get("latest_selected_asset_count"), 0, 52)
    sampled = _valid_counter(report.get("sample_asset_count"), 0, 52)
    candles = _valid_counter(report.get("stored_closed_candle_rows"), 0, 100_000)
    consecutive = _valid_counter(report.get("consecutive_snapshots_at_end"), 0, _MAX_PITS)
    minimum_hours = _valid_counter(report.get("min_hours_per_asset"), 0, 10_000)
    valid = (
        report.get("status") == "private_bybit_progress_readonly_verified"
        and report.get("sqlite_integrity_passed") is True
        and report.get("private_page_replay_passed") is True
        and report.get("first_pit_720h_coverage") is True
        and report.get("network_requests") == 0
        and pits is not None and pits >= 3
        and assets == 50 and sampled is not None and 50 <= sampled <= 52
        and candles is not None and candles >= 36_000
        and consecutive is not None and consecutive >= 1
        and minimum_hours is not None and minimum_hours >= 720
    )
    return {"available": True, "valid": valid,
            "pits": pits, "assets": assets, "candles": candles,
            "consecutive": consecutive}


def observe_private_exit5(*, directory: str | Path,
                          allow_private_readonly_status: bool = False) -> dict:
    """Summarize explicit owner-private artifacts; no process-status assertion.

    A success requires BOTH exit codes zero, the worker's final success event,
    and the independent read-only audit. A progress event alone never passes.
    """
    if allow_private_readonly_status is not True:
        raise PrivateJ1StatusError("status_owner_opt_in_required")
    target = _private_directory(directory)
    result_raw = _read_private_file(target, _ALLOWED_NAMES[0])
    audit_raw = _read_private_file(target, _ALLOWED_NAMES[1])
    log_raw = _read_private_file(target, _ALLOWED_NAMES[2])
    progress = _last_progress(log_raw)
    resume_rc, audit_rc = _exit_codes(result_raw)
    audit = _audit_summary(audit_raw)

    if result_raw is not None:
        if (resume_rc == 0 and audit_rc == 0
                and progress["worker_final_status"] == _SUCCESS
                and audit["valid"]):
            status = "concluido_amostra_revisada_auditada"
        elif resume_rc != 0 or audit_rc != 0:
            status = "falha_registrada_pelo_worker"
        else:
            status = "resultado_inconsistente_sem_aceite"
    elif audit_raw is not None:
        status = "auditoria_sem_recibo_final_sem_aceite"
    elif progress["worker_final_status"] is not None:
        status = ("worker_reportou_conclusao_sem_recibo"
                  if progress["worker_final_status"] == _SUCCESS
                  else "worker_reportou_falha_sem_recibo")
    elif progress["phase"] == "waiting_for_next_closed_hour":
        status = "aguardando_proximo_fechamento_informado"
    elif progress["phase"] in _PROGRESS_PHASES:
        status = "progresso_informado_sem_resultado"
    else:
        status = "sem_resultado_final"

    return {
        "status": status,
        "worker_running_verified": False,
        "worker_phase_reported": progress["phase"],
        "network_gets_reported": progress["network_gets"],
        "pit_updates_reported": progress["pit_updates"],
        "provider_ret_code_reported": progress["provider_ret_code"],
        "worker_final_status_reported": progress["worker_final_status"],
        "resume_exit_code": resume_rc,
        "audit_exit_code": audit_rc,
        "audit_available": audit["available"],
        "audit_accepted": audit["valid"] if audit["available"] else False,
        "immutable_pit_snapshots_audited": audit["pits"],
        "latest_selected_assets_audited": audit["assets"],
        "closed_candles_audited": audit["candles"],
        "consecutive_hourly_updates_audited": audit["consecutive"],
        "marketwide_top50_verified": False,
        "live_trading_authorized": False,
        "network_requests_by_observer": 0,
        "data_written_by_observer": False,
        "orders_sent": False,
    }