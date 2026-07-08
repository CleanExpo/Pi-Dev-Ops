"""RA-7015 provisioning gate — unit + red-team + stress coverage.

Golden acceptance (from the Judge Report loop/stress plan):
  * banned token in a scanned surface -> gate fails
  * clean tree -> gate passes
  * banned token under an excluded folder -> NOT flagged (design-system false positive)
  * reconciliation is report-only unless --strict
  * the real repo tree passes on day one (regression guard)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import check_provisioning as cp  # noqa: E402

_SSOT = {
    "version": 1,
    "provisioned": [
        {"name": "anthropic", "aliases": ["claude"]},
        {"name": "artlist"},
    ],
    "banned": [
        {"name": "higgsfield", "reason": "use Artlist"},
        {"name": "zapier", "reason": "no workflow tool"},
        {"name": "blotato", "reason": "decide posting first"},
    ],
    "scan": {
        "include": ["skills/**/*.md", "agentskills.json"],
        "exclude": ["remotion-studio/**"],
    },
}


@pytest.fixture()
def fake_repo(tmp_path: Path) -> Path:
    """A minimal repo root with the test SSOT and an empty skills dir."""
    harness = tmp_path / ".harness"
    harness.mkdir(parents=True)
    (harness / "provisioned-tools.yaml").write_text(yaml.safe_dump(_SSOT), encoding="utf-8")
    (tmp_path / "skills" / "demo").mkdir(parents=True)
    return tmp_path


def _ssot(fake_repo: Path) -> cp.Ssot:
    return cp.load_ssot(fake_repo / ".harness" / "provisioned-tools.yaml")


def test_load_ssot_normalises(fake_repo: Path) -> None:
    ssot = _ssot(fake_repo)
    assert ssot.provisioned == {"anthropic", "artlist"}
    assert ssot.aliases == {"claude": "anthropic"}
    assert set(ssot.banned) == {"higgsfield", "zapier", "blotato"}


def test_clean_tree_passes(fake_repo: Path) -> None:
    (fake_repo / "skills" / "demo" / "SKILL.md").write_text(
        "Uses Anthropic and Artlist only.", encoding="utf-8"
    )
    assert cp.scan_banned(_ssot(fake_repo), root=fake_repo) == []


def test_banned_token_is_flagged(fake_repo: Path) -> None:
    (fake_repo / "skills" / "demo" / "SKILL.md").write_text(
        "Generate video via Higgsfield.", encoding="utf-8"
    )
    hits = cp.scan_banned(_ssot(fake_repo), root=fake_repo)
    assert len(hits) == 1
    rel, line_no, name, reason = hits[0]
    assert name == "higgsfield" and line_no == 1
    assert "Artlist" in reason


def test_case_insensitive_and_apostrophe_boundary(fake_repo: Path) -> None:
    (fake_repo / "skills" / "demo" / "SKILL.md").write_text(
        "post via ZAPIER; also Blotato's API", encoding="utf-8"
    )
    names = {h[2] for h in cp.scan_banned(_ssot(fake_repo), root=fake_repo)}
    assert names == {"zapier", "blotato"}


def test_substring_does_not_false_positive(fake_repo: Path) -> None:
    # word-boundary: 'zapiered' must not trip the 'zapier' rule
    (fake_repo / "skills" / "demo" / "SKILL.md").write_text(
        "the workflow was zapiered together", encoding="utf-8"
    )
    assert cp.scan_banned(_ssot(fake_repo), root=fake_repo) == []


def test_excluded_folder_is_not_scanned(fake_repo: Path) -> None:
    # A banned token in a design-system folder must NOT trip the gate.
    ds = fake_repo / "remotion-studio" / "src" / "_library" / "zapier"
    ds.mkdir(parents=True)
    ssot = _ssot(fake_repo)
    ssot.include.append("remotion-studio/**/*.md")
    (ds / "DESIGN.md").write_text("The 'Zapier' visual style.", encoding="utf-8")
    assert cp.scan_banned(ssot, root=fake_repo) == []


def test_reconciliation_dormant_when_no_declarations(fake_repo: Path) -> None:
    (fake_repo / "agentskills.json").write_text(
        json.dumps({"skills": [{"id": "a", "dependencies": {"tools": []}}]}),
        encoding="utf-8",
    )
    declared, offenders = cp.reconcile_declarations(_ssot(fake_repo), root=fake_repo)
    assert declared == 0 and offenders == []


def test_reconciliation_flags_unprovisioned_declaration(fake_repo: Path) -> None:
    (fake_repo / "agentskills.json").write_text(
        json.dumps(
            {
                "skills": [
                    {"id": "vid", "dependencies": {"tools": ["kling"]}},
                    {"id": "ok", "dependencies": {"tools": ["claude", "artlist"]}},
                ]
            }
        ),
        encoding="utf-8",
    )
    declared, offenders = cp.reconcile_declarations(_ssot(fake_repo), root=fake_repo)
    assert declared == 3
    assert offenders == ["vid -> kling"]


def test_main_exit_codes(fake_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cp, "REPO_ROOT", fake_repo)
    monkeypatch.setattr(cp, "SSOT_PATH", fake_repo / ".harness" / "provisioned-tools.yaml")
    (fake_repo / "skills" / "demo" / "SKILL.md").write_text("Anthropic only.", encoding="utf-8")
    assert cp.main([]) == 0
    (fake_repo / "skills" / "demo" / "SKILL.md").write_text("via Higgsfield", encoding="utf-8")
    assert cp.main([]) == 1


def test_real_repo_tree_passes_today() -> None:
    """Regression guard: the live repo must be clean on day one, else the
    gate can never merge."""
    ssot = cp.load_ssot()
    assert cp.scan_banned(ssot) == []
