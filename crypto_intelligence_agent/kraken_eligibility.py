"""Conservative, offline-only research screening for Kraken USD crypto perpetuals.

Do NOT infer crypto-only membership from a PF_/PI_ symbol, flexible_futures
type, or tradfi=false flag: the live venue includes tokenized equities with
all those characteristics.

This pure module accepts a caller-verified crypto base registry and one
contemporaneous Kraken instruments/tickers observation. It does not fetch
APIs, reconstruct historical membership, trade, or authorize a provider swap.
"""
from __future__ import annotations

from decimal import Decimal
from .decimal_json import positive_market_decimal
import re
from typing import Any, Mapping, Sequence

from .market_data import DataValidationError, UniverseMember, UniverseSnapshot


RESEARCH_SOURCE = "kraken_futures_public_research"
_BLOCKED_CATEGORIES = frozenset({
    "xstocks", "equities", "forex", "commodities", "pre-ipo", "indices",
})
_BASE_NAME = re.compile(r"^[A-Z0-9]{2,24}$")
_INSTRUMENT_NAME = re.compile(r"^PF_[A-Z0-9]{2,36}$")


def _decimal_positive(value: Any, label: str) -> Decimal:
    # Do not restore source digits with Decimal(str(binary_float)).
    # Transport must call decode_public_market_json_exact first.
    return positive_market_decimal(value, label)


def _unique_by_symbol(rows: Sequence[Mapping[str, Any]], name: str) -> dict[str, Mapping[str, Any]]:
    if not isinstance(rows, (tuple, list)):
        raise DataValidationError(f"{name} must be a sequence")
    normalized: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise DataValidationError(f"{name} row must be an object")
        symbol = row.get("symbol")
        if not isinstance(symbol, str) or not symbol or len(symbol) > 80:
            raise DataValidationError(f"{name} has malformed symbol")
        old = normalized.get(symbol)
        if old is not None and old != row:
            raise DataValidationError(f"{name} has conflicting duplicate {symbol}")
        normalized[symbol] = row
    return normalized


def _why_ineligible(
    instrument: Mapping[str, Any], ticker: Mapping[str, Any] | None,
    trusted_bases: frozenset[str],
) -> tuple[str | None, Decimal | None]:
    symbol = instrument["symbol"]
    if _INSTRUMENT_NAME.fullmatch(symbol) is None:
        return "not_linear_usd_perpetual_symbol", None
    # The exact exchange type and ticker tag were observed independently.
    if instrument.get("type") != "flexible_futures":
        return "not_flexible_futures_type", None
    if instrument.get("tradeable") is not True or instrument.get("suspended") is not False:
        return "not_actively_tradeable", None
    if instrument.get("isExpired") is True:
        return "expired", None
    if instrument.get("tradfi") is not False:
        return "tradfi_or_unknown_flag", None
    category = instrument.get("category")
    if category is not None and not isinstance(category, str):
        return "invalid_category", None
    if isinstance(category, str) and category.casefold() in _BLOCKED_CATEGORIES:
        return "non_crypto_category", None

    base = instrument.get("base")
    quote = instrument.get("quote")
    pair = instrument.get("pair")
    if not isinstance(base, str) or not _BASE_NAME.fullmatch(base):
        return "invalid_base_asset", None
    if base not in trusted_bases:
        return "base_not_verified_crypto", None
    if quote != "USD" or pair != f"{base}:USD":
        return "not_comparable_usd_quote", None
    try:
        _decimal_positive(instrument.get("tickSize"), "tickSize")
        _decimal_positive(instrument.get("contractSize"), "contractSize")
    except DataValidationError:
        return "invalid_contract_precision", None
    if ticker is None:
        return "missing_current_ticker", None
    if ticker.get("tag") != "perpetual":
        return "ticker_not_perpetual", None
    if ticker.get("suspended") is not False or ticker.get("postOnly") is True:
        return "ticker_not_actively_tradeable", None
    if ticker.get("pair") is not None and ticker.get("pair") != pair:
        return "ticker_pair_mismatch", None
    try:
        volume = _decimal_positive(ticker.get("volumeQuote"), "volumeQuote")
    except DataValidationError:
        return "invalid_quote_volume", None
    return None, volume


def select_kraken_research_universe(
    *,
    instruments: Sequence[Mapping[str, Any]],
    tickers: Sequence[Mapping[str, Any]],
    observed_at_ms: int,
    verified_crypto_bases: frozenset[str],
    registry_version: str,
    max_symbols: int = 50,
) -> UniverseSnapshot:
    """Select only contemporaneous, USD-quoted, verified crypto futures.

    `verified_crypto_bases` must be a separately established and versioned
    crypto-asset registry: a symbol prefix or `tradfi=false` is never evidence.
    If the registry is unavailable, fail rather than select dubious markets.
    No remote calls, no orders, no historical backfilling of membership.
    """
    if type(observed_at_ms) is not int or observed_at_ms < 0:
        raise ValueError("observed_at_ms must be nonnegative UTC milliseconds")
    if type(max_symbols) is not int or not 1 <= max_symbols <= 50:
        raise ValueError("max_symbols must be between 1 and 50")
    if not isinstance(registry_version, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", registry_version):
        raise ValueError("registry_version must be an explicit immutable label")
    if not isinstance(verified_crypto_bases, frozenset) or not verified_crypto_bases:
        raise ValueError("nonempty verified crypto-asset registry is required")
    if not all(isinstance(base, str) and _BASE_NAME.fullmatch(base) for base in verified_crypto_bases):
        raise ValueError("crypto-asset registry contains malformed or unnormalized bases")

    by_contract = _unique_by_symbol(instruments, "instruments")
    by_ticker = _unique_by_symbol(tickers, "tickers")
    approved: list[tuple[str, Decimal]] = []
    excluded: dict[str, str] = {}
    for symbol, contract in by_contract.items():
        reason, quote_volume = _why_ineligible(contract, by_ticker.get(symbol), verified_crypto_bases)
        if reason is not None:
            excluded[symbol] = reason
        else:
            assert quote_volume is not None
            approved.append((symbol, quote_volume))
    approved.sort(key=lambda member: (-member[1], member[0]))
    chosen = approved[:max_symbols]
    for symbol, _volume in approved[max_symbols:]:
        excluded[symbol] = "below_dynamic_quote_volume_rank"
    # A current ticker cannot reconstruct a past universe, even with a stable
    # registry. The snapshot only reflects this explicit observation.
    return UniverseSnapshot(
        observed_at_ms=observed_at_ms,
        selection_rule_version=f"kraken-verified-crypto-v1:{registry_version}",
        eligible=tuple(
            UniverseMember(symbol=symbol, rank=i + 1, quote_volume=volume)
            for i, (symbol, volume) in enumerate(chosen)
        ),
        excluded=excluded,
        source=RESEARCH_SOURCE,
    )
