"""D482: explicit PAPER-DEMO can persist without forging J2 signals."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from crypto_intelligence_agent.bybit_public_ticker_state_d385 import BybitTickerQuote
from crypto_intelligence_agent.j2_j3_j4_btc_paper_shadow_d442 import CostedShadowPolicy
from crypto_intelligence_agent.j4_shadow_public_paper_pilot_d426 import ShadowPaperPolicy
from crypto_intelligence_agent.j4_private_paper_ws_operator_d425 import load_private_paper_routes
from crypto_intelligence_agent.j5_owner_paper_positions_d446 import read_owner_paper_positions
from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.paper_position_reservations import SQLitePaperPositionJournal
from crypto_intelligence_agent.synthetic_position_state import SyntheticSide
from scripts.run_j4_persistent_public_demo_d482 import create_persistent_demo

NOW = 1_795_435_000_000


@unittest.skipUnless(os.name == "posix" and hasattr(os, "geteuid")
                     and os.geteuid() != 0, "owner nonroot required")
class PersistentDemoTests(unittest.TestCase):
    def setUp(self):
        t = TemporaryDirectory(prefix="cia-d482-")
        self.addCleanup(t.cleanup)
        self.home = Path(t.name)
        self.home.chmod(0o700)
        self.quote = BybitTickerQuote(
            symbol="BTCUSDT", received_at_ms=NOW,
            exchange_at_ms=NOW-100, cross_sequence=10,
            last_price=Decimal("90000"), mark_price=Decimal("90000"),
            index_price=Decimal("90000"), bid_price=Decimal("89999"),
            ask_price=Decimal("90001"), bid_size=Decimal("20"),
            ask_size=Decimal("20"), turnover_24h=None,
            volume_24h=None, funding_rate=Decimal("0"),
        )
        self.policy = CostedShadowPolicy(
            ShadowPaperPolicy("BTCUSDT", SyntheticSide.LONG,
                              margin_quote=Decimal("5"), leverage=50,
                              stop_distance_bps=Decimal("50"),
                              target1_distance_bps=Decimal("200"),
                              target2_distance_bps=Decimal("300")),
            Decimal("6"), Decimal("6"), Decimal("3"), Decimal("3"),
        )

    def test_durable_open_j5_and_intrahour_exit_reservation(self):
        router, created = create_persistent_demo(
            paper_directory=self.home, quote=self.quote,
            policy=self.policy, universe_at_ms=NOW-2000,
        )
        self.assertEqual(created["entry_provenance"],
                         "EXPLICIT_PAPER_DEMO_NOT_J2_SIGNAL")
        self.assertIsNone(created["position_expires_at"])
        self.assertFalse(created["live_orders_sent"])
        self.assertEqual((self.home / "paper-positions.sqlite").stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.home / "paper-routes.json").stat().st_mode & 0o777, 0o600)
        restored = load_private_paper_routes(self.home)
        self.assertEqual(len(restored.monitored_position_ids), 1)
        snap = read_owner_paper_positions(directory=self.home)
        self.assertEqual(len(snap["positions"]), 1)
        self.assertFalse(snap["orders_sent"])
        self.assertFalse(snap["live_trading_authorized"])
        later = replace(
            self.quote, exchange_at_ms=NOW+1000,
            received_at_ms=NOW+1100, cross_sequence=11,
            mark_price=Decimal("92000"), last_price=Decimal("92000"),
            index_price=Decimal("92000"), bid_price=Decimal("91999"),
            ask_price=Decimal("92001"),
        )
        restored.process(later)
        book = SQLitePaperPositionJournal(self.home/"paper-positions.sqlite")
        position = book.load(restored.monitored_position_ids[0])
        self.assertGreaterEqual(len(position.exit_orders), 1)
        with self.assertRaises(DataValidationError):
            create_persistent_demo(
                paper_directory=self.home, quote=self.quote,
                policy=self.policy, universe_at_ms=NOW-2000,
            )
        self.assertEqual(len(read_owner_paper_positions(directory=self.home)["positions"]), 1)

    def test_denies_stale_quote_without_side_effect(self):
        with self.assertRaises(DataValidationError):
            create_persistent_demo(
                paper_directory=self.home,
                quote=replace(self.quote, exchange_at_ms=NOW-4000),
                policy=self.policy, universe_at_ms=NOW-5000,
            )
        self.assertEqual(list(self.home.iterdir()), [])

    def test_denies_first_target_cost_veto_without_persistence(self):
        weak = CostedShadowPolicy(
            ShadowPaperPolicy("BTCUSDT", SyntheticSide.LONG,
                              margin_quote=Decimal("5"), leverage=50,
                              stop_distance_bps=Decimal("50"),
                              target1_distance_bps=Decimal("10"),
                              target2_distance_bps=Decimal("20")),
            Decimal("6"), Decimal("6"), Decimal("3"), Decimal("3"),
        )
        with self.assertRaises(DataValidationError):
            create_persistent_demo(
                paper_directory=self.home, quote=self.quote, policy=weak,
                universe_at_ms=NOW-2000,
            )
        self.assertEqual(list(self.home.iterdir()), [])
