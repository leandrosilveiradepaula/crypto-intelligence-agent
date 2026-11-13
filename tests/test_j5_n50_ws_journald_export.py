"""J5/APP-DATA1: journalctl JSON adapter with strictly count-only output."""
from __future__ import annotations

import io
import json
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_closed_stream_cache import HOUR_MS
from crypto_intelligence_agent.market_data import DataValidationError
from scripts.export_j5_n50_ws_journald_once import (
    export_n50_journald_progress, main,
)

T = (1_800_000_000_000 // HOUR_MS) * HOUR_MS
NOW = T + 5 * HOUR_MS + 4 * 60_000
SHA = "f" * 64


def report(hour: int, *, failed: bool = False, extra: bool = False) -> dict:
    r = {
        "schema_version": "j1-n50-ws-cached-owner-window-v1",
        "status": ("ws_owner_hour_audit_abstain" if failed
                   else "ws_owner_hour_50_observed_local_only"),
        "expected_contracts": 50,
        "confirmed_contracts": 0 if failed else 50,
        "missing_contracts": 50 if failed else 0,
        "closed_events_appended_to_ws_journal": 50,
        "subscription_acks": 1,
        "http_gets": 0,
        "orders_sent": False,
        "rest_database_modified": False,
        "systemd_modified": False,
        "utc_closed_hour_end_ms": T + hour * HOUR_MS,
        "source_provenance": None if failed else "bybit_public_ws_confirmed",
        "hour_evidence_sha256": None if failed else SHA,
    }
    if extra:
        r["private_symbol"] = "BTCUSDT"
        r["private_price"] = "12345.67"
        r["private_path"] = "/home/owner/secret"
    return r


def entry(hour: int, *, failed: bool = False, extra: bool = False) -> dict:
    close = T + hour * HOUR_MS
    return {
        "_SYSTEMD_UNIT": "cia-j1-n50-ws.service",
        "__REALTIME_TIMESTAMP": str((close + 104_000) * 1000),
        "MESSAGE": json.dumps(report(hour, failed=failed, extra=extra),
                              separators=(",", ":")),
    }


def raw(*items: dict) -> bytes:
    return ("\n".join(json.dumps(x, separators=(",", ":")) for x in items) +
            "\n").encode("utf-8")


class JournalctlExportTests(unittest.TestCase):
    def test_two_success_hours_are_preliminary_not_formal(self):
        boot = entry(4)
        boot["MESSAGE"] = '{"schema_version":"j1-n50-ws-systemd-preflight-v1"}'
        systemd = entry(4)
        systemd["MESSAGE"] = "Service deactivated successfully."
        unrelated = entry(4)
        unrelated["_SYSTEMD_UNIT"] = "cia-other.service"
        result = export_n50_journald_progress(
            raw(entry(4,extra=True),entry(5),boot,systemd,unrelated),
            now_ms=NOW,
        )
        self.assertEqual(result["schema_version"],"j5-n50-ws-log-progress-v1")
        self.assertEqual(result["observed_50_of_50_hours"],2)
        self.assertEqual(result["consecutive_recent_observed_hours"],2)
        self.assertEqual(result["failed_hours"],0)
        self.assertEqual(result["missing_hours"],22)
        self.assertEqual(result["duplicate_hours"],0)
        self.assertEqual([x["state"] for x in result["slots"][-2:]],["ok","ok"])
        self.assertFalse(result["owner_d323_24h_audit_verified"])
        self.assertFalse(result["continuous_collector_verified"])
        self.assertFalse(result["rotation_36h_live_verified"])
        self.assertFalse(result["source_authenticated"])
        self.assertFalse(result["approved_for_signals"])
        self.assertFalse(result["orders_sent"])
        public = json.dumps(result)
        for forbidden in ("BTCUSDT","12345.67",SHA,"/home/owner/secret",
                          "MESSAGE","__REALTIME_TIMESTAMP"):
            self.assertNotIn(forbidden,public)

    def test_fifty_appends_without_audit_is_failure(self):
        result = export_n50_journald_progress(
            raw(entry(3,failed=True),entry(4),entry(5)),now_ms=NOW,
        )
        self.assertEqual(result["observed_50_of_50_hours"],2)
        self.assertEqual(result["failed_hours"],1)
        self.assertEqual(result["consecutive_recent_observed_hours"],2)
        self.assertEqual([r["state"] for r in result["slots"][-3:]],
                         ["failed","ok","ok"])

    def test_duplicate_same_hour_abstains_slot(self):
        result=export_n50_journald_progress(
            raw(entry(4),entry(5),entry(5)),now_ms=NOW,
        )
        self.assertEqual(result["duplicate_hours"],1)
        self.assertEqual(result["observed_50_of_50_hours"],1)
        self.assertEqual(result["consecutive_recent_observed_hours"],0)

    def test_out_of_window_and_premature_new_hour_rejected(self):
        with self.assertRaises(DataValidationError):
            export_n50_journald_progress(
                raw(entry(5)),now_ms=T+5*HOUR_MS+2*60_000,
            )
        with self.assertRaises(DataValidationError):
            export_n50_journald_progress(
                raw(entry(6)),now_ms=NOW,
            )

    def test_bad_journald_envelope_or_payload_never_promotes(self):
        good=entry(5)
        bad_cases = (
            {"_SYSTEMD_UNIT":"cia-j1-n50-ws.service","MESSAGE":good["MESSAGE"]},
            dict(good,__REALTIME_TIMESTAMP="NaN"),
            dict(good,__REALTIME_TIMESTAMP=True),
            dict(good,__REALTIME_TIMESTAMP="9999999999999999"),
            dict(good,MESSAGE='{"schema_version":"j1-n50-ws-cached-owner-window-v1","status":'),
            dict(good,MESSAGE='{"schema_version":"j1-n50-ws-cached-owner-window-v1","status":"fake"}'),
            dict(good,MESSAGE=23),
            dict(good,MESSAGE=json.dumps({**report(5),"orders_sent":True})),
            dict(good,MESSAGE=json.dumps({**report(5),"confirmed_contracts":0,
                                            "missing_contracts":50})),
            dict(good,MESSAGE=json.dumps({**report(5),"hour_evidence_sha256":None})),
        )
        for bad in bad_cases:
            with self.subTest(bad=str(bad)[:80]),self.assertRaises(DataValidationError):
                export_n50_journald_progress(raw(entry(4),bad),now_ms=NOW)

    def test_parser_resource_bounds_and_duplicate_json(self):
        payloads = (
            b"",
            b"not-json\n",
            b'{"_SYSTEMD_UNIT":"cia-j1-n50-ws.service","_SYSTEMD_UNIT":"cia-j1-n50-ws.service"}\n',
            b'{"num":NaN}\n',
            raw({"_SYSTEMD_UNIT":"other","MESSAGE":"progress"}),
            b"x" * 1_048_577,
            b"{}\n"*4097,
            raw(entry(5)).replace(b'"orders_sent":false',b'"orders_sent":true'),
        )
        for payload in payloads:
            with self.subTest(size=len(payload)),self.assertRaises(DataValidationError):
                export_n50_journald_progress(payload,now_ms=NOW)
        for bad in (True,"bad",None,123,bytearray(raw(entry(5)))):
            with self.assertRaises(DataValidationError):
                export_n50_journald_progress(bad,now_ms=NOW)

    def test_cli_no_optin_cannot_read_stdin_and_suppresses_failure_details(self):
        class ForbiddenInput:
            @property
            def buffer(self):
                raise AssertionError("must not consume stdin")
        output=io.StringIO()
        with patch("sys.stdin",ForbiddenInput()),patch("sys.stdout",output):
            self.assertEqual(main([]),65)
        self.assertNotIn("BTCUSDT",output.getvalue())
        self.assertIn("input_invalid_or_unavailable_abstain",output.getvalue())

    def test_cli_json_is_directly_accepted_by_mobile_contract(self):
        stream=io.TextIOWrapper(io.BytesIO(raw(entry(4),entry(5))))
        output=io.StringIO()
        with patch("sys.stdin",stream),patch("sys.stdout",output),patch(
            "time.time_ns",return_value=NOW*1_000_000,
        ),patch("socket.create_connection",side_effect=AssertionError("network")),patch(
            "sqlite3.connect",side_effect=AssertionError("db"),
        ):
            self.assertEqual(main(["--allow-sanitized-journald-stdin"]),0)
        result=json.loads(output.getvalue())
        self.assertEqual(result["observed_50_of_50_hours"],2)
        self.assertEqual(result["hours_in_window"],24)
        self.assertFalse(result["owner_d323_24h_audit_verified"])
        self.assertEqual(result["network_requests"],0)


if __name__=="__main__":
    unittest.main()
