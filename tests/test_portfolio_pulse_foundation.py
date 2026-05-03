"""tests/test_portfolio_pulse_foundation.py — RA-1888.

Coverage:
  * build_pulse() emits a markdown file with all 6 sections
  * run_all_projects() iterates DEFAULT_PROJECTS without raising on
    missing data / unwired section providers
  * set_section_provider() replaces the default unwired placeholder
  * Section provider that raises is captured into PulseSection.error
    without breaking the rest of the pulse
  * Cron trigger registration: portfolio-pulse-daily exists with
    type=portfolio_pulse
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from swarm import portfolio_pulse  # noqa: E402


def test_build_pulse_writes_markdown(tmp_path):
    """One project's pulse renders all 6 sections into a markdown file."""
    result = portfolio_pulse.build_pulse(
        "pi-ceo", repo_root=tmp_path, date="2026-05-03",
    )
    assert result.error is None
    assert result.output_path is not None
    assert result.output_path.exists()
    assert result.output_path.name == "2026-05-03.md"
    body = result.output_path.read_text(encoding="utf-8")
    assert "# pi-ceo — Portfolio Pulse 2026-05-03" in body
    for heading in (
        "## Deploys (last 24h)",
        "## CI state",
        "## Open PRs",
        "## Linear movement",
        "## Revenue & cost",
        "## Risks & flags",
    ):
        assert heading in body, f"missing section heading {heading!r}"


def test_run_all_projects_iterates_defaults(tmp_path):
    """run_all_projects covers all 7 default projects without raising."""
    results = portfolio_pulse.run_all_projects(repo_root=tmp_path)
    assert len(results) == len(portfolio_pulse.DEFAULT_PROJECTS)
    for r in results:
        assert r.project_id in portfolio_pulse.DEFAULT_PROJECTS
        assert r.error is None
        assert r.output_path is not None
        assert r.output_path.exists()


def test_set_section_provider_replaces_default(tmp_path):
    """Sibling-child wiring path: register a real provider, see it run."""
    sentinel_body = "REAL_DEPLOY_DATA_HERE"

    def real_provider(project_id, repo_root):
        return (sentinel_body, None)

    # Snapshot + restore so this test doesn't leak state to others
    original = portfolio_pulse._SECTION_PROVIDERS["deploys"]
    portfolio_pulse.set_section_provider("deploys", real_provider)
    try:
        result = portfolio_pulse.build_pulse(
            "pi-ceo", repo_root=tmp_path, date="2026-05-03",
        )
    finally:
        portfolio_pulse.set_section_provider("deploys", original)

    deploys = next(s for s in result.sections if s.name == "deploys")
    assert deploys.body_md == sentinel_body
    assert deploys.error is None


def test_section_provider_error_captured(tmp_path):
    """When a provider raises, the section captures the error but the
    rest of the pulse still renders + the file still writes."""
    def bad_provider(project_id, repo_root):
        raise RuntimeError("provider boom")

    original = portfolio_pulse._SECTION_PROVIDERS["deploys"]
    portfolio_pulse.set_section_provider("deploys", bad_provider)
    try:
        result = portfolio_pulse.build_pulse(
            "pi-ceo", repo_root=tmp_path, date="2026-05-03",
        )
    finally:
        portfolio_pulse.set_section_provider("deploys", original)

    assert result.error is None  # pulse-level OK
    assert result.output_path and result.output_path.exists()
    deploys = next(s for s in result.sections if s.name == "deploys")
    assert deploys.error == "provider boom"
    # Other sections still ran — they all produced a body, even if some
    # captured graceful errors of their own (real providers like
    # linear_movement legitimately error in CI without LINEAR_API_KEY).
    others = [s for s in result.sections if s.name != "deploys"]
    assert all(s.body_md for s in others), "every other section must render a body"


def test_cron_trigger_registered():
    """The portfolio-pulse-daily cron trigger is registered in the
    canonical .harness/cron-triggers.json."""
    triggers_path = REPO_ROOT / ".harness" / "cron-triggers.json"
    triggers = json.loads(triggers_path.read_text(encoding="utf-8"))
    by_id = {t.get("id"): t for t in triggers}
    assert "portfolio-pulse-daily" in by_id, (
        "portfolio-pulse-daily trigger not registered in cron-triggers.json"
    )
    pp = by_id["portfolio-pulse-daily"]
    assert pp.get("type") == "portfolio_pulse"
    assert pp.get("hour") == 20  # 06:00 AEST
    assert pp.get("minute") == 0
    assert pp.get("enabled", True) is True


def test_render_markdown_includes_generated_timestamp(tmp_path):
    """Rendered markdown contains a Generated <ISO> timestamp comment."""
    result = portfolio_pulse.build_pulse(
        "pi-ceo", repo_root=tmp_path, date="2026-05-03",
    )
    body = result.output_path.read_text(encoding="utf-8")
    assert "_Generated" in body
