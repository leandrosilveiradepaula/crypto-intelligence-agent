"""J6/PRE5: finite no-network demo covers all runner stages."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.demo_paper_runner_close_flow import main, run_demo


class PaperRunnerEndToEndDemoTests(unittest.TestCase):
    def test_full_chain_is_deterministic_and_has_no_live_authority(self):
        with patch("socket.create_connection", side_effect=AssertionError("network")):
            with patch("urllib.request.urlopen", side_effect=AssertionError("network")):
                a = run_demo()
                b = run_demo()
        self.assertEqual(a, b)
        self.assertEqual(a["etapas"], [
            "partials_confirmed_paper_only",
            "trailing_trigger_hypothetical_only",
            "runner_exit_reserved_no_fill",
            "restart_without_duplicate",
            "runner_closed_by_explicit_synthetic_fill",
        ])
        self.assertEqual(a["posicao_inicial_unidades_ficticias"], "100")
        self.assertEqual(a["parciais_preenchidas_unidades_ficticias"], "94")
        self.assertEqual(a["runner_fechado_unidades_ficticias"], "6")
        self.assertEqual(a["saldo_final_unidades_ficticias"], "0")
        self.assertEqual(a["intencoes_runner_distintas"], 1)
        self.assertTrue(a["fill_runner_injetado_explicitamente_em_fixture"])
        self.assertFalse(a["ordens_reais_enviadas"])
        self.assertFalse(a["stop_nativo_verificado"])
        self.assertFalse(a["trading_live_autorizado"])
        self.assertFalse(a["rede_utilizada"])
        self.assertFalse(a["arquivos_persistentes_criados"])

    def test_cli_stdout_contains_only_sanitized_json(self):
        out = io.StringIO()
        with patch("socket.create_connection", side_effect=AssertionError("network")):
            with redirect_stdout(out):
                main([])
        text = out.getvalue()
        parsed = json.loads(text)
        self.assertEqual(parsed["modalidade"], "offline_paper")
        self.assertFalse(parsed["dados_de_mercado_reais"])
        self.assertFalse(parsed["lucro_financeiro_calculado"])
        self.assertNotIn("BTCUSDT", text)
        self.assertNotIn("fixture_j6_e2e_open", text)
        self.assertNotIn("sqlite", text.lower())
        self.assertNotIn("http", text.lower())
        self.assertNotIn("3100", text)
        self.assertTrue(text.endswith("\n"))

    def test_cli_rejects_paths_endpoints_credentials_or_override(self):
        for opt in (
            ["--journal", "/tmp/wrong.sqlite"],
            ["--api-key", "fixture_fake"],
            ["--venue", "bybit"],
            ["--enable-live"],
            ["--output", "/tmp/unexpected"],
        ):
            with self.subTest(opt=opt):
                with redirect_stdout(io.StringIO()):
                    with self.assertRaises(SystemExit):
                        main(opt)

    def test_temporary_files_are_destroyed(self):
        created = []
        real_temp = tempfile.TemporaryDirectory
        def temp_factory(*args, **kwargs):
            obj = real_temp(*args, **kwargs)
            created.append(obj.name)
            return obj
        with patch(
            "scripts.demo_paper_runner_close_flow.tempfile.TemporaryDirectory",
            side_effect=temp_factory,
        ):
            run_demo()
        self.assertEqual(len(created), 1)
        self.assertFalse(Path(created[0]).exists())


if __name__ == "__main__":
    unittest.main()
