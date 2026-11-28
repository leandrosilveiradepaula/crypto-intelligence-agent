"""Synthetic-only D548 parity tests; no provider requests."""
from dataclasses import replace
from decimal import Decimal
import gzip
from hashlib import sha256
import io
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.j3_long_history_d528 import DAY, EXCHANGE, MARKET, QUALITY
from crypto_intelligence_agent.j3_trade_archive_reconciliation_d548 import (
    MAX_LINE, STEP, reconcile_daily_trades,
)
from crypto_intelligence_agent.market_data import ClosedCandle, DataValidationError
from scripts.reconcile_j3_trade_archive_d548 import _bounded_lines, _compare

START = 1704067200000
SYMBOL = "BTCUSDT"
HEADER = "timestamp,symbol,side,size,price,trdMatchID\n"


def trade(t, ident, *, price="10", size="2", symbol=SYMBOL):
    return f"{t},{symbol},Buy,{size},{price},{ident}\n"


def bars():
    return [
        ClosedCandle(EXCHANGE, MARKET, SYMBOL, "5m", t, t + STEP - 1,
                     Decimal("10"), Decimal("10"), Decimal("10"), Decimal("10"),
                     Decimal("2"), Decimal("20"), QUALITY)
        for t in range(START, START + DAY, STEP)
    ]


def rows():
    return [
        trade(t // 1000, f"trade-{i}")
        for i, t in enumerate(range(START, START + DAY, STEP))
    ]


def run(lines=None, reference=None, **kwargs):
    return reconcile_daily_trades(
        [HEADER, *rows()] if lines is None else lines,
        bars() if reference is None else reference,
        symbol=SYMBOL, day_start_ms=START, **kwargs,
    )


class ArchiveParityTests(unittest.TestCase):
    def test_full_day_in_reverse_file_order(self):
        result = run([HEADER, *reversed(rows())])
        self.assertEqual(result["status"], "exact_day_match")
        self.assertEqual(result["exact_paired_bars"], 288)
        self.assertFalse(result["source_equivalence_approved"])
        self.assertFalse(result["data_stored"])
        self.assertEqual(result["public_gets"], 0)

    def test_submillisecond_timestamp_and_price_order(self):
        ref = bars()
        ref[0] = replace(ref[0], close=Decimal("11"), high=Decimal("11"),
                         base_volume=Decimal("5"), quote_volume=Decimal("53"))
        first = START // 1000
        lines = [HEADER, trade(f"{first}.0009", "later", price="11", size="3"),
                 *rows()]
        result = run(lines, ref)
        self.assertEqual(result["status"], "exact_day_match")

    def test_tied_boundary_price_ambiguous(self):
        ref = bars()
        ref[0] = replace(ref[0], high=Decimal("11"), close=Decimal("11"),
                         base_volume=Decimal("3"), quote_volume=Decimal("31"))
        lines = [HEADER, trade(START // 1000, "same-time", price="11", size="1"), *rows()]
        result = run(lines, ref)
        self.assertEqual(result["status"], "not_equivalent")
        self.assertEqual(result["ambiguous_paired_bars"], 1)
        self.assertEqual(result["exact_paired_bars"], 287)
        self.assertEqual(result["field_mismatches"]["quote_volume"], 0)

    def test_ties_at_nonboundary_do_not_mark_open_close_ambiguous(self):
        t = START // 1000
        ref = bars()
        ref[0] = replace(ref[0], close=Decimal("9"), low=Decimal("8"),
                         high=Decimal("11"), base_volume=Decimal("5"),
                         quote_volume=Decimal("48"))
        result = run([HEADER, trade(t+2, "c", price="9", size="1"),
                      trade(t+1, "b", price="11", size="1"),
                      trade(t+1, "a", price="8", size="1"), *rows()], ref)
        self.assertEqual(result["status"], "exact_day_match")

    def test_missing_bar_and_reference_not_imputed(self):
        result = run([HEADER, *rows()[1:]], bars()[:-1])
        self.assertEqual(result["status"], "not_equivalent")
        self.assertEqual(result["archive_missing_bars"], 1)
        self.assertEqual(result["rest_missing_bars"], 1)
        self.assertEqual(result["archive_only_bars"], 1)
        self.assertEqual(result["rest_only_bars"], 1)
        self.assertEqual(result["exact_paired_bars"], 286)

    def test_turnover_mismatch_exact_decimal(self):
        ref = bars()
        ref[1] = replace(ref[1], quote_volume=Decimal("20.000000000001"))
        result = run(reference=ref)
        self.assertEqual(result["status"], "not_equivalent")
        self.assertEqual(result["field_mismatches"]["quote_volume"], 1)

    def test_invalid_archive_rejected(self):
        first = rows()[0]
        cases = [
            [HEADER, first, first],
            [HEADER, trade((START+DAY)//1000, "after")],
            [HEADER, trade(START//1000, "wrong", symbol="ETHUSDT")],
            [HEADER, trade(START//1000, "zero", size="0")],
            [HEADER, trade(START//1000, "nan", price="NaN")],
            ["timestamp,timestamp,symbol,size,price,trdMatchID\n", first],
            [HEADER, '1,"BTCUSDT,Buy,1,1,x\n'],
            [HEADER, "x" * (MAX_LINE+1)],
        ]
        for lines in cases:
            with self.subTest(lines=lines[:1]), self.assertRaises(DataValidationError):
                run(lines)
        with self.assertRaises(DataValidationError):
            run(max_rows=1)

    def test_invalid_reference_rejected(self):
        for ref in ([bars()[0], bars()[0]],
                    [replace(bars()[0], quality="other")],
                    [replace(bars()[0], close_time_ms=START)],
                    [replace(bars()[0], quote_volume=Decimal("NaN"))]):
            with self.assertRaises(DataValidationError):
                run(reference=ref)

    def test_owner_cli_gzip_reader_and_digest(self):
        # Only the private OS boundary is mocked for portable offline CI.
        data = gzip.compress("".join([HEADER, *rows()]).encode("utf-8"))
        with TemporaryDirectory() as d:
            path = Path(d) / "BTCUSDT2024-01-01.csv.gz"
            path.write_bytes(data)
            with patch("scripts.reconcile_j3_trade_archive_d548._private_directory",
                       side_effect=lambda p: p), patch(
                "scripts.reconcile_j3_trade_archive_d548._owner_file",
                side_effect=lambda parent, name: os.open(parent / name, os.O_RDONLY | getattr(os, "O_BINARY", 0)),
            ):
                result = _compare(path, bars(), SYMBOL, START, 1000)
                self.assertEqual(result["status"], "exact_day_match")
                self.assertEqual(result["archive_sha256"], sha256(data).hexdigest())
                self.assertEqual(path.read_bytes(), data)
                path.write_bytes(data[:-8])
                with self.assertRaises((EOFError, OSError)):
                    _compare(path, bars(), SYMBOL, START, 1000)

    def test_decompression_line_bound(self):
        with self.assertRaises(DataValidationError):
            list(_bounded_lines(io.BytesIO(b"x" * (MAX_LINE+1))))


if __name__ == "__main__":
    unittest.main()
