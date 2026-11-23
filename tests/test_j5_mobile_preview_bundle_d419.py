"""D419: the downloadable offline mobile preview must include ALL local assets.

A browser test against the repository directory can pass even when GitHub's
downloadable ZIP is missing scripts, leaving the user's extracted preview
partly broken. This test cross-checks the actual artifact path manifest
against HTML dependencies before upload, using only Python stdlib.
"""
from __future__ import annotations

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "web" / "app"
WORKFLOW = ROOT / ".github" / "workflows" / "paper-mobile-browser-qa.yml"
_ASSET = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,100}\Z")


def required_local_assets(html: str) -> set[str]:
    scripts = re.findall(r'<script\s+src="\./([^"/]+)"', html)
    styles = re.findall(r'<link\s+rel="stylesheet"\s+href="\./([^"/]+)"', html)
    if not scripts or not styles:
        raise ValueError("J5 browser asset dependencies were not found")
    assets = set(scripts + styles)
    if len(assets) != len(scripts) + len(styles):
        raise ValueError("J5 browser asset dependencies repeated")
    if any(_ASSET.fullmatch(name) is None for name in assets):
        raise ValueError("J5 browser asset filename invalid")
    return assets | {"index.html", "LEIA-ME.txt"}


def packaged_local_assets(workflow: str) -> set[str]:
    # Deliberately keep this parser specific to the ONE public-preview
    # upload-artifact block, so the QA screenshots artifact is not mistaken
    # for a runnable application ZIP.
    start = workflow.find("      - name: Package install-free PAPER mobile app for manual preview\n")
    end = workflow.find("      - name: Attach synthetic offline screenshots and JSON evidence\n")
    if start < 0 or end <= start:
        raise ValueError("D419 preview artifact workflow block missing")
    block = workflow[start:end]
    if "uses: actions/upload-artifact@v4" not in block or "path: |" not in block:
        raise ValueError("D419 preview artifact uploader missing")
    after_path = block.split("path: |", 1)[1]
    paths = re.findall(r"^\s+web/app/([^\s]+)\s*$", after_path, flags=re.MULTILINE)
    if not paths or len(set(paths)) != len(paths):
        raise ValueError("D419 duplicate/missing preview paths")
    if any(_ASSET.fullmatch(name) is None for name in paths):
        raise ValueError("D419 unsafe preview path")
    return set(paths)


class MobilePreviewBundleD419Tests(unittest.TestCase):
    def test_downloadable_zip_manifest_matches_all_local_html_assets(self):
        html = (APP / "index.html").read_text(encoding="utf-8")
        workflow = WORKFLOW.read_text(encoding="utf-8")
        expected = required_local_assets(html)
        listed = packaged_local_assets(workflow)
        self.assertEqual(listed, expected)
        self.assertEqual(len(listed), 14)
        self.assertGreater(len([x for x in listed if x.endswith(".js")]), 4)
        for asset in listed:
            with self.subTest(asset=asset):
                p = APP / asset
                self.assertTrue(p.is_file(), f"missing local asset {asset}")
                self.assertGreater(p.stat().st_size, 0)
                self.assertLess(p.stat().st_size, 100_000)
        self.assertLess(sum((APP / f).stat().st_size for f in listed), 500_000)

    def test_readme_lists_all_required_scripts_and_no_service(self):
        readme = (APP / "LEIA-ME.txt").read_text(encoding="utf-8")
        html = (APP / "index.html").read_text(encoding="utf-8")
        for asset in required_local_assets(html):
            self.assertIn(asset, readme)
        self.assertIn("Nenhuma conta ou API", readme)
        self.assertIn("Simulação offline", readme)
        self.assertIn("nem conecta à VPS", readme)

    def test_parser_would_catch_the_real_missing_five_dependencies(self):
        html = (APP / "index.html").read_text(encoding="utf-8")
        expected = required_local_assets(html)
        incomplete = {"index.html", "style.css", "engine.js", "app.js", "LEIA-ME.txt"}
        self.assertEqual(
            expected - incomplete,
            {"public-market.js", "persisted-paper.js",
             "integrated-paper-cycle.js", "research-scorebook.js",
             "paper-ws-health.js", "paper-watch.js", "resident-paper.js",
             "last-public-paper-lease.js", "prospective-research.js"},
        )
        self.assertNotEqual(expected, incomplete)


if __name__ == "__main__":
    unittest.main()
