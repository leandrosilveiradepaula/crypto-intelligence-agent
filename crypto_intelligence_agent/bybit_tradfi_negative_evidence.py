"""D259: dated public Bybit evidence for negative TradFi instrument screening.

This is a bounded retrospective research catalog, NOT a positive crypto
identity registry. Dates printed on provider announcements do not authenticate
their original publication timestamp, or prove the instrument's PIT state.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from hashlib import sha256
import json
from typing import Mapping

VERSION = "bybit-negative-tradfi-d259-v1"
INS_LOANS = (
    "https://announcements.bybit.com/en/article/"
    "ins-loans-tradfi-perpetual-contracts-leverage-adjustments--art9f80e1dca25d/"
)
INCENTIVE = (
    "https://announcements.bybit.com/en/article/"
    "tradfi-liquidity-incentive-program-weight-adjustments--arte82775610db0/"
)
DUOL = (
    "https://announcements.bybit.com/en/article/"
    "new-listing-listing-of-duolusdt-on-bybit-tradfi-perpetual-on-nov-6-2026-11-00am-utc--artde830783f6d5/"
)
FISV = (
    "https://announcements.bybit.com/en/article/"
    "new-listing-listing-of-fisvusdt-on-bybit-tradfi-perpetual-on-nov-6-2026-11-00am-utc--art5e5431016814/"
)
FN = (
    "https://announcements.bybit.com/en/article/"
    "new-listing-listing-of-fnusdt-on-bybit-tradfi-perpetual-on-nov-6-2026-11-00am-utc--artff454659fb47/"
)
BRENT_BZ = (
    "https://announcements.bybit.com/en/article/"
    "new-listing-bzusdt-perpetual-contract-with-up-to-10x-leverage-blt847e7209dd33a69a/"
)


# All symbols literally listed by Bybit as TradFi in the cited document.
# These are examples from the user's 50-member raw subset, not a complete
# exclusion catalog of the entire market.
_INS = (
    "SOXLUSDT KORUUSDT SNDKUSDT MUUSDT SKHYNIXUSDT SOXSUSDT "
    "SPCXUSDT QQQUSDT SKHYUSDT SNXXUSDT NVDAUSDT INTCUSDT "
    "TSLAUSDT DRAMUSDT MSTRUSDT TQQQUSDT SAMSUNGUSDT GOOGLUSDT"
).split()
_INC = ("XAUUSDT CLUSDT XAGUSDT").split()
_SHORT = {"DUOLUSDT": DUOL, "FISVUSDT": FISV, "FNUSDT": FN}

@dataclass(frozen=True)
class NegativeInstrumentEvidence:
    symbol: str
    provider_category: str
    announcement_date: str
    announcement_url: str

    def __post_init__(self) -> None:
        date.fromisoformat(self.announcement_date)
        if (not self.symbol.endswith("USDT")
                or not self.symbol.isascii() or not self.symbol.isalnum()
                or not self.symbol.isupper()
                or not self.announcement_url.startswith(
                    "https://announcements.bybit.com/en/article/"
                )):
            raise ValueError("negative evidence record invalid")


def _build() -> dict[str, NegativeInstrumentEvidence]:
    items: dict[str, NegativeInstrumentEvidence] = {}
    for symbols, published, link in (
        (_INS, "2026-08-26", INS_LOANS),
        (_INC, "2026-10-19", INCENTIVE),
    ):
        for symbol in symbols:
            if symbol in items:
                raise ValueError("duplicate negative evidence")
            items[symbol] = NegativeInstrumentEvidence(
                symbol, "tradfi_contract_bybit_documented", published, link,
            )
    # D265: literal Bybit listing identifies BZUSDT as *Brent Oil*,
    # not a BitZ/BZ crypto token or a Kanzhun/BZ equity.
    items["BZUSDT"] = NegativeInstrumentEvidence(
        "BZUSDT", "commodity_brent_oil_bybit_documented",
        "2026-05-13", BRENT_BZ,
    )
    for symbol, link in _SHORT.items():
        if symbol in items:
            raise ValueError("duplicate negative evidence")
        items[symbol] = NegativeInstrumentEvidence(
            symbol, "tradfi_equity_new_listing_bybit_documented",
            "2026-11-06", link,
        )
    return items


NEGATIVE_EVIDENCE: Mapping[str, NegativeInstrumentEvidence] = _build()


def catalog_digest() -> str:
    payload = [
        (row.symbol, row.provider_category,
         row.announcement_date, row.announcement_url)
        for row in sorted(NEGATIVE_EVIDENCE.values(), key=lambda x: x.symbol)
    ]
    return sha256(json.dumps(
        payload, ensure_ascii=True, separators=(",", ":"),
    ).encode("ascii")).hexdigest()


def classify_retrospective(symbol: str, archived_base_present: bool) -> str:
    """Only negative provider evidence; absence is NOT crypto certification."""
    if type(symbol) is not str or type(archived_base_present) is not bool:
        raise ValueError("classification input invalid")
    if symbol in NEGATIVE_EVIDENCE:
        return "bybit_tradfi_documented_retrospective"
    if archived_base_present:
        return "archived_crypto_reference_only"
    return "identity_unresolved"


def evidence_for(symbol: str) -> dict | None:
    row = NEGATIVE_EVIDENCE.get(symbol)
    if row is None:
        return None
    return {
        "provider_category": row.provider_category,
        "announcement_date": row.announcement_date,
        "announcement_url": row.announcement_url,
    }
