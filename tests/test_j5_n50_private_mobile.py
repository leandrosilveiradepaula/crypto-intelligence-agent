"""J5/D301: audited N50 report -> private offline PT-BR mobile, no trading."""
from __future__ import annotations

from html.parser import HTMLParser
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.j2_n50_private_screen import _result
from crypto_intelligence_agent.j5_n50_private_html import (
    InvalidPrivateResearchView, render_n50_private_html,
    validate_n50_private_report, write_n50_private_html_once,
)
from scripts.render_j5_n50_private_mobile_once import main as cli_main

T = 1_800_000_000_000


def report(*, btc: bool = True) -> dict:
    r = _result(
        "descriptive_research_ready" if btc else
        "btc_context_missing_research_only"
    )
    r.update(
        epoch_id=f"epoch-{T:013d}", scope_digest_sha256="a"*64,
        latest_published_end_ms=T, as_of_ms=T+180_000,
        eligible_closed_bars_per_asset=24, audited_assets=50,
        btc_context_available=btc,
        btc_return_24bar_pct="50" if btc else None,
        descriptive_up_breakouts=10, descriptive_down_breakouts=10,
        descriptive_inside_bars=30, window_digest_sha256="b"*64,
        owner_journal_integrity_verified=True,
    )
    symbols=(
        ["BTCUSDT"]+[f"TST{i:02d}USDT" for i in range(1,50)]
        if btc else
        [f"TST{i:02d}USDT" for i in range(50)]
    )
    directions=(
        ["above_prior_23h_high"]*10+
        ["below_prior_23h_low"]*10+
        ["inside_prior_23h_range"]*30
    )
    r["research_rows"] = [
        {
            "descriptive_rank":i+1, "symbol":symbol,
            "return_24bars_pct":str(50-i),
            "relative_vs_btc_pct_points":str(-i) if btc else None,
            "mean_true_range_14_pct":"1.25",
            "quote_turnover_24bars_usdt":"2500.00",
            "last_quote_turnover_vs_prior23_mean":"2",
            "last_closed_bar_breakout":directions[i],
            "approved_for_signals":False,"orders_sent":False,
        } for i,symbol in enumerate(symbols)
    ]
    return r


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags=[]
        self.attrs=[]
        self.text=[]
    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attrs.append((tag,dict(attrs)))
    def handle_data(self, data):
        self.text.append(data)


class J5PrivateN50HtmlTests(unittest.TestCase):
    def test_private_html_is_portuguese_responsive_and_inert(self):
        data=report()
        html=render_n50_private_html(data)
        page=Page()
        page.feed(html)
        page.close()
        self.assertIn("lang=\"pt-BR\"",html)
        self.assertIn("width=device-width",html)
        self.assertIn("@media(max-width:560px)",html)
        self.assertIn("PESQUISA PROVISÓRIA",html)
        self.assertIn("NENHUMA ORDEM",html)
        self.assertIn("nenhuma ordem",html.lower())
        self.assertIn("BTCUSDT",html)
        self.assertIn("TST49USDT",html)
        self.assertIn("Acima da máxima anterior",html)
        self.assertIn("Variação observada em 24 barras",html)
        self.assertNotIn("<script",html.lower())
        self.assertNotIn("http://",html)
        self.assertNotIn("https://",html)
        self.assertNotIn("const ws=",html)
        self.assertEqual(page.tags.count("main"),1)
        self.assertEqual(page.tags.count("h1"),1)
        self.assertEqual(page.tags.count("tr"),51)
        self.assertEqual(page.tags.count("article"),4)
        self.assertEqual(page.tags.count("footer"),1)
        self.assertFalse({"script","button","input","form","img","link",
                          "iframe","object","video","audio"}.intersection(page.tags))
        for tag, attrs in page.attrs:
            self.assertFalse(any(k.lower().startswith("on") for k in attrs))
            self.assertFalse(any(k in attrs for k in ("src","srcset","action")))
            if "href" in attrs:
                self.assertEqual((tag, attrs["href"]),("a","#conteudo"))
        csp=[a["content"] for tag,a in page.attrs
             if tag=="meta" and a.get("http-equiv")=="Content-Security-Policy"]
        self.assertEqual(len(csp),1)
        self.assertIn("default-src 'none'",csp[0])
        self.assertIn("connect-src 'none'",csp[0])
        self.assertIn("frame-src 'none'",csp[0])
        self.assertEqual(len(validate_n50_private_report(data)),50)

    def test_btc_missing_is_flagged_and_is_not_a_signal(self):
        html=render_n50_private_html(report(btc=False))
        self.assertIn("sem referência BTC, apenas descrição",html)
        self.assertIn("não disponível na coorte",html)
        self.assertIn("—",html)
        self.assertIn("NENHUMA ORDEM",html)

    def test_fail_closed_on_malicious_rows_or_false_approval(self):
        bad_cases=[
            ("live", lambda x:x.update(approved_for_live_use=True)),
            ("orders", lambda x:x.update(orders_sent=True)),
            ("integrity", lambda x:x.update(owner_journal_integrity_verified=False)),
            ("fake_count", lambda x:x.update(audited_assets=49)),
            ("wrong_digest", lambda x:x.update(window_digest_sha256="a")),
            ("snapshot_future", lambda x:x.update(as_of_ms=T-1)),
            ("missing_btc", lambda x:x.update(btc_context_available=False)),
            ("short_rows",lambda x:x["research_rows"].pop()),
            ("script",lambda x:x["research_rows"][0].update(
                symbol="<script>alert(1)</script>USDT")),
            ("decimal_nan",lambda x:x["research_rows"][0].update(
                return_24bars_pct="NaN")),
            ("decimal_inf",lambda x:x["research_rows"][0].update(
                return_24bars_pct="Infinity")),
            ("decimal_exponent",lambda x:x["research_rows"][0].update(
                return_24bars_pct="1e-999999")),
            ("price_like_secret",lambda x:x["research_rows"][0].update(
                symbol="\"><img src=x onerror=alert(1)>")),
            ("duplicate_symbol",lambda x:x["research_rows"][1].update(
                symbol="BTCUSDT")),
            ("unsorted_return",lambda x:x["research_rows"][0].update(
                return_24bars_pct="-90")),
            ("extra_row_field",lambda x:x["research_rows"][0].update(
                account_api_key="secret")),
            ("wrong_btc_relative",lambda x:x["research_rows"][0].update(
                relative_vs_btc_pct_points=None)),
            ("bad_breakout_count",lambda x:x.update(descriptive_up_breakouts=12)),
        ]
        for name, mutate in bad_cases:
            with self.subTest(name=name):
                d=report()
                mutate(d)
                with self.assertRaises(InvalidPrivateResearchView):
                    render_n50_private_html(d)

    def test_html_values_are_display_only_and_no_execution_claim(self):
        data=report()
        html=render_n50_private_html(data)
        self.assertIn("50.00%",html)
        self.assertIn("2500.00",html)
        self.assertIn("0.00",html)
        self.assertIn("50",html)
        self.assertNotIn("preço de entrada",html.lower())
        self.assertNotIn("alavancagem recomendada",html.lower())
        self.assertNotIn("pnl",html.lower())


