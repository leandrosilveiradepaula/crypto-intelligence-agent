"""D317: owner D287 -> bounded D314 GET -> immutable D316 cache, no WS."""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from crypto_intelligence_agent.bybit_public_j1_transport import (
    BoundedBybitPublicClient, instruments_url,
)
from crypto_intelligence_agent.j1_auto_research_epoch import FILE_NAME
from crypto_intelligence_agent.j1_n50_ws_metadata_bootstrap import (
    _exclusive_metadata_ingress, cache_current_n50_ws_metadata_once,
)
from crypto_intelligence_agent.j1_n50_ws_private_cache import (
    FILE_NAME as CACHE_NAME, load_n50_ws_dynamic_admission,
)
from scripts.cache_j1_n50_ws_metadata_owner_once import main as owner_cli
from test_j1_n50_managed_cycle import T, SYMS, sealed
from test_j1_n50_ws_dynamic_scope_d314 import OBS, page


@unittest.skipUnless(
    os.name == "posix" and os.geteuid() != 0,
    "owner-only capture and lock require POSIX nonroot",
)
class OwnerN50WSMetadataIngressTests(unittest.TestCase):
    def setUp(self):
        tmp=TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root=Path(tmp.name)
        self.manifest=root/"ranked"
        self.ws=root/"ws-n50"
        for d in (self.manifest,self.ws):
            d.mkdir(mode=0o700)
            d.chmod(0o700)
        self.ranked=sealed(T)
        p=self.manifest/FILE_NAME
        p.write_text(json.dumps(self.ranked,sort_keys=True),encoding="ascii")
        p.chmod(0o600)
        self.gets=[]
        def fetch(url,size):
            self.gets.append(url)
            return json.dumps(page(tuple(SYMS))).encode("ascii")
        self.client=BoundedBybitPublicClient(transport=fetch)

    def call(self,**changed):
        args=dict(
            manifest_directory=self.manifest,
            ws_directory=self.ws,
            allow_public_network=True,
            confirm_region_and_personal_research=True,
            enable_n50_ws_metadata_capture=True,
            allow_private_manifest_read=True,
            allow_private_ws_cache_write=True,
            client=self.client,
            clock_ms=lambda:OBS,
        )
        args.update(changed)
        return cache_current_n50_ws_metadata_once(**args)

    def assert_safe(self,out):
        text=json.dumps(out,sort_keys=True)
        for symbol in SYMS:
            self.assertNotIn(symbol,text)
        self.assertNotIn("retMsg",text)
        self.assertEqual(out["kline_rest_gets"],0)
        self.assertEqual(out["websocket_connections_opened"],0)
        self.assertFalse(out["orders_sent"])
        self.assertFalse(out["systemd_modified"])
        self.assertFalse(out["marketwide_top50_verified"])
        self.assertFalse(out["source_authenticated"])

    def test_one_public_catalog_get_immutably_cached_with_same_50(self):
        out=self.call()
        self.assertEqual(out["status"],"ws_metadata_owner_n50_cached_for_ws_research",out)
        self.assertEqual(out["catalog_gets"],1)
        self.assertEqual(self.gets,[instruments_url()])
        self.assertEqual(out["selected_contracts"],50)
        self.assertTrue(out["private_cache_written"])
        self.assertEqual(len(out["private_cache_sha256"]),64)
        self.assertEqual((self.ws/CACHE_NAME).stat().st_mode&0o777,0o600)
        self.assert_safe(out)
        again=load_n50_ws_dynamic_admission(
            directory=self.ws,current_at_ms=OBS+2000,
            expected_ranked_scope_sha256=self.ranked["scope_digest_sha256"],
            allow_private_scope_read=True,
        )
        self.assertEqual(again.status,"private_n50_ws_admission_loaded_revalidated")
        self.assertEqual(again.admission.selected_contracts,50)
        self.assertEqual(len(again.admission.ws_scope.contracts),50)
        self.assertEqual(out["ws_metadata_sha256"],again.admission.metadata_sha256)

    def test_existing_cache_blocks_before_any_new_http_get(self):
        self.assertTrue(self.call()["private_cache_written"])
        other=BoundedBybitPublicClient(
            transport=lambda *_: (_ for _ in ()).throw(AssertionError("GET")),
        )
        out=self.call(client=other)
        self.assertEqual(out["status"],"ws_metadata_cache_exists_no_get")
        self.assertEqual(out["catalog_gets"],0)
        self.assertEqual(other.requests_attempted,0)
        self.assert_safe(out)

    def test_10006_one_get_no_cache_no_retry_and_no_provider_leak(self):
        limited=BoundedBybitPublicClient(
            transport=lambda url,size: self.gets.append(url) or
            b'{"retCode":10006,"retMsg":"PRIVATE_VALUE"}',
        )
        out=self.call(client=limited)
        self.assertEqual(out["status"],"ws_metadata_capture_abstain_no_retry")
        self.assertEqual(out["failure_category"],"provider_rate_limit_no_retry")
        self.assertEqual(out["catalog_gets"],1)
        self.assertEqual(len(self.gets),1)
        self.assertFalse((self.ws/CACHE_NAME).exists())
        self.assert_safe(out)
        self.assertNotIn("PRIVATE_VALUE",json.dumps(out))

    def test_no_optin_denies_before_get_and_file(self):
        for missing in (
            "allow_public_network",
            "confirm_region_and_personal_research",
            "enable_n50_ws_metadata_capture",
            "allow_private_manifest_read",
            "allow_private_ws_cache_write",
        ):
            with self.subTest(missing=missing):
                out=self.call(**{missing:False})
                self.assertEqual(out["status"],"ws_metadata_bootstrap_optin_required")
                self.assertEqual(out["catalog_gets"],0)
                self.assertFalse((self.ws/CACHE_NAME).exists())
        self.assertEqual(self.gets,[])

    def test_mismatched_rank_or_outdated_catalog_refuses_before_get(self):
        p=self.manifest/FILE_NAME
        doc=dict(self.ranked,scope_digest_sha256="0"*64)
        p.write_text(json.dumps(doc,sort_keys=True))
        p.chmod(0o600)
        out=self.call()
        self.assertEqual(out["status"],"ws_metadata_bootstrap_integrity_or_lock_abstain")
        self.assertEqual(self.gets,[])
        p.write_text(json.dumps(self.ranked,sort_keys=True))
        p.chmod(0o600)
        out=self.call(clock_ms=lambda:OBS+20*60_000)
        self.assertEqual(out["status"],"ws_metadata_capture_window_expired_no_get")
        self.assertEqual(self.gets,[])

    def test_concurrent_bootstraps_do_not_issue_extra_get(self):
        with _exclusive_metadata_ingress(self.ws):
            result=self.call()
        self.assertEqual(result["status"],"ws_metadata_bootstrap_integrity_or_lock_abstain")
        self.assertEqual(result["catalog_gets"],0)
        self.assertEqual(self.gets,[])
        self.assertFalse((self.ws/CACHE_NAME).exists())

    def test_untrusted_tradfi_metadata_has_no_cache(self):
        doc=page(tuple(SYMS))
        doc["result"]["list"][0]["underlyingTicker"]="AAPL"
        bad=BoundedBybitPublicClient(
            transport=lambda *_: json.dumps(doc).encode("ascii"),
        )
        out=self.call(client=bad)
        self.assertEqual(out["status"],"ws_metadata_capture_abstain_no_retry")
        self.assertEqual(out["catalog_gets"],1)
        self.assertFalse((self.ws/CACHE_NAME).exists())

    def test_cli_default_never_starts_capture(self):
        buf=StringIO()
        with redirect_stdout(buf):
            rc=owner_cli([
                "--manifest-directory",str(self.manifest),
                "--ws-directory",str(self.ws),
            ])
        output=json.loads(buf.getvalue())
        self.assertEqual(rc,77)
        self.assertEqual(output["status"],"ws_metadata_bootstrap_optin_required")
        self.assert_safe(output)
        self.assertFalse((self.ws/CACHE_NAME).exists())


if __name__=="__main__":
    unittest.main()
