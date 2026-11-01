"""Ensure CI and handoff run every standalone SDA regression module."""
import fnmatch
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "skills/visual-qa/scripts"
RUNNERS = (".github/workflows/ci.yml", "scripts/handoff-loop.sh")
DISCOVERY = r"""-m unittest discover -s skills/visual-qa/scripts -p ['"]([^'"]+)['"]"""


class SdaDiscoveryCoverageTests(unittest.TestCase):
    def test_ci_and_handoff_collect_every_sda_module(self):
        modules = {p.name for p in SOURCE.glob("test_sda_*.py")}
        self.assertIn("test_sda_review_p2_r17.py", modules)
        for runner in RUNNERS:
            with self.subTest(runner=runner):
                body = (ROOT / runner).read_text()
                patterns = re.findall(DISCOVERY, body)
                self.assertEqual(len(patterns), 1, patterns)
                discovered = {
                    name for name in modules
                    if fnmatch.fnmatchcase(name, patterns[0])
                }
                self.assertEqual(discovered, modules)


if __name__ == "__main__":
    unittest.main()
