"""J5/PRE1: static PT-BR mobile PAPER dashboard must never imply live trading."""
from html.parser import HTMLParser
from pathlib import Path
import unittest

from crypto_intelligence_agent.synthetic_order_lifecycle import PaperVenue
from scripts.demo_automated_paper_cycle import simulate_automatic_paper_cycle


ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "web/paper-demo.html"


class PageAudit(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.attrs = []
        self.metrics = {}
        self.metric = None
        self.venues = []
        self.steps = []
        self.text = []

    def handle_starttag(self, tag, attr_list):
        attrs = dict(attr_list)
        self.tags.append(tag)
        self.attrs.append((tag, attrs))
        if tag == "dd" and attrs.get("data-metric"):
            self.metric = attrs["data-metric"]
            self.metrics[self.metric] = ""
        if tag == "article" and attrs.get("data-venue"):
            self.venues.append(attrs["data-venue"])
        if tag == "tr" and attrs.get("data-step"):
            self.steps.append((int(attrs["data-step"]), attrs.get("data-qty")))

    def handle_data(self, data):
        self.text.append(data)
        if self.metric is not None:
            self.metrics[self.metric] += data

    def handle_endtag(self, tag):
        if tag == "dd":
            self.metric = None


class OfflinePaperDashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = PAGE.read_text(encoding="utf-8")
        cls.page = PageAudit()
        cls.page.feed(cls.html)
        cls.page.close()

    def test_accessible_portuguese_and_mobile_viewport(self):
        html = next(a for tag, a in self.page.attrs if tag == "html")
        self.assertEqual(html["lang"], "pt-BR")
        meta = [a for tag, a in self.page.attrs if tag == "meta"]
        self.assertTrue(any(a.get("name") == "viewport" and
                            "width=device-width" in a.get("content", "")
                            for a in meta))
        self.assertIn("@media (max-width: 640px)", self.html)
        self.assertIn("@media (max-width: 420px)", self.html)
        self.assertIn("@media (max-width: 790px)", self.html)
        main = next(a for tag, a in self.page.attrs if tag == "main")
        self.assertEqual(main["data-mode"], "offline_paper")
        self.assertEqual(main["data-demo-only"], "true")
        self.assertIn("SIMULADO", "".join(self.page.text))
        self.assertIn("Negociação real desativada", "".join(self.page.text))

    def test_no_network_actions_scripts_accounts_or_real_order_ui(self):
        forbidden = {"script", "iframe", "form", "button", "input", "object",
                     "embed", "video", "audio", "img", "link"}
        self.assertFalse(forbidden.intersection(self.page.tags))
        links = []
        for tag, attrs in self.page.attrs:
            with self.subTest(tag=tag):
                self.assertFalse(any(k.lower().startswith("on") for k in attrs))
                self.assertFalse(any(k in attrs for k in ("src", "action", "srcset")))
                if "href" in attrs:
                    links.append((tag, attrs["href"]))
        self.assertEqual(links, [("a", "#conteudo-principal")])
        self.assertNotIn("https://", self.html)
        self.assertNotIn("http://", self.html)
        policy = next(a["content"] for tag, a in self.page.attrs
                      if tag == "meta" and a.get("http-equiv") == "Content-Security-Policy")
        self.assertIn("default-src 'none'", policy)
        self.assertIn("connect-src 'none'", policy)
        self.assertIn("form-action 'none'", policy)
        self.assertIn("frame-src 'none'", policy)

    def test_keyboard_skip_navigation_and_scrollable_table_semantics(self):
        main = next(a for tag, a in self.page.attrs if tag == "main")
        self.assertEqual(main.get("id"), "conteudo-principal")
        self.assertEqual(main.get("tabindex"), "-1")
        internal_link = next(a for tag, a in self.page.attrs if tag == "a")
        self.assertEqual(internal_link.get("class"), "skip-link")
        self.assertEqual(internal_link.get("href"), "#conteudo-principal")
        self.assertIn("Pular para o conteúdo principal", " ".join(self.page.text))
        self.assertIn(".skip-link:focus-visible", self.html)
        scroller = next(a for tag, a in self.page.attrs
                        if tag == "div" and a.get("class") == "table-wrap")
        self.assertEqual(scroller.get("role"), "region")
        self.assertEqual(scroller.get("tabindex"), "0")
        self.assertEqual(scroller.get("aria-describedby"), "table-scroll-instructions")
        self.assertIn("Etapas e saldos", scroller.get("aria-label", ""))
        self.assertIn('id="table-scroll-instructions"', self.html)
        self.assertIn("use as setas horizontais", " ".join(self.page.text))
        self.assertIn(".brand span:last-child", self.html)
        self.assertIn("overflow-wrap: anywhere", self.html)

    def test_static_cards_match_current_paper_demo_math(self):
        self.assertEqual(self.page.venues, ["binance_usdm", "bybit_v5"])
        values = {key: str(value).strip() for key, value in self.page.metrics.items()}
        self.assertEqual(set(values), {"initial_units", "filled_exit_units",
                                       "residual_units"})
        self.assertEqual(self.page.steps, [(1, "50"), (2, "30"), (3, "14")])
        for venue in (PaperVenue.BINANCE_USDM, PaperVenue.BYBIT_V5):
            with self.subTest(venue=venue):
                scenario = simulate_automatic_paper_cycle(venue)
                self.assertEqual(values["initial_units"], scenario["initial_confirmed_units"])
                self.assertEqual(values["filled_exit_units"], scenario["filled_exit_units"])
                self.assertEqual(values["residual_units"], scenario["residual_units"])
                self.assertEqual([v for _, v in self.page.steps],
                                 [x["filled_units"] for x in scenario["exit_steps"]])
                self.assertFalse(scenario["orders_sent"])
                self.assertFalse(scenario["live_trading_authorized"])

    def test_provenance_and_real_world_gaps_are_visible(self):
        text = " ".join(self.page.text)
        for requirement in (
            "SIMULADO", "valores fictícios", "Nenhuma ordem foi enviada",
            "nenhuma conta Binance ou Bybit foi acessada",
            "UNKNOWN", "FILL", "6 unidades", "Dados financeiros",
            "Estratégia validada", "Operação segura", "não está homologado",
        ):
            with self.subTest(requirement=requirement):
                self.assertIn(requirement, text)
        self.assertIn("<details>", self.html)
        self.assertIn("<summary>", self.html)

    def test_single_standalone_html_no_runtime_or_external_dependencies(self):
        self.assertTrue(self.html.lstrip().lower().startswith("<!doctype html>"))
        self.assertEqual(self.page.tags.count("main"), 1)
        self.assertEqual(self.page.tags.count("h1"), 1)
        self.assertEqual(self.page.tags.count("footer"), 1)
        self.assertGreaterEqual(self.page.tags.count("section"), 5)
        self.assertNotIn("data-live-enabled=\"true\"", self.html)


if __name__ == "__main__":
    unittest.main()
