"""PRE5: owner-local sanitized PAPER recovery CLI contract."""
import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from crypto_intelligence_agent.paper_order_store import SQLitePaperOrderJournal
from crypto_intelligence_agent.paper_position_reservations import SQLitePaperPositionJournal
from scripts.inspect_paper_recovery import main


class RecoveryCLITests(unittest.TestCase):
    def test_empty_journals_cannot_claim_recovery(self):
        with TemporaryDirectory() as root:
            orders = Path(root) / "orders.sqlite"
            positions = Path(root) / "positions.sqlite"
            SQLitePaperOrderJournal(orders)
            SQLitePaperPositionJournal(positions)
            before = (orders.read_bytes(), positions.read_bytes())
            out = StringIO()
            with redirect_stdout(out):
                code = main(["--orders", str(orders), "--positions", str(positions)])
            self.assertEqual(code, 2)
            self.assertEqual((orders.read_bytes(), positions.read_bytes()), before)
            payload = json.loads(out.getvalue())
            self.assertEqual(payload["state"], "UNVERIFIED")
            self.assertEqual(payload["reason"], "paper_replay_not_initialized")
            self.assertFalse(payload["new_open_authorized"])
            self.assertFalse(payload["native_stop_verified"])
            self.assertFalse(payload["orders_sent"])
            self.assertNotIn(str(root), out.getvalue())

    def test_missing_file_is_fail_closed_without_creating_it(self):
        with TemporaryDirectory() as root:
            orders = Path(root) / "missing.sqlite"
            positions = Path(root) / "positions.sqlite"
            out = StringIO()
            with redirect_stdout(out):
                code = main(["--orders", str(orders), "--positions", str(positions)])
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(out.getvalue())["state"], "UNVERIFIED")
            self.assertFalse(orders.exists())
            self.assertFalse(positions.exists())

    def test_same_path_never_certifies(self):
        with TemporaryDirectory() as root:
            orders = Path(root) / "orders.sqlite"
            SQLitePaperOrderJournal(orders)
            out = StringIO()
            with redirect_stdout(out):
                code = main(["--orders", str(orders), "--positions", str(orders)])
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(out.getvalue())["state"], "UNVERIFIED")


if __name__ == "__main__":
    unittest.main()
