"""secrets_check: hyphenated "your-key-here" placeholders are suppressed; a real-looking value is not.

The vendored TypeSafe docs (docs/vendor/typesafe/llms-full.txt) carry
`export TYPESAFE_API_KEY="your-key-here"`. The placeholder rule only knew the underscore form
(`YOUR_..._HERE`), so the handoff gate reported a secret that is a documentation placeholder.
The positive control proves the same line with a realistic value still fires.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "secrets_check.py"
# Invented, non-functional value; avoids the placeholder vocabulary on purpose.
REALISTIC = "k7Qm2Rv9Xp4Lw8Zt3Nb6Yc1Hd5Fj0GsTq"


def _scan_line(tmp_path: Path, line: str) -> subprocess.CompletedProcess[str]:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "setup.txt").write_text(line + "\n", encoding="utf-8")
    return subprocess.run([sys.executable, str(SCRIPT), "--repo-root", str(tmp_path), "--dry-run"],
                          text=True, capture_output=True, check=False)


def test_realistic_value_on_the_same_line_still_fires(tmp_path: Path) -> None:
    out = _scan_line(tmp_path, f'export TYPESAFE_API_KEY="{REALISTIC}"')
    assert out.returncode != 0, out.stdout[-400:]


def test_hyphenated_your_key_here_placeholder_is_suppressed(tmp_path: Path) -> None:
    out = _scan_line(tmp_path, 'export TYPESAFE_API_KEY="your-key-here"')
    assert out.returncode == 0, out.stdout[-400:]


def test_unquoted_hyphenated_placeholder_is_suppressed(tmp_path: Path) -> None:
    out = _scan_line(tmp_path, "export ANTHROPIC_API_KEY=your-key-here")
    assert out.returncode == 0, out.stdout[-400:]
