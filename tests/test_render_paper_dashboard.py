"""J5/PRE2: strict fixture-to-static-HTML export, NEVER a live dashboard."""
from contextlib import redirect_stdout
from copy import deepcopy
from decimal import Decimal
from html.parser import HTMLParser
from io import StringIO
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from scripts.render_paper_dashboard import (
    InvalidPaperSnapshot, TEMPLATE, make_paper_snapshot,
    main, render_paper_dashboard, validate_paper_snapshot,
)


class SnapshotHTMLAudit(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.visible = []
        self.attrs = []
        self.metrics = {}
        self.metric = None
        self.rows = []

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        self.tags.append(tag)
        self.attrs.append((tag, attrs))
        if tag == "dd" and attrs.get("data-metric"):
            self.metric = attrs["data-metric"]
            self.metrics[self.metric] = ""
        if tag == "tr" and attrs.get("data-step"):
            self.rows.append((attrs["data-step"], attrs.get("data-qty")))

    def handle_data(self, data):
        self.visible.append(data)
        if self.metric is not None:
            self.metrics[self.metric] += data

    def handle_endtag(self, tag):
        if tag == "dd":
            self.metric = None


class RenderPaperDashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot = make_paper_snapshot()
        cls.template = TEMPLATE.read_text(encoding="utf-8")
        cls.rendered = render_paper_dashboard(cls.snapshot, cls.template)

    def test_fixture_contract_is_explicitly_non_live(self):
        checked = validate_paper_snapshot(self.snapshot)
        self.assertEqual(self.snapshot["schema_version"], "paper_dashboard_snapshot_v1")
        self.assertEqual(len(checked), 2)
        self.assertEqual([v["venue_candidate"] for v in checked],
                         ["binance_usdm", "bybit_v5"])
        self.assertFalse(self.snapshot["orders_sent"])
        self.assertFalse(self.snapshot["live_trading_authorized"])
        for scenario in checked:
            self.assertEqual(scenario["quality"], "synthetic_fixture_only")
            self.assertFalse(scenario["orders_sent"])
            self.assertFalse(scenario["approved_for_live_use"])
            self.assertFalse(scenario["real_financial_pnl_available"])
            self.assertEqual(scenario["market_data_source"],
                             "invented_unit_test_values_not_exchange_data")

    def test_page_is_rendered_from_fixture_with_all_repeated_values(self):
        parser = SnapshotHTMLAudit()
        parser.feed(self.rendered)
        self.assertEqual(parser.metrics,
                         {"initial_units": "100", "filled_exit_units": "94",
                          "residual_units": "6"})
        self.assertEqual(parser.rows,
                         [("1", "50"), ("2", "30"), ("3", "14")])
        self.assertEqual(self.rendered.count(">100 unidades<"), 2)
        self.assertEqual(self.rendered.count(">50 / 30 / 14<"), 2)
        self.assertEqual(self.rendered.count(">6 unidades<"), 2)
        self.assertIn(">50 + 30 + 14 unidades</small>", self.rendered)
        self.assertIn(">6% da posição inicial</small>", self.rendered)
        self.assertIn(">6 unidades (6%)</strong>", self.rendered)
        for amount, rest in (("50", "50"), ("30", "20"), ("14", "6")):
            self.assertIn(f">{amount}</strong> unidades</td>", self.rendered)
            self.assertIn(f">{rest}</td></tr>", self.rendered)

    def test_nonhundred_consistent_synthetic_fixture_changes_all_visible_fields(self):
        alt = deepcopy(self.snapshot)
        for item in alt["results"]:
            item["initial_confirmed_units"] = "200"
            item["filled_exit_units"] = "188"
            item["residual_units"] = "12"
            for step, qty in zip(item["exit_steps"], ("100", "60", "28")):
                step["filled_units"] = qty
        html = render_paper_dashboard(alt, self.template)
        self.assertIn('data-metric="initial_units">200</dd>', html)
        self.assertIn('data-metric="filled_exit_units">188</dd>', html)
        self.assertIn('data-metric="residual_units">12</dd>', html)
        self.assertIn('data-step="1" data-qty="100"', html)
        self.assertIn('data-step="2" data-qty="60"', html)
        self.assertIn('data-step="3" data-qty="28"', html)
        self.assertIn('>100 / 60 / 28</strong>', html)
        self.assertIn(">12 unidades (6%)</strong>", html)
        self.assertIn(">100 + 60 + 28 unidades</small>", html)
        self.assertIn(">200</span> unidades abstratas", html)
        self.assertIn(">200</span> unidades.", html)
        self.assertNotIn(">50 / 30 / 14</strong>", html)
        self.assertNotIn(">6 unidades (6%)</strong>", html)

    def test_reject_live_approval_and_extra_pnl_fields(self):
        for key, value in (("orders_sent", True),
                           ("live_trading_authorized", True),
                           ("mode", "live"), ("mode", "testnet")):
            with self.subTest(key=key):
                data = deepcopy(self.snapshot)
                data[key] = value
                with self.assertRaises(InvalidPaperSnapshot):
                    render_paper_dashboard(data, self.template)
        for key, value in (
            ("orders_sent", True), ("live_trading_authorized", True),
            ("approved_for_live_use", True),
            ("venue_selected_for_live", True),
            ("real_financial_pnl_available", True),
            ("quality", "actual_market_data"),
            ("market_data_source", "exchange_data"),
        ):
            with self.subTest(key=key):
                data = deepcopy(self.snapshot)
                data["results"][0][key] = value
                with self.assertRaises(InvalidPaperSnapshot):
                    render_paper_dashboard(data, self.template)
        data = deepcopy(self.snapshot)
        data["results"][0]["profit_percent"] = "9999"
        with self.assertRaises(InvalidPaperSnapshot):
            render_paper_dashboard(data, self.template)
        data = deepcopy(self.snapshot)
        data["account_api_key"] = "do_not_render"
        with self.assertRaises(InvalidPaperSnapshot):
            render_paper_dashboard(data, self.template)

    def test_reject_conflicting_venues_steps_status_and_unbalanced_fills(self):
        for change in (
            lambda v: v[1].update(venue_candidate="binance_usdm"),
            lambda v: v[1].update(initial_confirmed_units="300"),
            lambda v: v[0].update(filled_exit_units="95"),
            lambda v: v[0].update(residual_units="7"),
            lambda v: v[0]["exit_steps"][0].update(filled_units="51"),
            lambda v: v[0]["exit_steps"][1].update(status="UNKNOWN"),
            lambda v: v[0]["exit_steps"][2].update(basis="INITIAL_POSITION"),
            lambda v: v[0]["exit_steps"][0].update(step=True),
            lambda v: v[0].update(unknown_resolved_by_explicit_fixture_fill=False),
        ):
            data = deepcopy(self.snapshot)
            change(data["results"])
            with self.subTest(data=data["results"][0]["exit_steps"]):
                with self.assertRaises(InvalidPaperSnapshot):
                    render_paper_dashboard(data, self.template)

    def test_reject_decimal_injection_nan_and_unbounded_values(self):
        for value in ("<svg onload=alert(1)>", "NaN", "Infinity",
                      "-1", "1e500", "0.000000000000001",
                      "123456789012345678901234", 10, None, True):
            with self.subTest(value=value):
                data = deepcopy(self.snapshot)
                data["results"][0]["filled_exit_units"] = value
                with self.assertRaises(InvalidPaperSnapshot):
                    render_paper_dashboard(data, self.template)

    def test_missing_or_duplicated_template_marker_fails_before_export(self):
        missing = self.template.replace(
            'data-snapshot-key="exit-1-fill"',
            'data-snapshot-key="deleted-exit-fill"',
        )
        duplicate = self.template.replace(
            'data-snapshot-key="exit-1-fill"',
            'data-snapshot-key="exit-1-fill" data-copy="exit-1-fill"',
        ).replace("</body>", '<span data-snapshot-key="exit-1-fill">50</span></body>')
        for html in (missing, duplicate, self.template.replace("SIMULADO", "LIVE")):
            with self.subTest(html_len=len(html)), self.assertRaises(InvalidPaperSnapshot):
                render_paper_dashboard(self.snapshot, html)
        unsafe = self.template.replace("</body>", "<script>alert(1)</script></body>")
        with self.assertRaises(InvalidPaperSnapshot):
            render_paper_dashboard(self.snapshot, unsafe)
        for injection in (
            '<a href="https://example.invalid">externo</a>',
            '<img src="https://example.invalid/pixel.png">',
            '<span onclick="alert(1)">handler</span>',
            '<style>@import url(https://example.invalid/remote.css);</style>',
        ):
            with self.subTest(injection=injection), self.assertRaises(InvalidPaperSnapshot):
                render_paper_dashboard(
                    self.snapshot, self.template.replace("</body>", injection + "</body>"),
                )

    def test_standalone_page_preserves_accessibility_and_blocks_network(self):
        parsed = SnapshotHTMLAudit()
        parsed.feed(self.rendered)
        html = next(a for tag, a in parsed.attrs if tag == "html")
        self.assertEqual(html.get("lang"), "pt-BR")
        main = next(a for tag, a in parsed.attrs if tag == "main")
        self.assertEqual(main.get("data-mode"), "offline_paper")
        self.assertEqual(main.get("data-demo-only"), "true")
        self.assertEqual(main.get("data-snapshot-schema"), "paper_dashboard_snapshot_v1")
        self.assertEqual(parsed.tags.count("h1"), 1)
        self.assertEqual(parsed.tags.count("footer"), 1)
        self.assertIn("SIMULADO", " ".join(parsed.visible))
        self.assertIn(":focus-visible", self.rendered)
        self.assertIn("@media (max-width: 640px)", self.rendered)
        self.assertIn("@media (max-width: 420px)", self.rendered)
        for forbidden in ("script", "form", "button", "input", "iframe",
                          "img", "link", "object", "embed"):
            self.assertNotIn(forbidden, parsed.tags)
        links = []
        for tag, attrs in parsed.attrs:
            self.assertFalse(any(k.lower().startswith("on") for k in attrs))
            self.assertFalse(any(k in attrs for k in ("src", "srcset", "action")))
            if "href" in attrs:
                links.append((tag, attrs["href"]))
        self.assertEqual(links, [("a", "#conteudo-principal")])
        self.assertEqual(main.get("id"), "conteudo-principal")
        self.assertEqual(main.get("tabindex"), "-1")
        self.assertIn(".skip-link:focus-visible", self.rendered)
        scroll = next(a for tag, a in parsed.attrs
                      if tag == "div" and a.get("class") == "table-wrap")
        self.assertEqual(scroll.get("tabindex"), "0")
        self.assertEqual(scroll.get("role"), "region")
        self.assertEqual(scroll.get("aria-describedby"), "table-scroll-instructions")
        self.assertNotIn("http://", self.rendered)
        self.assertNotIn("https://", self.rendered)
        self.assertIn("default-src 'none'", self.rendered)
        self.assertIn("connect-src 'none'", self.rendered)

    def test_same_snapshot_has_byte_exact_deterministic_html(self):
        self.assertEqual(self.rendered,
                         render_paper_dashboard(make_paper_snapshot(), self.template))

    def test_cli_stdout_and_new_file_are_equal_without_overwrite(self):
        a = StringIO()
        with redirect_stdout(a):
            main([])
        self.assertEqual(a.getvalue(), self.rendered)
        with tempfile.TemporaryDirectory() as d:
            destination = Path(d) / "new-paper-view.html"
            main(["--output", str(destination)])
            self.assertEqual(destination.read_text("utf-8"), self.rendered)
            with self.assertRaises(FileExistsError):
                main(["--output", str(destination)])
            self.assertEqual(destination.read_text("utf-8"), self.rendered)

    def test_json_export_is_only_generated_fixture_with_explicit_v1_schema(self):
        output = StringIO()
        with redirect_stdout(output):
            main(["--format", "json"])
        data = json.loads(output.getvalue())
        self.assertEqual(data, self.snapshot)
        self.assertEqual(data["schema_version"], "paper_dashboard_snapshot_v1")
        self.assertFalse(data["orders_sent"])
        self.assertFalse(data["live_trading_authorized"])
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "snapshot.json"
            main(["--format", "json", "--output", str(target)])
            self.assertEqual(json.loads(target.read_text("utf-8")), data)
            with self.assertRaises(FileExistsError):
                main(["--format", "json", "--output", str(target)])
        tampered = deepcopy(self.snapshot)
        tampered["schema_version"] = "paper_dashboard_snapshot_live_v2"
        with self.assertRaises(InvalidPaperSnapshot):
            validate_paper_snapshot(tampered)

    def test_cli_never_accepts_external_json_and_no_network_is_used(self):
        with redirect_stdout(StringIO()), self.assertRaises(SystemExit):
            main(["--input", "/tmp/untrusted.json"])
        with patch("urllib.request.urlopen",
                   side_effect=AssertionError("offline renderer used network")):
            with patch("socket.create_connection",
                       side_effect=AssertionError("offline renderer used network")):
                data = make_paper_snapshot()
                html = render_paper_dashboard(data, self.template)
                self.assertIn("Nenhuma ordem foi enviada", html)


if __name__ == "__main__":
    unittest.main()