@unittest.skipUnless(os.name=="posix", "private file permissions POSIX")
class J5PrivateHtmlOwnerWriteTests(unittest.TestCase):
    def setUp(self):
        temp=TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)/"private"
        self.root.mkdir(mode=0o700)
        self.root.chmod(0o700)

    def write(self, **kwargs):
        args=dict(
            root_directory=self.root,
            allow_private_report_write=True,
            owner_ok=True,
        )
        args.update(kwargs)
        return write_n50_private_html_once(report(),**args)

    def test_exact_0600_once_idempotent_without_external_files(self):
        r1=self.write()
        self.assertEqual(r1["status"],"private_report_saved",r1)
        self.assertFalse(r1["orders_sent"])
        self.assertFalse(r1["systemd_modified"])
        self.assertFalse(r1["research_journal_modified"])
        parent=self.root/"reports"
        self.assertEqual(parent.stat().st_mode&0o777,0o700)
        file=parent/r1["file_name"]
        self.assertTrue(file.is_file())
        self.assertEqual(file.stat().st_mode&0o777,0o600)
        self.assertIn("PESQUISA PROVISÓRIA",file.read_text(encoding="utf-8"))
        data=file.read_bytes()
        r2=self.write()
        self.assertEqual(r2["status"],"identical_private_report_exists",r2)
        self.assertFalse(r2["private_report_saved"])
        self.assertEqual(file.read_bytes(),data)
        self.assertEqual(len(list(parent.iterdir())),1)

    def test_no_optin_and_wrong_owner_never_create_file(self):
        self.assertEqual(self.write(allow_private_report_write=False)
                         ["status"],"optin_required")
        self.assertEqual(self.write(owner_ok=False)["status"],"blocked")
        self.assertFalse((self.root/"reports").exists())

    def test_symlink_tamper_and_unverified_report_denied(self):
        parent=self.root/"reports"
        parent.symlink_to(self.root)
        self.assertEqual(self.write()["status"],"blocked")
        parent.unlink()
        bad=report()
        bad["source_authenticated"]=True
        self.assertEqual(write_n50_private_html_once(
            bad,root_directory=self.root,
            allow_private_report_write=True,owner_ok=True)["status"],"blocked")
        self.assertFalse(parent.exists())

    def test_existing_file_never_overwritten(self):
        first=self.write()
        target=self.root/"reports"/first["file_name"]
        target.write_text("tampered",encoding="utf-8")
        target.chmod(0o600)
        self.assertEqual(self.write()["status"],"blocked")
        self.assertEqual(target.read_text(encoding="utf-8"),"tampered")


class J5PrivateHtmlCLITests(unittest.TestCase):
    def test_missing_any_of_three_flags_blocks_before_market_read(self):
        with patch(
            "scripts.render_j5_n50_private_mobile_once.audit_private_n50_research",
            side_effect=AssertionError("must not read private state"),
        ):
            for flags in ([],["--allow-private-report-write"],
                          ["--allow-private-readonly-audit",
                           "--allow-private-report-write"]):
                with self.subTest(flags=flags):
                    from io import StringIO
                    from contextlib import redirect_stdout
                    output=StringIO()
                    with redirect_stdout(output):
                        self.assertEqual(cli_main(flags),65)
                    self.assertIn("three_owner_optins_required",output.getvalue())

    def test_cli_denies_unverified_market_before_any_file_write(self):
        with patch(
            "scripts.render_j5_n50_private_mobile_once.audit_private_n50_research",
            return_value={"status":"no_current_integral_checkpoint",
                          "orders_sent":False},
        ), patch(
            "scripts.render_j5_n50_private_mobile_once.write_n50_private_html_once",
            side_effect=AssertionError("must not write"),
        ):
            from io import StringIO
            from contextlib import redirect_stdout
            output=StringIO()
            with redirect_stdout(output):
                rc=cli_main(["--allow-private-readonly-audit",
                             "--allow-private-report-write",
                             "--include-private-symbols"])
            self.assertEqual(rc,65)
            self.assertIn("audit_unavailable_or_unverified",output.getvalue())


if __name__=="__main__":
    unittest.main()
