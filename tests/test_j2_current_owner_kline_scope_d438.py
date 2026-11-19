"""D438 tests: revalidate owner J1 epoch/cache without disk/network access."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_closed_stream_cache import (
    HOUR_MS, MAX_SCOPE_AGE_MS, OfflineReviewedStreamScope,
)
from crypto_intelligence_agent.j1_n50_ws_dynamic_scope import DynamicN50WSAdmission
from crypto_intelligence_agent.j2_current_j1_n50_public_scope_d406 import CurrentResearchN50
from crypto_intelligence_agent.market_data import DataGapError, DataValidationError
import crypto_intelligence_agent.j2_current_owner_kline_scope_d438 as bridge
from scripts.demo_j2_prospective_bybit_research_d436 import _scope


NOW = 1_800_000_000_000
RANK = "a" * 64
META = "b" * 64
PRIVATE = Path(__file__).resolve().parents[1] / "owner-fixture-never-read"


def example():
    base = _scope().contracts[0]
    contracts = tuple(
        replace(base, symbol=sym, base_coin=sym[:-4],
                observed_at_ms=NOW - 2_000, registry_sha256=META)
        for sym in ("BTCUSDT",) + tuple(f"R{i:02d}USDT" for i in range(1, 50))
    )
    scope = OfflineReviewedStreamScope(NOW - 1_000, META, contracts, 500)
    research = CurrentResearchN50(
        tuple(x.symbol for x in contracts), RANK, META, NOW - 4_000)
    pointer = SimpleNamespace(status="active_n50_ws_epoch_revalidated",
                              ws_directory=PRIVATE / "cache",
                              ranked_scope_sha256=RANK,
                              ws_metadata_sha256=META,
                              activated_at_ms=research.activated_at_ms)
    admission = DynamicN50WSAdmission(
        scope, RANK, META, scope.observed_at_ms)
    cache = SimpleNamespace(status="private_n50_ws_admission_loaded_revalidated",
                            admission=admission)
    return scope, research, pointer, cache


class OwnerKlineD438Tests(unittest.TestCase):
    def test_missing_gate_must_not_read_private_state(self):
        with patch.object(bridge, "read_current_j1_n50_scope",
                          side_effect=AssertionError("I/O")):
            with self.assertRaises(DataValidationError):
                bridge.read_current_owner_n50_kline_scope(
                    state_directory=PRIVATE, now_ms=NOW)

    def test_owner_cohort_is_reused_not_ranked_or_recreated(self):
        scope, research, pointer, cache = example()
        with patch.object(bridge, "read_current_j1_n50_scope",
                          side_effect=[research, research]) as owner:
            with patch.object(bridge, "load_active_n50_ws_epoch",
                              return_value=pointer) as active:
                with patch.object(bridge, "load_n50_ws_dynamic_admission",
                                  return_value=cache) as cached:
                    value = bridge.read_current_owner_n50_kline_scope(
                        state_directory=PRIVATE, now_ms=NOW,
                        allow_private_pointer_read=True)
        self.assertIs(value, scope)
        self.assertEqual(owner.call_count, 2)
        self.assertEqual(active.call_count, 1)
        self.assertEqual(cached.call_count, 1)
        self.assertEqual({x.symbol for x in value.contracts},
                         set(research.symbols))
        self.assertEqual(cached.call_args.kwargs["expected_ranked_scope_sha256"], RANK)

    def test_rotation_or_changed_metadata_is_not_accepted(self):
        scope, research, pointer, cache = example()
        modified = replace(research, metadata_sha256="c" * 64)
        for first, second, ptr, cached in (
            (research, modified, pointer, cache),
            (research, research, replace_pointer(pointer, ws_metadata_sha256="c" * 64), cache),
            (research, research, pointer, SimpleNamespace(
                status=cache.status, admission=replace(cache.admission,
                metadata_sha256="c" * 64))),
        ):
            with self.subTest():
                with patch.object(bridge, "read_current_j1_n50_scope",
                                  side_effect=[first, second]):
                    with patch.object(bridge, "load_active_n50_ws_epoch",
                                      return_value=ptr):
                        with patch.object(bridge, "load_n50_ws_dynamic_admission",
                                          return_value=cached):
                            with self.assertRaises(DataGapError):
                                bridge.read_current_owner_n50_kline_scope(
                                    state_directory=PRIVATE, now_ms=NOW,
                                    allow_private_pointer_read=True)

    def test_stale_future_or_missing_btc_fails_closed(self):
        scope, research, pointer, cache = example()
        for at in (scope.observed_at_ms - 1,
                   scope.observed_at_ms + MAX_SCOPE_AGE_MS + 1):
            with self.subTest(at=at):
                with patch.object(bridge, "read_current_j1_n50_scope",
                                  side_effect=[research, research]):
                    with patch.object(bridge, "load_active_n50_ws_epoch",
                                      return_value=pointer):
                        with patch.object(bridge, "load_n50_ws_dynamic_admission",
                                          return_value=cache):
                            with self.assertRaises(DataGapError):
                                bridge.read_current_owner_n50_kline_scope(
                                    state_directory=PRIVATE, now_ms=at,
                                    allow_private_pointer_read=True)
        no_btc = replace(scope, contracts=tuple(
            replace(x, symbol="R50USDT", base_coin="R50")
            if x.symbol == "BTCUSDT" else x for x in scope.contracts))
        changed = replace(cache.admission, ws_scope=no_btc)
        with patch.object(bridge, "read_current_j1_n50_scope",
                          side_effect=[research, research]):
            with patch.object(bridge, "load_active_n50_ws_epoch",
                              return_value=pointer):
                with patch.object(bridge, "load_n50_ws_dynamic_admission",
                                  return_value=SimpleNamespace(
                                      status=cache.status, admission=changed)):
                    with self.assertRaises(DataGapError):
                        bridge.read_current_owner_n50_kline_scope(
                            state_directory=PRIVATE, now_ms=NOW,
                            allow_private_pointer_read=True)


def replace_pointer(pointer, **kwargs):
    return SimpleNamespace(**{**vars(pointer), **kwargs})


if __name__ == "__main__":
    unittest.main()
