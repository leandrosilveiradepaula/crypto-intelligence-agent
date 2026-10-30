"""J5 #385: mobile PAPER runner readiness from existing read-only journal."""
from decimal import Decimal as D
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.paper_position_reservations import SQLitePaperPositionJournal
from crypto_intelligence_agent.paper_position_inspection import (
    PaperPositionInspection, inspect_paper_position,
)
from crypto_intelligence_agent.synthetic_order_lifecycle import PaperOrderEventKind
from scripts.inspect_paper_positions import (
    TEMPLATE, multi_paper_snapshot, render_paper_positions,
)
from test_paper_position_reservations import (
    T, e, opened_order, plan, entire_plan, exit_order,
)


class PaperRunnerMobileTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path=Path(tmp.name)/"paper.sqlite"
        self.store=SQLitePaperPositionJournal(self.path)
        self.initial=self.store.create_position(
            position_id="fixture_mobile_runner",
            opening_intent=opened_order(),
            opening_events=(e("mobile_runner_open",PaperOrderEventKind.FILL,1,"100"),),
            exit_plan=plan(),plan_version="fixture_mobile_v1",
            synthetic_lot_step_units=D(1),as_of_ms=T+1)

    def view(self):
        selected=(inspect_paper_position(self.path,self.initial.position_id),)
        return multi_paper_snapshot(selected),render_paper_positions(
            selected,TEMPLATE.read_text(encoding="utf-8"))

    def test_unfilled_runner_is_not_reported_as_confirmed(self):
        snap,html=self.view()
        p=snap["positions"][0]
        self.assertEqual(p["runner_readiness"],"WAITING_FOR_PARTIAL_FILLS")
        self.assertFalse(p["trailing_stop_active"])
        self.assertFalse(p["native_stop_verified"])
        self.assertIn("Aguardando preenchimento das parciais",html)
        self.assertIn("trailing não ativo",html)
        self.assertIn("Runner PAPER",html)

    def test_unknown_or_pending_exit_has_priority_over_runner(self):
        intent=exit_order("mobilepending","50",1)
        self.store.reserve_exit(self.initial.position_id,1,intent,as_of_ms=T+1)
        snap,html=self.view()
        self.assertEqual(snap["positions"][0]["runner_readiness"],
                         "PENDING_EXIT_RECONCILIATION")
        self.assertIn("Saída pendente ou incerta",html)
        self.assertNotIn("Runner confirmado —",html)

    def test_all_three_tranches_filled_leave_runner_unprotected(self):
        current=self.initial
        for index,amount in enumerate(("50","30","14"),start=1):
            intent=exit_order(f"mobile{index}",amount,
                              current.as_of_ms-T,
                              cap=str(current.confirmed_remaining_units))
            current=self.store.reserve_exit(current.position_id,index,intent,
                                            as_of_ms=current.as_of_ms)
            current=self.store.append_exit_events(
                current.position_id,intent.intent_id,
                (e(f"mobile_runner_fill{index}",PaperOrderEventKind.FILL,
                   current.as_of_ms-T+1,amount),),
                as_of_ms=current.as_of_ms+1)
        snap,html=self.view()
        self.assertEqual(snap["positions"][0]["runner_readiness"],
                         "RUNNER_CONFIRMED_NOT_PROTECTED")
        self.assertEqual(snap["positions"][0]["runner_floor_units"],"6")
        self.assertFalse(snap["positions"][0]["trailing_stop_active"])
        self.assertFalse(snap["positions"][0]["native_stop_verified"])
        self.assertIn("Runner confirmado — stop não instalado",html)
        self.assertIn('data-field="runner-readiness"',html)
        self.assertNotIn("<script",html.lower())
        self.assertNotIn("https://",html)
        self.assertFalse(snap["orders_sent"])
        self.assertFalse(snap["live_trading_authorized"])

    def test_zero_residual_plan_is_not_mislabeled_runner(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"zero-runner.sqlite"
            journal=SQLitePaperPositionJournal(path)
            journal.create_position(
                position_id="fixture_no_runner",
                opening_intent=opened_order(),
                opening_events=(e("mobile_zero_runner",PaperOrderEventKind.FILL,1,"100"),),
                exit_plan=entire_plan(),plan_version="fixture_zero_v1",
                synthetic_lot_step_units=D(1),as_of_ms=T+1)
            selected=(inspect_paper_position(path,"fixture_no_runner"),)
            r=multi_paper_snapshot(selected)
            self.assertEqual(r["positions"][0]["runner_readiness"],
                             "NO_RESIDUAL_RUNNER_CONFIGURED")

    def test_no_network_or_journal_mutation(self):
        before=self.store.load(self.initial.position_id)
        with patch("socket.create_connection",side_effect=AssertionError("network")):
            with patch("urllib.request.urlopen",side_effect=AssertionError("network")):
                x,html=self.view()
        self.assertEqual(self.store.load(self.initial.position_id),before)
        self.assertFalse(x["financial_pnl_available"])
        self.assertIn("SIMULADO",html)
        self.assertNotIn("preço mark atual",json.dumps(x,ensure_ascii=False))


if __name__=="__main__":
    unittest.main()
