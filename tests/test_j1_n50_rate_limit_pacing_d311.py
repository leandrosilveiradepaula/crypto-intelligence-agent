"""D311 regression: N50 hourly pacing after observed 10006 failback.

All tests are offline: no provider, SQLite owner files or systemd changes.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch
import unittest

from crypto_intelligence_agent import bybit_public_j1_transport as transport
from crypto_intelligence_agent.bybit_public_j1_transport import (
    BoundedBybitPublicClient, J1BybitCaptureError,
    MIN_PUBLIC_GET_INTERVAL_SECONDS, kline_url,
)
from crypto_intelligence_agent.j1_n50_supervised_once import (
    N50_HOURLY_MIN_GET_INTERVAL_SECONDS,
    run_supervised_n50_once,
)
from test_j1_n50_supervised_once import (
    SCOPE, OUTPUT, T, HOUR_MS, manifest, readiness, worker,
)


class D311PacingTests(unittest.TestCase):
    def invoke(self, **overrides):
        opts = dict(
            manifest_directory=SCOPE, output_directory=OUTPUT,
            owner_ok=True, clock_ms=lambda: T + HOUR_MS + 120_000,
            allow_private_manifest_read=True,
            allow_private_readonly_audit=True,
            allow_public_network=True, allow_private_storage=True,
            confirm_region_and_personal_research=True,
            enable_n50_research_once=True,
        )
        opts.update(overrides)
        return run_supervised_n50_once(**opts)

    def test_default_global_and_n2_pacing_remain_unchanged(self):
        self.assertEqual(MIN_PUBLIC_GET_INTERVAL_SECONDS, 2.0)
        self.assertEqual(
            BoundedBybitPublicClient().min_interval_seconds, 2.0,
        )
        self.assertEqual(N50_HOURLY_MIN_GET_INTERVAL_SECONDS, 8.0)
        self.assertLess(50 * N50_HOURLY_MIN_GET_INTERVAL_SECONDS, 15*60)
        # The capture-and-seal path creates a default 2s client, not the
        # N50-only 8s client instantiated only for the hourly writer.

    def test_untrusted_or_too_fast_pacing_cannot_change_network_contract(self):
        for invalid in (None, True, False, 0, -2, 1.99, 12.001,
                        "8", float("nan"), float("inf"), -float("inf")):
            with self.subTest(invalid=repr(invalid)):
                with self.assertRaises(ValueError):
                    BoundedBybitPublicClient(min_interval_seconds=invalid)
        self.assertEqual(
            BoundedBybitPublicClient(min_interval_seconds=12).min_interval_seconds,
            12.0,
        )

    def test_real_network_boundary_uses_eight_seconds_but_never_retries_10006(self):
        # No actual network: _network_get is mocked and the monotonic
        # clock advances through fake sleep. RetMsg must never propagate.
        clock = [100.0]
        starts = []
        sleeps = []
        calls = []
        def now():
            return clock[0]
        def sleep(seconds):
            self.assertGreater(seconds, 0)
            clock[0] += seconds
            sleeps.append(seconds)
        def network(uri, max_bytes):
            starts.append(now())
            calls.append(uri)
            if len(calls) == 4:
                return b'{"retCode":10006,"retMsg":"SECRET_PRIVATE_TOKEN"}'
            return b'{"retCode":0,"result":{},"time":1793000000000}'
        with (
            patch.object(transport.time, "monotonic", side_effect=now),
            patch.object(transport.time, "sleep", side_effect=sleep),
            patch.object(transport, "_network_get", side_effect=network),
        ):
            client = BoundedBybitPublicClient(min_interval_seconds=8.0)
            for i in range(3):
                client.get(kline_url("BTCUSDT", T-3*HOUR_MS+i*HOUR_MS,
                                     T-2*HOUR_MS+i*HOUR_MS))
            with self.assertRaisesRegex(
                J1BybitCaptureError, "provider_rate_limit_no_retry",
            ) as error:
                client.get(kline_url("BTCUSDT", T-HOUR_MS, T))
        self.assertEqual(client.requests_attempted, 4)
        self.assertEqual(client.last_provider_retcode, 10006)
        self.assertEqual(len(calls), 4)
        self.assertEqual(len(sleeps), 3)
        self.assertTrue(all(abs(v-8.0) < 0.01 for v in sleeps))
        self.assertEqual(starts, [100.0, 108.0, 116.0, 124.0])
        self.assertNotIn("SECRET_PRIVATE_TOKEN", str(error.exception))

    def test_safe_writer_injects_new_pacing_after_all_owner_gates(self):
        with (
            patch("crypto_intelligence_agent.j1_n50_supervised_once._strict_owner"),
            patch("crypto_intelligence_agent.j1_n50_supervised_once.load_private_ranked_scope",
                  return_value=manifest()),
            patch.object(Path, "is_file", return_value=True),
            patch("crypto_intelligence_agent.j1_n50_supervised_once.audit_existing_rest_resume",
                  return_value=readiness()),
            patch("crypto_intelligence_agent.j1_n50_supervised_once.run_current_ranked_epoch_once",
                  return_value=worker()) as run,
        ):
            good = self.invoke()
            self.assertEqual(good["status"], "research_hour_persisted")
            client = run.call_args.kwargs["client"]
            self.assertIs(type(client), BoundedBybitPublicClient)
            self.assertEqual(client.min_interval_seconds, 8.0)
            self.assertEqual(client.requests_attempted, 0)
            self.assertEqual(good["requests_attempted"], 50)
            self.assertFalse(good["orders_sent"])

            # An offline fixture client is never silently replaced.
            dummy = BoundedBybitPublicClient(
                transport=lambda *_: b'{"retCode":0,"result":{}}',
            )
            self.invoke(client=dummy)
            self.assertIs(run.call_args.kwargs["client"], dummy)

    def test_no_client_constructed_before_owner_and_audit_preflights(self):
        with (
            patch("crypto_intelligence_agent.j1_n50_supervised_once.BoundedBybitPublicClient",
                  side_effect=AssertionError("must not create network client")) as factory,
            patch("crypto_intelligence_agent.j1_n50_supervised_once._strict_owner"),
            patch("crypto_intelligence_agent.j1_n50_supervised_once.load_private_ranked_scope",
                  return_value=manifest()),
            patch.object(Path, "is_file", return_value=True),
            patch("crypto_intelligence_agent.j1_n50_supervised_once.audit_existing_rest_resume",
                  return_value={**readiness(), "journal_integrity_verified": False}),
            patch("crypto_intelligence_agent.j1_n50_supervised_once.run_current_ranked_epoch_once",
                  side_effect=AssertionError("must not GET")) as runner,
        ):
            self.assertEqual(self.invoke()["status"], "blocked")
            self.assertEqual(self.invoke(enable_n50_research_once=False)
                             ["status"], "optin_required")
            self.assertEqual(self.invoke(owner_ok=False)["status"], "blocked")
            factory.assert_not_called()
            runner.assert_not_called()

    def test_provider_rate_limit_still_fails_closed_and_preserves_partial_count(self):
        fail = worker()
        fail.update(status="research_provider_fail_stop",
                    failure_category="provider_rate_limit_no_retry",
                    requests_attempted=4, new_closed_candles=3)
        with (
            patch("crypto_intelligence_agent.j1_n50_supervised_once._strict_owner"),
            patch("crypto_intelligence_agent.j1_n50_supervised_once.load_private_ranked_scope",
                  return_value=manifest()),
            patch.object(Path, "is_file", return_value=True),
            patch("crypto_intelligence_agent.j1_n50_supervised_once.audit_existing_rest_resume",
                  return_value=readiness()),
            patch("crypto_intelligence_agent.j1_n50_supervised_once.run_current_ranked_epoch_once",
                  return_value=fail),
        ):
            out = self.invoke()
        self.assertEqual(out["status"], "blocked")
        self.assertEqual(out["failure_category"], "provider_rate_limit_no_retry")
        self.assertEqual((out["requests_attempted"],out["new_closed_candles"]),(4,3))
        self.assertFalse(out["marketwide_top50_verified"])
        self.assertFalse(out["orders_sent"])
        self.assertFalse(out["systemd_modified"])


if __name__ == "__main__":
    unittest.main()
