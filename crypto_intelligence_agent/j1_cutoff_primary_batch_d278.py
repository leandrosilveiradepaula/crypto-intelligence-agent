"""D278: fixed first-party evidence triage for nine Top50 cutoff rivals.

Documentary research as of 2026-11-11, never historical PIT authentication.
A venue perpetual notice and another venue's token/contract notice are NOT
proof of the same venue's underlying mint or of crypto-only eligibility.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re
from typing import Any
from urllib.parse import urlsplit

from .bybit_identity_crosswalk_research import research_category
from .bybit_primary_identity_research import PRIMARY_LEADS

_SYMBOL = re.compile(r"[A-Z0-9]{1,28}USDT\Z")
_DATE = re.compile(r"20[0-9]{2}-(0[1-9]|1[0-2])-([0-2][0-9]|3[01])\Z")
_SAFE = re.compile(r"[A-Za-z0-9 ()._-]{2,80}\Z")
_SCHEMA = "j1-d278-cutoff-primary-dossier-v1"
_REVIEWED = "2026-11-11"
_HOSTS = frozenset({
    "announcements.bybit.com", "www.binance.com",
    "www.bybit.com",
})
_ROLES = frozenset({
    "venue_perpetual_listing",
    "independent_perpetual_underlying",
    "venue_spot_token_migration",
    "independent_token_reference",
})
_STATES = frozenset({
    "cross_venue_perpetual_name_research",
    "single_venue_perpetual_only",
    "external_underlying_no_venue_perpetual",
    "spot_migration_not_perpetual",
    "existing_primary_collided_research",
    "primary_evidence_missing",
})


@dataclass(frozen=True)
class PublicSource:
    role: str
    source_url: str
    published_on: str

    def __post_init__(self):
        if type(self.role) is not str or self.role not in _ROLES:
            raise ValueError("invalid evidence role")
        if type(self.source_url) is not str or not 12 <= len(self.source_url) <= 350:
            raise ValueError("invalid evidence link")
        try:
            p = urlsplit(self.source_url)
            hostname, port = p.hostname, p.port
        except ValueError:
            raise ValueError("invalid evidence URL") from None
        if (p.scheme != "https" or hostname not in _HOSTS or port is not None
                or p.username is not None or p.password is not None
                or p.query or p.fragment or "\\" in self.source_url
                or any(c.isspace() for c in self.source_url)
                or not p.path.startswith((
                    "/en/article/", "/fr/support/announcement/detail/",
                    "/en/support/announcement/detail/",
                ))):
            raise ValueError("invalid first party evidence URL")
        if (self.role in ("venue_perpetual_listing", "venue_spot_token_migration")
                and hostname != "announcements.bybit.com"):
            raise ValueError("venue evidence must originate from Bybit")
        if self.role.startswith("independent_") and hostname != "www.binance.com":
            raise ValueError("independent evidence must originate from Binance")
        if type(self.published_on) is not str or not _DATE.fullmatch(self.published_on):
            raise ValueError("invalid first party publication date")
        from datetime import date
        try:
            if date.fromisoformat(self.published_on) > date.fromisoformat(_REVIEWED):
                raise ValueError("source after research review")
        except ValueError:
            raise ValueError("invalid source chronology") from None


@dataclass(frozen=True)
class RivalResearch:
    symbol: str
    proposed_underlying: str | None
    research_state: str
    source_notes: tuple[PublicSource, ...]

    def __post_init__(self):
        if type(self.symbol) is not str or not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("invalid dossier symbol")
        if self.proposed_underlying is not None and (
            type(self.proposed_underlying) is not str
            or not _SAFE.fullmatch(self.proposed_underlying)
        ):
            raise ValueError("invalid proposed name")
        if self.research_state not in _STATES:
            raise ValueError("invalid research state")
        if type(self.source_notes) is not tuple or any(
            type(s) is not PublicSource for s in self.source_notes
        ) or len(self.source_notes) > 4:
            raise ValueError("invalid source notes")
        roles = [s.role for s in self.source_notes]
        if len(roles) != len(set(roles)):
            raise ValueError("duplicate source role")
        states = {
            "cross_venue_perpetual_name_research": frozenset({
                "venue_perpetual_listing", "independent_perpetual_underlying"}),
            "single_venue_perpetual_only": frozenset({"venue_perpetual_listing"}),
            "external_underlying_no_venue_perpetual": frozenset({
                "independent_perpetual_underlying"}),
            "spot_migration_not_perpetual": frozenset({"venue_spot_token_migration"}),
            "existing_primary_collided_research": frozenset(),
            "primary_evidence_missing": frozenset(),
        }
        if frozenset(roles) != states[self.research_state]:
            raise ValueError("source roles cannot imply a stronger classification")
        if self.research_state == "existing_primary_collided_research":
            if self.symbol not in PRIMARY_LEADS:
                raise ValueError("existing lead missing")
        if (self.research_state == "primary_evidence_missing"
                and self.proposed_underlying is not None):
            raise ValueError("unverified identity may not be inferred by ticker")
        if self.research_state == "cross_venue_perpetual_name_research" and (
            self.proposed_underlying is None
        ):
            raise ValueError("two sources must name the proposed asset")


_ROWS = (
    RivalResearch("LYNUSDT", "Everlyn AI",
                  "cross_venue_perpetual_name_research", (
        PublicSource("venue_perpetual_listing",
                     "https://announcements.bybit.com/en/article/"
                     "new-listing-lynusdt-perpetual-contract-with-up-to-50x-leverage-blteec52ce3c263c923/",
                     "2025-10-06"),
        PublicSource("independent_perpetual_underlying",
                     "https://www.binance.com/fr/support/announcement/detail/"
                     "f4077219b5a441b5bf39413c603c5a7b", "2025-10-06"),
    )),
    RivalResearch("DOTUSDT", None, "primary_evidence_missing", ()),
    RivalResearch("ICNTUSDT", "Impossible Cloud Network",
                  "external_underlying_no_venue_perpetual", (
        PublicSource("independent_perpetual_underlying",
                     "https://www.binance.com/en/support/announcement/detail/"
                     "baaa3a53a66840d087e845fb44872dc8", "2025-07-03"),
    )),
    RivalResearch("ELSAUSDT", "HeyElsa",
                  "cross_venue_perpetual_name_research", (
        PublicSource("venue_perpetual_listing",
                     "https://announcements.bybit.com/en/article/"
                     "new-listing-elsausdt-perpetual-contract-in-innovation-zone-with-up-to-20x-leverage-blt41fbabdeb9208666/",
                     "2026-01-22"),
        PublicSource("independent_perpetual_underlying",
                     "https://www.binance.com/en/support/announcement/detail/"
                     "4afa6aa807234762b141920847b4fe0b", "2026-01-22"),
    )),
    RivalResearch("AEROUSDT", "Aerodrome and Aero",
                  "spot_migration_not_perpetual", (
        PublicSource("venue_spot_token_migration",
                     "https://announcements.bybit.com/en/article/"
                     "bybit-will-support-the-aerodrome-aero-token-migration--art01f028b44dd4/",
                     "2026-10-26"),
    )),
    RivalResearch("LITUSDT", "Lighter Protocol",
                  "cross_venue_perpetual_name_research", (
        PublicSource("venue_perpetual_listing",
                     "https://announcements.bybit.com/en/article/"
                     "new-listing-litusdt-perpetual-contract-with-up-to-25x-leverage-blt0bf35ec2cd5047d8/",
                     "2025-12-30"),
        PublicSource("independent_perpetual_underlying",
                     "https://www.binance.com/en/support/announcement/detail/"
                     "6a33be00231c4539b3a4a625538e4d1e", "2025-12-23"),
    )),
    RivalResearch("ARIAUSDT", None, "primary_evidence_missing", ()),
    RivalResearch("BIRBUSDT", None, "primary_evidence_missing", ()),
    RivalResearch("CLANKERUSDT", "tokenbot (CLANKER)",
                  "existing_primary_collided_research", ()),
)
if len({r.symbol for r in _ROWS}) != len(_ROWS):
    raise ValueError("duplicate cutoff symbol")
RIVALS = {r.symbol: r for r in _ROWS}


def _digest(data: object) -> str:
    raw = json.dumps(data, separators=(",", ":"), sort_keys=True,
                     ensure_ascii=True).encode("ascii")
    return sha256(raw).hexdigest()


def batch_research(
    *, raw_baseline_frontier: tuple[str, ...],
    possible_replacements: tuple[str, ...],
    include_private_symbols: bool = False,
) -> dict[str, Any]:
    """Label known symbols in the frozen candidate set; never promote to Top50.

    The caller's frontier is validated/ranked outside this function. No input
    data is assumed to be a genuine Bybit response or PIT approval here.
    """
    for name, rows in (("baseline", raw_baseline_frontier),
                       ("replacements", possible_replacements)):
        if (type(rows) is not tuple or len(rows) > 5000
                or len(set(rows)) != len(rows)
                or any(type(s) is not str or not _SYMBOL.fullmatch(s) for s in rows)):
            raise ValueError(name + "_invalid")
    if len(raw_baseline_frontier) != 50 or type(include_private_symbols) is not bool:
        raise ValueError("invalid cutoff batch scope")
    if set(raw_baseline_frontier) & set(possible_replacements):
        raise ValueError("replacement already in baseline")
    selected = tuple(s for s in (*raw_baseline_frontier, *possible_replacements)
                     if s in RIVALS)
    counts: dict[str, int] = {}
    rows: list[dict[str, Any]] = []
    for symbol in selected:
        r = RIVALS[symbol]
        counts[r.research_state] = counts.get(r.research_state, 0) + 1
        if include_private_symbols:
            rows.append({
                "symbol": symbol,
                "source_class": r.research_state,
                "historical_category_unchanged": research_category(symbol, False),
                "proposed_underlying_unverified": r.proposed_underlying,
                "public_primary_urls": [s.source_url for s in r.source_notes],
                "independently_authenticated_venue_mint": False,
                "identity_pit_authenticated": False,
                "eligible_top50": False,
            })
    result: dict[str, Any] = {
        "schema": _SCHEMA,
        "status": "nine_cutoff_symbols_documentary_research_only",
        "symbol_research_catalog_size": len(RIVALS),
        "selected_in_observed_frontier_and_replacements": len(selected),
        "selected_source_state_counts": dict(sorted(counts.items())),
        "research_catalog_digest": _digest([
            [r.symbol, r.proposed_underlying, r.research_state,
             [(s.role, s.source_url, s.published_on) for s in r.source_notes]]
            for r in sorted(_ROWS, key=lambda v: v.symbol)
        ]),
        "research_reviewed_on": _REVIEWED,
        "identity_pit_authenticated": False,
        "eligible_crypto_approved": False,
        "marketwide_top50_verified": False,
        "trading_enabled": False,
        "orders_sent": False,
        "network_requests": 0,
        "database_modified": False,
    }
    if include_private_symbols:
        result["private_symbol_research_rows_only"] = rows
    return result
