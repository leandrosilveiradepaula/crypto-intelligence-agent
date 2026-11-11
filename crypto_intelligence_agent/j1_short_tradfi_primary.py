"""J1/D277: fixed primary-venue evidence for the three short TradFi contracts.

Source publications checked on 2026-11-11, AFTER the frozen 2026-11-06
market window. A dated announcement is retrospective documentary evidence,
not an authenticated point-in-time capture. No network or trading.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from hashlib import sha256
import json
import re
from typing import Any
from urllib.parse import urlsplit

_SYMBOL = re.compile(r"[A-Z0-9]{1,28}USDT\Z")
_SHA = re.compile(r"[a-z0-9-]{6,120}\Z")
_DAY = "2026-11-06"
_LAUNCH_MS = 1793962800000  # 2026-11-06 11:00:00 UTC
_RESEARCH_REVIEWED = "2026-11-11"
_SCHEMA = "j1-d277-short-tradfi-primary-v1"
_CATALOG = (
    ("DUOLUSDT", "Duolingo", "new-listing-listing-of-duolusdt-on-bybit-tradfi-perpetual-on-nov-6-2026-11-00am-utc--artde830783f6d5"),
    ("FISVUSDT", "Fiserv", "new-listing-listing-of-fisvusdt-on-bybit-tradfi-perpetual-on-nov-6-2026-11-00am-utc--art5e5431016814"),
    ("FNUSDT", "Fabrinet", "new-listing-listing-of-fnusdt-on-bybit-tradfi-perpetual-on-nov-6-2026-11-00am-utc--artff454659fb47"),
)


@dataclass(frozen=True)
class ShortTradfiPrimary:
    venue_symbol: str
    underlying_equity: str
    announcement_url: str
    published_date: str
    announced_launch_ms: int
    reviewed_date: str

    def __post_init__(self) -> None:
        if (type(self.venue_symbol) is not str or not _SYMBOL.fullmatch(self.venue_symbol)
                or type(self.underlying_equity) is not str
                or not 2 <= len(self.underlying_equity) <= 60
                or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz " for c in self.underlying_equity)
                or type(self.announcement_url) is not str
                or len(self.announcement_url) > 300):
            raise ValueError("short_tradfi_primary_invalid")
        url = urlsplit(self.announcement_url)
        if (url.scheme != "https" or url.netloc != "announcements.bybit.com"
                or not url.path.startswith("/en/article/")
                or not _SHA.fullmatch(url.path.removeprefix("/en/article/"))
                or url.query or url.fragment or url.username or url.password):
            raise ValueError("short_tradfi_primary_url_invalid")
        try:
            published = date.fromisoformat(self.published_date)
            reviewed = date.fromisoformat(self.reviewed_date)
        except (ValueError, TypeError):
            raise ValueError("short_tradfi_date_invalid") from None
        if (type(self.published_date) is not str or len(self.published_date) != 10
                or type(self.reviewed_date) is not str or len(self.reviewed_date) != 10
                or type(self.announced_launch_ms) is not int
                or not 1_600_000_000_000 <= self.announced_launch_ms <= 4_102_444_800_000
                or published > reviewed):
            raise ValueError("short_tradfi_chronology_invalid")


SOURCES = {sym: ShortTradfiPrimary(
    venue_symbol=sym,
    underlying_equity=underlying,
    announcement_url="https://announcements.bybit.com/en/article/" + slug + "/",
    published_date=_DAY,
    announced_launch_ms=_LAUNCH_MS,
    reviewed_date=_RESEARCH_REVIEWED,
) for sym, underlying, slug in _CATALOG}


def audit_short_tradfi(
    *, shorts: tuple[tuple[str, int, int | None], ...],
    historical_window_end_ms: int,
    contemporary_negative_symbols: frozenset[str],
    include_private_symbols: bool = False,
) -> dict[str, Any]:
    """Offline retrospective evidence, never independent PIT certification.

    shorts are already integrity-checked by D256 _replay and must come from
    the immutable DB; negative indicators are later D264 provider claims.
    Non-documented shorts remain unresolved; they never receive a zero rank.
    """
    if (type(shorts) is not tuple or len(shorts) > 5000
            or len({s[0] for s in shorts if type(s) is tuple and s}) != len(shorts)
            or type(contemporary_negative_symbols) is not frozenset
            or any(type(s) is not str or not _SYMBOL.fullmatch(s)
                   for s in contemporary_negative_symbols)
            or type(historical_window_end_ms) is not int
            or not 1_600_000_000_000 <= historical_window_end_ms <= 4_102_444_800_000
            or historical_window_end_ms % 3_600_000
            or type(include_private_symbols) is not bool):
        raise ValueError("short_tradfi_input_invalid")
    for row in shorts:
        if (type(row) is not tuple or len(row) != 3
                or type(row[0]) is not str or not _SYMBOL.fullmatch(row[0])
                or type(row[1]) is not int or not 0 <= row[1] < 24
                or (row[2] is not None and
                    (type(row[2]) is not int or not 1_600_000_000_000 <= row[2] <= historical_window_end_ms))):
            raise ValueError("short_tradfi_row_invalid")

    documented = []
    unknown = []
    matched_negative = 0
    for symbol, count, launch_hint in sorted(shorts):
        record = SOURCES.get(symbol)
        if record is not None and record.announced_launch_ms <= historical_window_end_ms:
            documented.append(symbol)
            if symbol in contemporary_negative_symbols:
                matched_negative += 1
        else:
            unknown.append(symbol)

    def digest(values: list[str]) -> str:
        raw = json.dumps(values, separators=(",", ":"), ensure_ascii=True).encode("ascii")
        return sha256(raw).hexdigest()

    result: dict[str, Any] = {
        "schema_version": _SCHEMA,
        "status": "retrospective_tradfi_short_documentary_research_only",
        "short_census_contracts": len(shorts),
        "short_observed_candles": sum(row[1] for row in shorts),
        "shorts_with_venue_primary_tradfi_documentation": len(documented),
        "documented_shorts_matching_later_negative_indicator": matched_negative,
        "undocumented_shorts_still_possible_crypto_rivals": len(unknown),
        "documented_short_symbols_sha256": digest(documented),
        "undocumented_short_symbols_sha256": digest(unknown),
        "primary_publisher_count": 1 if documented else 0,
        "primary_documentation_reviewed_after_frozen_window": True,
        "historical_provider_identity_pit_authenticated": False,
        "all_short_rivals_independently_disqualified_pit": False,
        "marketwide_top50_verified": False,
        "trading_enabled": False,
        "orders_sent": False,
        "network_requests": 0,
        "database_modified": False,
    }
    if include_private_symbols:
        result["documented_short_contracts_only"] = [
            {"symbol": s, "underlying_equity": SOURCES[s].underlying_equity,
             "official_bybit_announcement_url": SOURCES[s].announcement_url,
             "announced_launch_ms": SOURCES[s].announced_launch_ms,
             "historical_count": next(n for symbol, n, _ in shorts if symbol == s),
             "matches_contemporary_negative_indicator": s in contemporary_negative_symbols}
            for s in documented
        ]
        result["undocumented_short_symbols_only"] = unknown
    return result
