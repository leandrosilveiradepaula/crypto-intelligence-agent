"""D316: immutable owner D314 cache; fixtures only, no GET, WS or orders."""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_closed_stream_cache import (
    SQLiteOfflineClosedStreamJournal, parse_offline_confirmed_kline,
)
from crypto_intelligence_agent.bybit_ws_supervisor import _topic_batches
from crypto_intelligence_agent.j1_n50_ws_private_cache import (
    FILE_NAME, cache_n50_ws_dynamic_admission_once,
    load_n50_ws_dynamic_admission,
)
from crypto_intelligence_agent.j1_n50_ws_hourly_attestation import (
    attest_n50_ws_hour_once,
)
from test_j1_n50_managed_cycle import T, SYMS, sealed
from test_j1_n50_ws_dynamic_scope_d314 import page, OBS
from test_j1_n50_ws_hourly_attestation_d313 import candle, DECISION


@unittest.skipUnless(
    os.name == "posix" and os.geteuid() != 0,
    "D316 real 0700/0600 owner file requires nonroot POSIX",
)
class N50WSPrivateCacheTests(unittest.TestCase):
    def setUp(self):
        holder = TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.directory = Path(holder.name) / "private-ws-epoch"
        self.directory.mkdir(mode=0o700)
        self.directory.chmod(0o700)
        self.ranked = sealed(T)
        self.args = dict(
            directory=self.directory,
            ranked_scope=self.ranked,
            instrument_pages=(page(tuple(SYMS)),),
            requested_cursors=(None,),
            page_received_at_ms=(OBS,),
            captured_at_ms=OBS,
        )

    def cache(self, **override):
        args=dict(self.args)
        args["allow_private_scope_write"]=True
        args.update(override)
        with patch(
            "crypto_intelligence_agent.bybit_public_j1_transport.BoundedBybitPublicClient.get",
            side_effect=AssertionError("unexpected REST GET"),
        ):
            return cache_n50_ws_dynamic_admission_once(**args)

    def load(self, **override):
        args=dict(
            directory=self.directory,
            current_at_ms=OBS+2000,
            expected_ranked_scope_sha256=self.ranked["scope_digest_sha256"],
            allow_private_scope_read=True,
        )
        args.update(override)
        with patch(
            "crypto_intelligence_agent.bybit_public_j1_transport.BoundedBybitPublicClient.get",
            side_effect=AssertionError("unexpected REST GET"),
        ):
            return load_n50_ws_dynamic_admission(**args)

    def assert_private_report(self, result):
        text=json.dumps(result.sanitized_report(), sort_keys=True)
        for sym in SYMS:
            self.assertNotIn(sym,text)
        self.assertNotIn("turnover",text)
        self.assertEqual(result.sanitized_report()["network_requests"],0)
        self.assertEqual(result.sanitized_report()["websocket_connections_opened"],0)
        self.assertFalse(result.sanitized_report()["orders_sent"])
        self.assertFalse(result.sanitized_report()["marketwide_top50_verified"])
        self.assertFalse(result.sanitized_report()["source_authenticated"])

    def test_immutable_one_capture_reloads_same_exact_fifty_without_get(self):
        created=self.cache()
        self.assertEqual(created.status,"private_n50_ws_admission_cached_immutable",created)
        self.assertTrue(created.file_written)
        self.assertEqual(created.admission.selected_contracts,50)
        cache=self.directory/FILE_NAME
        self.assertEqual(cache.stat().st_mode&0o777,0o600)
        self.assertEqual(self.directory.stat().st_mode&0o777,0o700)
        self.assertEqual(len(created.file_digest_sha256),64)
        loaded=self.load()
        self.assertEqual(loaded.status,"private_n50_ws_admission_loaded_revalidated",loaded)
        self.assertFalse(loaded.file_written)
        self.assertEqual(loaded.file_digest_sha256,created.file_digest_sha256)
        self.assertEqual(loaded.admission.metadata_sha256,created.admission.metadata_sha256)
        self.assertEqual(loaded.ranked_scope,self.ranked)
        self.assertEqual(len(_topic_batches(loaded.admission.ws_scope)[0]),50)
        self.assertEqual(set(m.symbol for m in loaded.admission.ws_scope.contracts),
                         set(SYMS))
        self.assert_private_report(created)
        self.assert_private_report(loaded)

        # Rehydrated scope can still pass D313 for a separate WS-only journal.
        journal=SQLiteOfflineClosedStreamJournal.create(
            self.directory/"ws-confirmed.sqlite",
        )
        for symbol in SYMS:
            event=parse_offline_confirmed_kline(
                candle(symbol), scope=loaded.admission.ws_scope,
                received_at_ms=DECISION+2000,
            )
            self.assertEqual(journal.append(event),"appended")
        evidence=attest_n50_ws_hour_once(
            ranked_scope=loaded.ranked_scope, ws_scope=loaded.admission.ws_scope,
            journal=journal, decision_at_ms=DECISION,
            observed_at_ms=DECISION+4000,
        )
        self.assertEqual(evidence["status"],
                         "ws_hour_50_observed_local_only_not_marketwide")
        self.assertEqual(evidence["confirmed_contracts"],50)

    def test_no_optin_means_no_private_file_or_read(self):
        denied=cache_n50_ws_dynamic_admission_once(**self.args)
        self.assertEqual(denied.status,"owner_optin_required")
        self.assertFalse((self.directory/FILE_NAME).exists())
        denied_read=load_n50_ws_dynamic_admission(
            directory=self.directory,current_at_ms=OBS+2000,
            expected_ranked_scope_sha256=self.ranked["scope_digest_sha256"],
        )
        self.assertEqual(denied_read.status,"owner_optin_required")
        self.assert_private_report(denied)

    def test_second_write_abstains_with_exact_bytes_unchanged(self):
        self.assertTrue(self.cache().file_written)
        before=(self.directory/FILE_NAME).read_bytes()
        again=self.cache()
        self.assertEqual(again.status,"cache_exists_no_overwrite")
        self.assertFalse(again.file_written)
        self.assertEqual((self.directory/FILE_NAME).read_bytes(),before)
        self.assert_private_report(again)

    def test_invalid_metadata_is_denied_before_any_file_write(self):
        bad=page(tuple(SYMS))
        bad["result"]["list"][0]["underlyingTicker"]="AAPL"
        out=self.cache(instrument_pages=(bad,))
        self.assertEqual(out.status,"private_n50_ws_cache_write_abstain")
        self.assertFalse((self.directory/FILE_NAME).exists())
        self.assert_private_report(out)

    def test_stale_ranked_epoch_or_wrong_expected_digest_abstains(self):
        self.assertTrue(self.cache().file_written)
        for opts in (
            {"current_at_ms":OBS+49*3_600_000},
            {"expected_ranked_scope_sha256":"0"*64},
            {"current_at_ms":OBS-1},
        ):
            with self.subTest(opts=opts):
                out=self.load(**opts)
                self.assertEqual(out.status,"private_n50_ws_cache_read_abstain")
                self.assertIsNone(out.admission)
                self.assert_private_report(out)

    def test_one_byte_tamper_makes_replay_fail_closed(self):
        self.assertTrue(self.cache().file_written)
        file=self.directory/FILE_NAME
        data=file.read_bytes()
        file.write_bytes(data[:-1]+(b"x" if data[-1:] != b"x" else b"y"))
        result=self.load()
        self.assertEqual(result.status,"private_n50_ws_cache_read_abstain")
        self.assertIsNone(result.admission)

    def test_unsafe_directory_permission_denies_before_write(self):
        self.directory.chmod(0o755)
        result=self.cache()
        self.assertEqual(result.status,"private_n50_ws_cache_write_abstain")
        self.assertFalse((self.directory/FILE_NAME).exists())
        self.directory.chmod(0o700)

    def test_symlinked_scope_file_is_rejected(self):
        other=self.directory/"innocent"
        other.write_bytes(b"dummy")
        other.chmod(0o600)
        (self.directory/FILE_NAME).symlink_to(other)
        self.assertEqual(self.cache().status,"cache_exists_no_overwrite")
        self.assertEqual(self.load().status,"private_n50_ws_cache_read_abstain")

    def test_raw_private_symbols_are_not_emitted_by_public_summary(self):
        created=self.cache()
        self.assertEqual(created.status,"private_n50_ws_admission_cached_immutable")
        assert SYMS[0] in (self.directory/FILE_NAME).read_text("ascii")
        report=json.dumps(created.sanitized_report())
        self.assertNotIn(SYMS[0],report)
        self.assertNotIn("USDT",report)


if __name__=="__main__":
    unittest.main()
