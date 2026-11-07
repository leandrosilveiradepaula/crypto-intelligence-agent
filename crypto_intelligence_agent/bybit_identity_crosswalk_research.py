"""D261: *candidate-only* Bybit symbol/asset-class crosswalk for J1 research.

Public URLs and possible canonical IDs here are research leads, not authenticated
venue identity, independent source approval, PIT evidence, or trade eligibility.
In particular do not strip numeric prefixes or infer a coin from its ticker.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from hashlib import sha256
import json
import re
from types import MappingProxyType
from typing import Mapping
from urllib.parse import urlsplit

from .bybit_tradfi_negative_evidence import NEGATIVE_EVIDENCE

VERSION = "bybit-identity-candidate-d261-v1"
RESEARCH_ASSEMBLED_ON_UTC_DATE = "2026-11-07"
MAX_FRONTIER = 50
MAX_CENSUS_MEMBERS = 5000
_SYMBOL = re.compile(r"[A-Z0-9]{2,32}USDT\Z")
_CANDIDATE = re.compile(r"[a-z0-9]+:[a-z0-9][a-z0-9-]*\Z")
_CLASSES = frozenset({
    "crypto_token_candidate_unverified",
    "ticker_collision_unresolved",
    "tokenized_gold_policy_gate",
})
_RELATIONS = frozenset({
    "direct_ticker_hypothesis",
    "unit_1000_requires_venue_proof",
    "venue_alias_requires_proof",
    "ticker_collision_requires_contract_id",
    "tokenized_commodity_not_tradfi_xau",
})


@dataclass(frozen=True)
class CandidateCrosswalk:
    venue_symbol: str
    research_class: str
    symbol_relation: str
    proposed_asset_refs: tuple[str, ...]
    source_urls: tuple[str, ...]

    def __post_init__(self) -> None:
        if (type(self.venue_symbol) is not str
                or _SYMBOL.fullmatch(self.venue_symbol) is None
                or self.venue_symbol in NEGATIVE_EVIDENCE
                or self.research_class not in _CLASSES
                or self.symbol_relation not in _RELATIONS
                or type(self.proposed_asset_refs) is not tuple
                or not 1 <= len(self.proposed_asset_refs) <= 4
                or len(set(self.proposed_asset_refs)) != len(self.proposed_asset_refs)
                or any(type(x) is not str or _CANDIDATE.fullmatch(x) is None
                       for x in self.proposed_asset_refs)
                or type(self.source_urls) is not tuple
                or not 1 <= len(self.source_urls) <= 4
                or len(set(self.source_urls)) != len(self.source_urls)):
            raise ValueError("unverified candidate record invalid")
        if (self.research_class == "ticker_collision_unresolved") != (
            len(self.proposed_asset_refs) >= 2
        ):
            raise ValueError("ambiguous ticker needs multiple candidates")
        if (self.research_class == "ticker_collision_unresolved") != (
            self.symbol_relation == "ticker_collision_requires_contract_id"
        ):
            raise ValueError("ticker collision must fail closed")
        if (self.research_class == "tokenized_gold_policy_gate") != (
            self.symbol_relation == "tokenized_commodity_not_tradfi_xau"
        ):
            raise ValueError("tokenized gold requires explicit product gate")
        for url in self.source_urls:
            if type(url) is not str or not 12 <= len(url) <= 320:
                raise ValueError("candidate reference URL invalid")
            try:
                p = urlsplit(url)
                host = (p.hostname or "").lower()
                port = p.port
            except ValueError:
                raise ValueError("candidate reference URL invalid") from None
            if (p.scheme != "https" or not host or "." not in host
                    or p.username is not None or p.password is not None
                    or port is not None or p.query or p.fragment
                    or "@" in p.netloc or "\\" in url
                    or any(c.isspace() for c in url)
                    or host in {"localhost", "127.0.0.1"}):
                raise ValueError("candidate reference URL invalid")


def _row(symbol: str, kind: str, relation: str,
         ids: tuple[str, ...], links: tuple[str, ...]) -> CandidateCrosswalk:
    return CandidateCrosswalk(symbol, kind, relation, ids, links)


# Research references: dated at compilation only; none were observed/authenticated
# at the November 6 13:00Z candle decision instant. No signed review is present.
_ROWS = (
    _row("1000PEPEUSDT", "crypto_token_candidate_unverified",
         "unit_1000_requires_venue_proof", ("coingecko:pepe",),
         ("https://www.coingecko.com/en/coins/pepe",)),
    _row("TRUMPUSDT", "crypto_token_candidate_unverified",
         "direct_ticker_hypothesis", ("coingecko:official-trump",),
         ("https://www.coingecko.com/en/coins/official-trump",)),
    _row("AKEUSDT", "crypto_token_candidate_unverified",
         "direct_ticker_hypothesis", ("coingecko:akedo",),
         ("https://www.coingecko.com/en/coins/akedo",)),
    _row("JCTUSDT", "crypto_token_candidate_unverified",
         "direct_ticker_hypothesis", ("coingecko:janction",),
         ("https://www.coingecko.com/en/coins/janction",
          "https://announcements.bybit.com/en/article/change-tick-size-for-usdt-perpetual-contract-aug-11-2026--art0ae2431459d9/")),
    _row("LITUSDT", "ticker_collision_unresolved",
         "ticker_collision_requires_contract_id",
         ("coingecko:lighter", "coingecko:litentry"),
         ("https://www.coingecko.com/en/coins/lighter",
          "https://www.coingecko.com/en/coins/litentry")),
    _row("XAUTUSDT", "tokenized_gold_policy_gate",
         "tokenized_commodity_not_tradfi_xau", ("tether:xaut",),
         ("https://www.bybit.com/en/learn/bybit-guide/bybit-gold-derivatives-trading",
          "https://www.coingecko.com/en/coins/tether-gold")),
    _row("ARIAUSDT", "ticker_collision_unresolved",
         "ticker_collision_requires_contract_id",
         ("coingecko:aria-ai", "coingecko:aria"),
         ("https://www.coingecko.com/en/coins/aria-ai",
          "https://www.coingecko.com/en/coins/aria")),
    _row("BIRBUSDT", "ticker_collision_unresolved",
         "ticker_collision_requires_contract_id",
         ("coingecko:moonbirds", "coingecko:birb"),
         ("https://www.coingecko.com/en/coins/moonbirds",
          "https://www.coingecko.com/en/coins/birb")),
    _row("UAIUSDT", "crypto_token_candidate_unverified",
         "direct_ticker_hypothesis", ("coingecko:unifai-network",),
         ("https://www.coingecko.com/en/coins/unifai-network",)),
    _row("PUMPFUNUSDT", "crypto_token_candidate_unverified",
         "venue_alias_requires_proof", ("coingecko:pump-fun",),
         ("https://www.coingecko.com/en/coins/pump-fun",)),
)

if len({item.venue_symbol for item in _ROWS}) != len(_ROWS):
    raise ValueError("duplicated research-only venue symbol")

CANDIDATE_CROSSWALK: Mapping[str, CandidateCrosswalk] = MappingProxyType({
    item.venue_symbol: item for item in _ROWS
})


def candidate_crosswalk_digest() -> str:
    """Content digest, not identity proof or a venue-authenticated signature."""
    payload = [
        (r.venue_symbol, r.research_class, r.symbol_relation,
         r.proposed_asset_refs, r.source_urls)
        for r in sorted(_ROWS, key=lambda item: item.venue_symbol)
    ]
    return sha256(json.dumps(payload, ensure_ascii=True,
                             separators=(",", ":")).encode("ascii")).hexdigest()


def research_frontier(ordered_closed_symbols: tuple[str, ...], *,
                      limit: int = MAX_FRONTIER) -> tuple[str, ...]:
    """Omit *documented negative* contracts for research ONLY, not trading.

    Returning 50 candidates cannot prove a crypto-only universe: the negative
    list is incomplete, evidence is retrospective, identities remain pending.
    """
    if (type(ordered_closed_symbols) is not tuple
            or not 1 <= len(ordered_closed_symbols) <= MAX_CENSUS_MEMBERS
            or type(limit) is not int or not 1 <= limit <= MAX_FRONTIER
            or len(set(ordered_closed_symbols)) != len(ordered_closed_symbols)
            or any(type(s) is not str or _SYMBOL.fullmatch(s) is None
                   for s in ordered_closed_symbols)):
        raise ValueError("closed research frontier input invalid")
    return tuple(
        symbol for symbol in ordered_closed_symbols
        if symbol not in NEGATIVE_EVIDENCE
    )[:limit]


def research_category(symbol: str, archived_base_present: bool) -> str:
    """Exact-symbol negative gate first; nothing here authorizes crypto."""
    if (type(symbol) is not str or _SYMBOL.fullmatch(symbol) is None
            or type(archived_base_present) is not bool):
        raise ValueError("research identity category input invalid")
    if symbol in NEGATIVE_EVIDENCE:
        return "bybit_tradfi_documented_retrospective"
    if archived_base_present:
        return "archived_crypto_reference_only"
    record = CANDIDATE_CROSSWALK.get(symbol)
    return record.research_class if record else "identity_unresolved"


def research_details(symbol: str) -> dict | None:
    """Return opt-in public hints; no prices, private data or verified status."""
    if type(symbol) is not str or _SYMBOL.fullmatch(symbol) is None:
        raise ValueError("research details require a public Bybit symbol")
    item = CANDIDATE_CROSSWALK.get(symbol)
    if item is None:
        return None
    return {
        "relation_hypothesis_only": item.symbol_relation,
        "proposed_asset_refs_unverified": list(item.proposed_asset_refs),
        "candidate_research_urls": list(item.source_urls),
        "identity_approval": False,
        "evidence_pit_authenticated": False,
    }


def research_provenance() -> dict[str, object]:
    # A compilation day is NOT the timestamp at which those sources were
    # independently observed, or proof they were available at an older time.
    date.fromisoformat(RESEARCH_ASSEMBLED_ON_UTC_DATE)
    return {
        "candidate_crosswalk_version": VERSION,
        "candidate_crosswalk_digest_sha256": candidate_crosswalk_digest(),
        "candidate_research_assembled_on_utc_date": RESEARCH_ASSEMBLED_ON_UTC_DATE,
        "candidate_venue_crosswalk_verified": False,
        "candidate_identity_independent_review_verified": False,
        "candidate_research_pit_authenticated": False,
        "candidate_catalog_complete_for_market": False,
    }
