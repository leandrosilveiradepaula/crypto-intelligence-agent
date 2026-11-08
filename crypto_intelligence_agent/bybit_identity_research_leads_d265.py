"""D265: retrospective *research leads* for 9 unresolved D264 symbols.

These pages are discovery evidence, not signed point-in-time venue identity,
independent approval, token contract/mint matching, or trading authorization.
D264 remains read-only and BZ is rejected separately in the D259 negative gate.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re
from types import MappingProxyType
from typing import Mapping
from urllib.parse import urlsplit

SCHEMA = "bybit-identity-leads-d265-v1"
ASSEMBLED_ON_UTC_DATE = "2026-11-08"
_SYM = re.compile(r"[A-Z0-9]{1,28}USDT\Z")
_REF = re.compile(r"[a-z0-9]+:[a-z0-9][a-z0-9-]*\Z")
_ALLOWED = frozenset({
    "crypto_token_candidate_unverified",
    "ticker_collision_unresolved",
    "identity_unresolved",
})


@dataclass(frozen=True)
class ResearchLead:
    symbol: str
    category: str
    proposed_refs: tuple[str, ...]
    public_urls: tuple[str, ...]
    reason: str

    def __post_init__(self):
        if (type(self.symbol) is not str or _SYM.fullmatch(self.symbol) is None
                or self.category not in _ALLOWED
                or type(self.proposed_refs) is not tuple
                or len(self.proposed_refs) > 3
                or any(type(x) is not str or _REF.fullmatch(x) is None
                       for x in self.proposed_refs)
                or len(set(self.proposed_refs)) != len(self.proposed_refs)
                or type(self.public_urls) is not tuple
                or len(self.public_urls) > 3
                or len(set(self.public_urls)) != len(self.public_urls)
                or type(self.reason) is not str
                or self.reason not in {
                    "direct_token_hypothesis_needs_venue_proof",
                    "ticker_collision_needs_chain_contract",
                    "identity_no_credible_crosswalk",
                }):
            raise ValueError("invalid D265 research lead")
        if (self.category == "ticker_collision_unresolved") != (
            self.reason == "ticker_collision_needs_chain_contract"
        ):
            raise ValueError("ambiguous lead must fail closed")
        if (self.category == "identity_unresolved") != (
            self.reason == "identity_no_credible_crosswalk"
        ):
            raise ValueError("unknown lead must remain unknown")
        if (self.category == "identity_unresolved" and
                (self.proposed_refs or self.public_urls)):
            raise ValueError("unknown identity cannot receive fake refs")
        if self.category == "crypto_token_candidate_unverified" and (
            len(self.proposed_refs) != 1 or not self.public_urls
        ):
            raise ValueError("positive research hypothesis missing reference")
        if self.category == "ticker_collision_unresolved" and (
            len(self.proposed_refs) < 2 or len(self.public_urls) < 2
        ):
            raise ValueError("collision requires competing references")
        for url in self.public_urls:
            if type(url) is not str or not 12 <= len(url) <= 320:
                raise ValueError("invalid D265 source URL")
            try:
                parsed = urlsplit(url)
                hostname, port = parsed.hostname, parsed.port
            except ValueError:
                raise ValueError("invalid D265 source URL") from None
            if (parsed.scheme != "https" or hostname != "www.coingecko.com"
                    or port is not None or parsed.username is not None
                    or parsed.password is not None or parsed.query or parsed.fragment
                    or not parsed.path.startswith("/en/coins/")
                    or "\\" in url or any(c.isspace() for c in url)):
                raise ValueError("invalid D265 source URL")


_ROWS = (
    ResearchLead("WLFIUSDT", "crypto_token_candidate_unverified",
                 ("coingecko:world-liberty-financial",),
                 ("https://www.coingecko.com/en/coins/world-liberty-financial",),
                 "direct_token_hypothesis_needs_venue_proof"),
    ResearchLead("CAPUSDT", "crypto_token_candidate_unverified",
                 ("coingecko:cap",),
                 ("https://www.coingecko.com/en/coins/cap",),
                 "direct_token_hypothesis_needs_venue_proof"),
    ResearchLead("CYBERUSDT", "crypto_token_candidate_unverified",
                 ("coingecko:cyberconnect",),
                 ("https://www.coingecko.com/en/coins/cyberconnect",),
                 "direct_token_hypothesis_needs_venue_proof"),
    ResearchLead("CLANKERUSDT", "ticker_collision_unresolved",
                 ("coingecko:tokenbot-2", "coingecko:clanker"),
                 ("https://www.coingecko.com/en/coins/tokenbot-2",
                  "https://www.coingecko.com/en/coins/clanker"),
                 "ticker_collision_needs_chain_contract"),
    ResearchLead("XPLUSDT", "crypto_token_candidate_unverified",
                 ("coingecko:plasma",),
                 ("https://www.coingecko.com/en/coins/plasma",),
                 "direct_token_hypothesis_needs_venue_proof"),
    ResearchLead("FARTCOINUSDT", "crypto_token_candidate_unverified",
                 ("coingecko:fartcoin",),
                 ("https://www.coingecko.com/en/coins/fartcoin",),
                 "direct_token_hypothesis_needs_venue_proof"),
    ResearchLead("DGAIUSDT", "identity_unresolved", (), (),
                 "identity_no_credible_crosswalk"),
    ResearchLead("PONSUSDT", "crypto_token_candidate_unverified",
                 ("coingecko:pons",),
                 ("https://www.coingecko.com/en/coins/pons",),
                 "direct_token_hypothesis_needs_venue_proof"),
    ResearchLead("ASTERUSDT", "crypto_token_candidate_unverified",
                 ("coingecko:aster-2",),
                 ("https://www.coingecko.com/en/coins/aster-2",),
                 "direct_token_hypothesis_needs_venue_proof"),
)

if len({row.symbol for row in _ROWS}) != len(_ROWS):
    raise ValueError("duplicated D265 lead")

RESEARCH_LEADS: Mapping[str, ResearchLead] = MappingProxyType({
    row.symbol: row for row in _ROWS
})


def lead_details(symbol: str) -> dict | None:
    if type(symbol) is not str or _SYM.fullmatch(symbol) is None:
        raise ValueError("invalid D265 symbol")
    row = RESEARCH_LEADS.get(symbol)
    if row is None:
        return None
    return {
        "research_category": row.category,
        "relation_hypothesis_only": row.reason,
        "proposed_asset_refs_unverified": list(row.proposed_refs),
        "candidate_research_urls": list(row.public_urls),
        "identity_approval": False,
        "evidence_pit_authenticated": False,
        "provider_contract_id_authenticated": False,
    }


def lead_digest() -> str:
    raw = [
        (r.symbol, r.category, r.proposed_refs, r.public_urls, r.reason)
        for r in sorted(_ROWS, key=lambda x: x.symbol)
    ]
    return sha256(json.dumps(raw, ensure_ascii=True,
                             separators=(",", ":")).encode("ascii")).hexdigest()
