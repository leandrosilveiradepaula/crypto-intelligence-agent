"""Private, opt-in Kraken BTC/ETH research capture (J1/WU36).

Reuse the existing Kraken read-only client, dated crypto registry, pure
selector and local SQLite store. This is never a canonical OHLCV or trading
adapter, contains no keys or order methods and never publishes raw data.

Real market access requires explicit double opt-in. No background scheduler.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from stat import S_IMODE
import os
from time import time
from typing import Any, Callable

from .crypto_asset_registry import CryptoRegistryHistory, load_registry_json
from .kraken_price_archive import (
    SQLiteKrakenPriceOnlyArchive, _validated_rows,
)
from .kraken_public_readonly import (
    KrakenPublicReadOnlyResearch, SOURCE as KRAKEN_CAPTURE_SOURCE,
)
from .market_data import DataValidationError
from .research_registry_catalog import load_reviewed_registry

_HOUR_MS = 3_600_000
_MAX_CAPTURE_AGE_MS = 30_000
_MAX_REGISTRY_AGE_MS = 7 * 86_400_000
_REPO_ROOT = Path(__file__).resolve().parent.parent
_REGISTRY_PATH = _REPO_ROOT / "registries" / "crypto-btc-eth-20261025-v1.json"
_SYMBOL = "PF_XBTUSD"
_INTERVAL = "1h"


class LocalResearchError(ValueError):
    """No financial or remote payloads are permitted in diagnostics."""


@dataclass(frozen=True)
class LocalCaptureSummary:
    registry_sha256: str
    selected_bases_limit: int
    eligible_contracts: int
    excluded_contracts: int
    observed_at_ms: int
    private_price_candles_added: int
    price_candles_in_window: int
    price_window_complete: bool
    canonical_ohlcv_approved: bool = False
    historical_top50_approved: bool = False
    public_or_commercial_rights_approved: bool = False
    orders_sent: bool = False


def _now(clock: Callable[[], int]) -> int:
    value = clock()
    if type(value) is not int or not 0 < value < 253_402_300_799_999:
        raise LocalResearchError("invalid_utc_clock")
    return value


def _private_db_path(db_path: str | Path) -> Path:
    if not isinstance(db_path, (str, Path)):
        raise LocalResearchError("absolute_private_database_path_required")
    path = Path(db_path).expanduser()
    if not path.is_absolute() or path.suffix not in (".sqlite", ".sqlite3", ".db"):
        raise LocalResearchError("absolute_private_sqlite_path_required")
    if path.is_symlink() or path.is_dir():
        raise LocalResearchError("database_must_not_be_symlink_or_directory")
    if path.parent.is_symlink() or not path.parent.is_dir():
        raise LocalResearchError("private_database_parent_must_exist")
    resolved = path.resolve(strict=False)
    if resolved == _REPO_ROOT or _REPO_ROOT in resolved.parents:
        raise LocalResearchError("never_save_market_data_inside_public_repository")
    if S_IMODE(path.parent.stat().st_mode) & 0o077:
        raise LocalResearchError("private_database_directory_permissions_required")
    if path.exists():
        if not path.is_file() or S_IMODE(path.stat().st_mode) & 0o077:
            raise LocalResearchError("existing_database_permissions_not_private")
    return path


def _create_private_file(path: Path) -> bool:
    """Create an owner-readable file if missing, not via a symlink."""
    if path.exists():
        return False
    flags = os.O_CREAT | os.O_EXCL | os.O_RDWR
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError:
        raise LocalResearchError("database_file_changed_during_capture") from None
    os.close(fd)
    return True


def capture_private_research(
    *, db_path: str | Path,
    allow_public_network: bool = False,
    allow_private_persistence: bool = False,
    client: Any | None = None,
    clock_ms: Callable[[], int] | None = None,
    registry_bytes: bytes | None = None,
    registry_variant: str = "btc-eth",
) -> LocalCaptureSummary:
    """Collect one bounded CURRENT BTC universe and 3 closed BTC 1h prices.

    At most three GET calls (instruments/tickers/chart) when opted in.
    Validate provider responses before opening or writing the local database.
    The store's two record families are individually transactional; a crash
    between them can leave a valid partial capture, not a completed session.
    Replays detect conflicts and preserve first-observed prices.
    """
    if allow_public_network is not True or allow_private_persistence is not True:
        raise LocalResearchError("double_opt_in_required")
    target = _private_db_path(db_path)
    clock = clock_ms or (lambda: int(time() * 1000))
    started_at = _now(clock)
    if registry_bytes is not None and registry_variant != "btc-eth":
        raise LocalResearchError("injected_registry_revision_not_allowed")
    registry = (load_reviewed_registry(registry_variant, as_of_ms=started_at)
                if registry_bytes is None else load_registry_json(registry_bytes))
    if registry.observed_at_ms > started_at:
        raise LocalResearchError("crypto_registry_not_yet_observed")
    if started_at - registry.observed_at_ms > _MAX_REGISTRY_AGE_MS:
        raise LocalResearchError("crypto_registry_stale_no_auto_renewal")
    history = CryptoRegistryHistory((registry,))

    reader = client or KrakenPublicReadOnlyResearch(allow_public_network=True)
    snapshot = reader.current_market_snapshot()  # two GET, no auth/order
    if (snapshot.source != KRAKEN_CAPTURE_SOURCE
            or type(snapshot.captured_start_ms) is not int
            or type(snapshot.captured_end_ms) is not int
            or snapshot.captured_start_ms < started_at
            or snapshot.captured_end_ms < snapshot.captured_start_ms
            or snapshot.captured_end_ms - started_at > _MAX_CAPTURE_AGE_MS):
        raise LocalResearchError("invalid_current_kraken_capture_clock")
    decision_at = _now(clock)
    if (decision_at < snapshot.captured_end_ms
            or decision_at - snapshot.captured_end_ms > _MAX_CAPTURE_AGE_MS):
        raise LocalResearchError("invalid_private_decision_clock")
    ranked = history.select_at(
        instruments=snapshot.instruments, tickers=snapshot.tickers,
        market_observed_at_ms=snapshot.observed_at_ms, decision_at_ms=decision_at,
        max_market_age_ms=_MAX_CAPTURE_AGE_MS,
        max_registry_age_ms=_MAX_REGISTRY_AGE_MS,
        max_symbols=min(50, len(registry.assets)),
    )
    if _SYMBOL not in {row.symbol for row in ranked.eligible}:
        raise LocalResearchError("btc_perpetual_not_eligible_in_current_snapshot")

    # The window is the three bars before the most recent fully closed hour.
    # A buffer of one full hour protects against the still-open newest bar.
    aligned = (started_at // _HOUR_MS) * _HOUR_MS
    start, end = aligned - 4 * _HOUR_MS, aligned - _HOUR_MS
    staged = reader.staged_closed_candles(
        symbol=_SYMBOL, interval=_INTERVAL,
        start_open_ms=start, end_open_ms=end,
    )  # third and last GET
    if (staged.staged.symbol != _SYMBOL or staged.staged.interval != _INTERVAL
            or staged.staged.start_open_ms != start
            or staged.staged.end_open_ms != end
            or staged.observed_at_ms < decision_at
            or staged.observed_at_ms - started_at > _MAX_CAPTURE_AGE_MS):
        raise LocalResearchError("invalid_private_chart_capture_timing")
    _validated_rows(staged)  # explicitly validate before disk I/O

    created = _create_private_file(target)
    try:
        archive = SQLiteKrakenPriceOnlyArchive(target)
        archive.save_universe_snapshot(ranked)
        added = archive.commit_price_only(staged)
        restored = archive.universe_snapshot(
            observed_at_ms=ranked.observed_at_ms,
            selection_rule_version=ranked.selection_rule_version,
            source=ranked.source,
        )
        quality = archive.price_quality(
            symbol=_SYMBOL, interval=_INTERVAL,
            start_open_ms=start, end_open_ms=end,
            as_of_ms=staged.observed_at_ms,
        )
        if restored != ranked or not quality.complete:
            raise LocalResearchError("private_sqlite_roundtrip_or_coverage_failed")
        if archive.candles(
            exchange="kraken_futures", market="linear_perpetual",
            symbol=_SYMBOL, interval=_INTERVAL,
            start_open_ms=start, end_open_ms=end,
        ):
            raise LocalResearchError("canonical_candle_table_must_remain_empty")
        return LocalCaptureSummary(
            registry_sha256=registry.sha256_digest,
            selected_bases_limit=len(registry.assets),
            eligible_contracts=len(ranked.eligible),
            excluded_contracts=len(ranked.excluded),
            observed_at_ms=ranked.observed_at_ms,
            private_price_candles_added=added,
            price_candles_in_window=quality.captured,
            price_window_complete=quality.complete,
        )
    except Exception:
        # If newly created and the session fails, never silently leave a DB
        # that might be mistaken for an accepted completed capture. Existing
        # DBs retain individually validated transactional records.
        if created:
            target.unlink(missing_ok=True)
        raise
