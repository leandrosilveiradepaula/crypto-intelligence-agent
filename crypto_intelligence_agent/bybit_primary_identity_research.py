"""J1 D273: primary-source venue-to-crypto identity leads, research-only.

The sources below are published first-party announcements, checked by a
researcher AFTER the frozen 06-Nov market observation. Their publication date
is not the researcher's independent observation time, proof of historical
availability in the collector, or an authenticated identity-allowlist.
Never import these leads as reviewed-positive symbols in the Top50 gate.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from hashlib import sha256
import json
import re
from types import MappingProxyType
from typing import Mapping
from urllib.parse import urlsplit

from .bybit_tradfi_negative_evidence import NEGATIVE_EVIDENCE

SCHEMA = "j1-bybit-primary-identity-d273-research-v1"
_SYMBOL = re.compile(r"[A-Z0-9]{1,28}USDT\Z")
_ASSET_ID = re.compile(r"[a-z0-9]+:[a-z0-9][a-z0-9-]*\Z")
_CHAIN_CONTRACT = re.compile(r"[a-z0-9][a-z0-9-]{1,24}:0x[0-9a-fA-F]{40}\Z")
_SAFE_LABEL = re.compile(r"[A-Za-z0-9 ._-]{3,72}\Z")


def _public_primary_url(url: str, hostname: str, path_prefix: str) -> None:
    if type(url) is not str or len(url) > 320:
        raise ValueError("invalid primary URL")
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError:
        raise ValueError("invalid primary URL") from None
    if (parsed.scheme != "https" or parsed.hostname != hostname
            or not parsed.path.startswith(path_prefix)
            or not parsed.path[len(path_prefix):]
            or parsed.query or parsed.fragment or port is not None
            or parsed.username is not None or parsed.password is not None
            or "\\" in url or any(c.isspace() for c in url)):
        raise ValueError("invalid primary URL")


@dataclass(frozen=True)
class PrimaryIdentityLead:
    venue_symbol: str
    venue_underlying: str
    canonical_asset_ref: str
    network_contract_id: str
    venue_announcement_url: str
    venue_published_on: str
    independent_announcement_url: str
    independent_published_on: str
    research_reviewed_on: str

    def __post_init__(self) -> None:
        if (type(self.venue_symbol) is not str
                or _SYMBOL.fullmatch(self.venue_symbol) is None
                or self.venue_symbol in NEGATIVE_EVIDENCE
                or type(self.venue_underlying) is not str
                or _SAFE_LABEL.fullmatch(self.venue_underlying) is None
                or type(self.canonical_asset_ref) is not str
                or _ASSET_ID.fullmatch(self.canonical_asset_ref) is None
                or type(self.network_contract_id) is not str
                or _CHAIN_CONTRACT.fullmatch(self.network_contract_id) is None):
            raise ValueError("invalid primary identity lead")
        _public_primary_url(self.venue_announcement_url,
                            "announcements.bybit.com", "/en/article/")
        _public_primary_url(self.independent_announcement_url,
                            "www.gate.com", "/pt-br/announcements/article/")
        try:
            venue = date.fromisoformat(self.venue_published_on)
            other = date.fromisoformat(self.independent_published_on)
            reviewed = date.fromisoformat(self.research_reviewed_on)
        except (TypeError, ValueError):
            raise ValueError("invalid identity evidence dates") from None
        if (any(type(x) is not str or len(x) != 10 for x in (
                self.venue_published_on, self.independent_published_on,
                self.research_reviewed_on))
                or min(venue, other, reviewed) < date(2020, 1, 1)
                or max(venue, other) > reviewed):
            raise ValueError("primary evidence publication/review chronology invalid")


# Official Bybit perpetual listing identifies its underlying as DGrid AI.
# Independently, the Gate token listing identifies DGrid AI/DGAI and publishes
# its BNB Chain token address. Both pages were checked on 11-Nov-2026 UTC.
# This deliberately does NOT predate review into the 06-Nov frozen snapshot.
_ROWS = (
    PrimaryIdentityLead(
        venue_symbol="DGAIUSDT",
        venue_underlying="DGrid AI",
        canonical_asset_ref="coingecko:dgrid-ai",
        network_contract_id="bsc:0x10D4183389e99233db3cc981c43443Ebd28Ebd5e",
        venue_announcement_url=(
            "https://announcements.bybit.com/en/article/"
            "new-listing-dgaiusdt-perpetual-contract-in-innovation-zone-with-up-to-20x-leverage--art151aff198a7e/"
        ),
        venue_published_on="2026-09-04",
        independent_announcement_url=(
            "https://www.gate.com/pt-br/announcements/article/101292"
        ),
        independent_published_on="2026-08-23",
        research_reviewed_on="2026-11-11",
    ),
)

if len({row.venue_symbol for row in _ROWS}) != len(_ROWS):
    raise ValueError("duplicate primary venue symbol")

PRIMARY_LEADS: Mapping[str, PrimaryIdentityLead] = MappingProxyType({
    item.venue_symbol: item for item in _ROWS
})


def lead_digest() -> str:
    """Deterministic published-record checksum; never source authentication."""
    fields = tuple(PrimaryIdentityLead.__dataclass_fields__)
    rows = [
        [getattr(lead, field) for field in fields]
        for lead in sorted(_ROWS, key=lambda row: row.venue_symbol)
    ]
    raw = json.dumps(rows, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    return sha256(raw).hexdigest()


def primary_research_details(symbol: str, *, market_window_end_ms: int) -> dict | None:
    """Return only research details; even 2 sources never approve Top50/trading.

    The dates embedded in sources are publication dates. The first documented
    independent research review occurred 11-Nov, so this record cannot be
    treated as PIT identity at the historical 06-Nov market window.
    """
    if (type(symbol) is not str or _SYMBOL.fullmatch(symbol) is None
            or type(market_window_end_ms) is not int
            or not 1_600_000_000_000 <= market_window_end_ms <= 4_102_444_800_000):
        raise ValueError("invalid research lookup")
    row = PRIMARY_LEADS.get(symbol)
    if row is None:
        return None
    market_date = datetime.fromtimestamp(
        market_window_end_ms / 1000, tz=timezone.utc
    ).date()
    reviewed = date.fromisoformat(row.research_reviewed_on)
    publication_both_precede_window = (
        date.fromisoformat(row.venue_published_on) < market_date
        and date.fromisoformat(row.independent_published_on) < market_date
    )
    # A review date alone has day granularity: require a later UTC DAY.
    review_precedes_window = reviewed < market_date
    return {
        "schema_version": SCHEMA,
        "venue_symbol": symbol,
        "venue_underlying_research": row.venue_underlying,
        "candidate_canonical_asset_ref": row.canonical_asset_ref,
        "network_contract_research": row.network_contract_id,
        "venue_primary_url": row.venue_announcement_url,
        "independent_token_primary_url": row.independent_announcement_url,
        "venue_source_published_on": row.venue_published_on,
        "independent_source_published_on": row.independent_published_on,
        "research_reviewed_on": row.research_reviewed_on,
        "primary_publisher_roots_count": 2,
        "primary_sources_published_before_market_window": publication_both_precede_window,
        "research_reviewed_before_market_window": review_precedes_window,
        "status": (
            "documented_two_primary_sources_research_only"
            if publication_both_precede_window and review_precedes_window
            else "historical_pit_not_established"
        ),
        "identity_approved": False,
        "provider_identity_authenticated": False,
        "identity_pit_authenticated": False,
        "eligible_top50": False,
        "marketwide_top50_verified": False,
        "trading_enabled": False,
        "orders_sent": False,
        "network_requests": 0,
        "database_modified": False,
    }
