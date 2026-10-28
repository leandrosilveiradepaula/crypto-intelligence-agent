"""J6/PRE4: multi-journal recovery status stays diagnostic and fail-closed."""
from pathlib import Path
import tempfile
import unittest

from crypto_intelligence_agent.paper_order_store import SQLitePaperOrderJournal
from crypto_intelligence_agent.paper_position_reservations import SQLitePaperPositionJournal
from crypto_intelligence_agent.paper_recovery_status import (
    PaperRecoveryState, inspect_local_paper_recovery_status,
)
from tests.test_paper_open_health import opening, fill


class RecoveryStatusTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.orders_path = Path(tmp.name) / "orders.sqlite"
        self.positions_path = Path(tmp.name) / "positions.sqlite"
        self.orders = SQLitePaperOrderJournal(self.orders_path)
        SQLitePaperPositionJournal(self.positions_path)

    def inspect(self):
        return inspect_local_paper_recovery_status(
            self.orders_path, self.positions_path,
        )

    def test_empty_is_only_hypothetical_and_never_authorizes_open(self):
        status = self.inspect()
        self.assertEqual(status.state, PaperRecoveryState.PAPER_FLAT_HYPOTHETICAL_ONLY)
        self.assertFalse(status.cross_database_atomic_snapshot_available)
        self.assertFalse(status.native_stop_verified)
        self.assertFalse(status.new_open_authorized)
        self.assertFalse(status.orders_sent)
        self.assertFalse(status.live_trading_authorized)

    def test_pending_open_blocks(self):
        self.orders.reserve(opening())
        status = self.inspect()
        self.assertEqual(status.state, PaperRecoveryState.BLOCKED)
        self.assertEqual(status.reason, "paper_order_reconciliation_required")

    def test_fill_without_position_blocks(self):
        self.orders.reserve(opening())
        self.orders.append_events(opening().intent_id, (fill(),), as_of_ms=opening().created_at_ms + 1)
        self.assertEqual(self.inspect().state, PaperRecoveryState.BLOCKED)

    def test_missing_position_journal_unverified(self):
        self.positions_path.unlink()
        self.assertEqual(self.inspect().state, PaperRecoveryState.UNVERIFIED)

    def test_same_path_unverified(self):
        self.assertEqual(
            inspect_local_paper_recovery_status(self.orders_path, self.orders_path).state,
            PaperRecoveryState.UNVERIFIED,
        )

    def test_read_only_no_file_creation(self):
        self.orders_path.unlink()
        self.assertEqual(self.inspect().state, PaperRecoveryState.UNVERIFIED)
        self.assertFalse(self.orders_path.exists())


if __name__ == "__main__":
    unittest.main()
