"""J1/D332: owner-only count of actual N50 scope / legacy WS symbol grammar.

No ticker identities, OHLC, raw metadata, network, writes or service changes.
The audit may veto a future root WS cutover if the hypothesised single-base
grammar mismatch is not present in the sealed active N50 cohort.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import time
from typing import Any

from .bybit_closed_stream_cache import OfflineReviewedStreamScope
from .bybit_linear_candle_research import _SYMBOL as _CANDLE_SYMBOL
from .j1_auto_usdt_perp import _SYMBOL as _AUTO_SYMBOL
from .j1_auto_research_epoch import validate_ranked_research_scope
from .j1_n50_ws_epoch_rotation import _OWNER_ROOT, load_active_n50_ws_epoch
from .j1_n50_ws_private_cache import load_n50_ws_dynamic_admission
from .market_data import DataGapError, DataValidationError
from scripts.run_j1_current_ranked_epoch_once import load_private_ranked_scope

_STATE = _OWNER_ROOT / "active"
_LEGACY_CANDLE_SYMBOL = re.compile(r"^[A-Z0-9]{2,30}(?:USDT|USDC)$")
_ONE_CHAR_BASE = re.compile(r"[A-Z0-9]USDT\Z")


def _report(status: str) -> dict[str, Any]:
    return {
        "schema_version": "j1-n50-ws-symbol-grammar-owner-v1",
        "status": status,
        "reviewed_contracts": 0,
        "one_character_usdt_bases": 0,
        "legacy_candle_parser_rejections": 0,
        "new_candle_parser_rejections": 0,
        "network_requests": 0,
        "database_mutation_statements": 0,
        "systemd_modified": False,
        "orders_sent": False,
        "marketwide_top50_verified": False,
        "live_trading_authorized": False,
    }


def evaluate_n50_ws_symbol_grammar(scope: object) -> dict[str, Any]:
    """Count-only proof for a fixed immutable scope, never a symbol listing."""
    out = _report("scope_symbol_contract_abstain")
    if (type(scope) is not OfflineReviewedStreamScope
            or type(scope.contracts) is not tuple
            or len(scope.contracts) != 50):
        return out
    symbols: set[str] = set()
    old_rejections = new_rejections = single = 0
    for member in scope.contracts:
        symbol = getattr(member, "symbol", None)
        base = getattr(member, "base_coin", None)
        if (type(symbol) is not str or type(base) is not str
                or symbol in symbols or not _AUTO_SYMBOL.fullmatch(symbol)
                or symbol != base + "USDT"
                or getattr(member, "quote_coin", None) != "USDT"
                or getattr(member, "settle_coin", None) != "USDT"
                or getattr(member, "registry_sha256", None) != scope.registry_sha256):
            return out
        symbols.add(symbol)
        single += int(_ONE_CHAR_BASE.fullmatch(symbol) is not None)
        old_rejections += int(_LEGACY_CANDLE_SYMBOL.fullmatch(symbol) is None)
        new_rejections += int(_CANDLE_SYMBOL.fullmatch(symbol) is None)
    out.update(reviewed_contracts=50,
               one_character_usdt_bases=single,
               legacy_candle_parser_rejections=old_rejections,
               new_candle_parser_rejections=new_rejections)
    if new_rejections:
        out["status"] = "new_candle_parser_still_rejects_scope_abstain"
    elif single and old_rejections == single:
        out["status"] = "single_letter_legacy_mismatch_in_scope"
    else:
        out["status"] = "legacy_mismatch_not_established_abstain"
    return out


def observe_n50_ws_symbol_grammar_owner(
    *, allow_private_pointer_read: bool = False,
    allow_private_manifest_read: bool = False,
    allow_private_ws_scope_read: bool = False,
    allow_owner_symbol_grammar_audit: bool = False,
    now_ms: int | None = None,
) -> dict[str, Any]:
    """Owner-opt-in count-only read, same D321/D316 provenance as WS worker."""
    if not all((
        allow_private_pointer_read is True,
        allow_private_manifest_read is True,
        allow_private_ws_scope_read is True,
        allow_owner_symbol_grammar_audit is True,
    )):
        return _report("owner_optin_required")
    if (os.name != "posix" or os.getuid() != os.geteuid()
            or os.geteuid() == 0
            or (now_ms is not None and type(now_ms) is not int)):
        return _report("owner_environment_abstain")
    now = time.time_ns() // 1_000_000 if now_ms is None else now_ms
    try:
        active = load_active_n50_ws_epoch(
            state_directory=_STATE, current_at_ms=now,
            allow_private_pointer_read=True,
        )
        if (active.status != "active_n50_ws_epoch_revalidated"
                or active.manifest_directory is None
                or active.ws_directory is None
                or active.ranked_scope_sha256 is None
                or active.ws_metadata_sha256 is None):
            return _report("owner_active_ws_epoch_unavailable")
        ranked = load_private_ranked_scope(active.manifest_directory, now_ms=now)
        members, digest = validate_ranked_research_scope(
            ranked, now_ms=now, max_assets=50)
        cache = load_n50_ws_dynamic_admission(
            directory=active.ws_directory, current_at_ms=now,
            expected_ranked_scope_sha256=digest, allow_private_scope_read=True,
        )
        if (len(members) != 50 or digest != active.ranked_scope_sha256
                or cache.status != "private_n50_ws_admission_loaded_revalidated"
                or cache.admission is None or cache.ranked_scope != ranked
                or cache.admission.selected_contracts != 50
                or cache.admission.metadata_sha256 != active.ws_metadata_sha256):
            return _report("owner_ws_scope_integrity_abstain")
        return evaluate_n50_ws_symbol_grammar(cache.admission.ws_scope)
    except (DataValidationError, DataGapError, OSError, ValueError,
            TypeError, OverflowError, UnicodeError, KeyError):
        return _report("owner_readonly_scope_audit_abstain")
