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
    price_symbols_validated: int
    public_gets_on_success: int
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
    max_price_symbols: int = 1,
) -> LocalCaptureSummary:
    """Collect bounded CURRENT crypto universe and closed price-only 1h pages.

    At most 2 + max_price_symbols GET calls (2 metadata and <=5 charts).
    Validate provider responses before opening or writing the local database.
    The store's two record families are individually transactional; a crash
    between them can leave a valid partial capture, not a completed session.
    Replays detect conflicts and preserve first-observed prices.
    """
    if allow_public_network is not True or allow_private_persistence is not True:
        raise LocalResearchError("double_opt_in_required")
    if type(max_price_symbols) is not int or not 1 <= max_price_symbols <= 5:
        raise LocalResearchError("max_price_symbols_must_be_between_1_and_5")
    target = _private_db_path(db_path)
    clock = clock_ms or (lambda: int(time() * 1000))
    started_at = _now(clock)
    if registry_bytes is not None and registry_variant != "btc-eth":
        raise LocalResearchError("injected_registry_revision_not_allowed")
    try:
        registry = (load_reviewed_registry(registry_variant, as_of_ms=started_at)
                    if registry_bytes is None else load_registry_json(registry_bytes))
    except DataValidationError as error:
        if "too old" in str(error):
            raise LocalResearchError("crypto_registry_stale_no_auto_renewal") from None
        raise LocalResearchError("crypto_registry_not_available_at_observation") from None
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

    # One shared UTC window, with a full-hour buffer beyond the last closed
    # bar. BTC is the mandatory anchor; only verified and live-ranked contracts
    # may fill up to N-1 additional slots. No fixed list of invented perps.
    aligned = (started_at // _HOUR_MS) * _HOUR_MS
    start, end = aligned - 4 * _HOUR_MS, aligned - _HOUR_MS
    selected = (_SYMBOL,) + tuple(
        row.symbol for row in ranked.eligible if row.symbol != _SYMBOL
    )[:max_price_symbols - 1]

    # Validate ALL sources before touching the database. A blocked/invalid
    # later chart must not create a new DB or partially archive earlier charts.
    validated_pages = []
    last_observed_at = decision_at
    for symbol in selected:
        captured = reader.staged_closed_candles(
            symbol=symbol, interval=_INTERVAL,
            start_open_ms=start, end_open_ms=end,
        )
        if (captured.staged.symbol != symbol
                or captured.staged.interval != _INTERVAL
                or captured.staged.start_open_ms != start
                or captured.staged.end_open_ms != end
                or captured.observed_at_ms < last_observed_at
                or captured.observed_at_ms - started_at > _MAX_CAPTURE_AGE_MS):
            raise LocalResearchError("invalid_private_chart_capture_timing")
        _validated_rows(captured)
        validated_pages.append((symbol, captured))
        last_observed_at = captured.observed_at_ms

    created = _create_private_file(target)
    try:
        archive = SQLiteKrakenPriceOnlyArchive(target)
        archive.save_universe_snapshot(ranked)
        added = 0
        covered = 0
        for symbol, captured in validated_pages:
            added += archive.commit_price_only(captured)
            quality = archive.price_quality(
                symbol=symbol, interval=_INTERVAL,
                start_open_ms=start, end_open_ms=end,
                as_of_ms=captured.observed_at_ms,
            )
            if not quality.complete or quality.captured != 3:
                raise LocalResearchError("private_sqlite_price_coverage_failed")
            covered += quality.captured
            if archive.candles(
                exchange="kraken_futures", market="linear_perpetual",
                symbol=symbol, interval=_INTERVAL,
                start_open_ms=start, end_open_ms=end,
            ):
                raise LocalResearchError("canonical_candle_table_must_remain_empty")
        restored = archive.universe_snapshot(
            observed_at_ms=ranked.observed_at_ms,
            selection_rule_version=ranked.selection_rule_version,
            source=ranked.source,
        )
        if restored != ranked:
            raise LocalResearchError("private_sqlite_roundtrip_failed")
        return LocalCaptureSummary(
            registry_sha256=registry.sha256_digest,
            selected_bases_limit=len(registry.assets),
            eligible_contracts=len(ranked.eligible),
            excluded_contracts=len(ranked.excluded),
            observed_at_ms=ranked.observed_at_ms,
            private_price_candles_added=added,
            price_candles_in_window=covered,
            price_window_complete=True,
            price_symbols_validated=len(validated_pages),
            public_gets_on_success=2 + len(validated_pages),
        )
    except Exception:
        # If newly created and the session fails, never silently leave a DB
        # that might be mistaken for an accepted completed capture. Existing
        # DBs retain individually validated transactional records.
        if created:
            target.unlink(missing_ok=True)
        raise
