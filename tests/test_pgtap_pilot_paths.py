"""pgtap-pilot.yml runs only for PRs that touch its `paths`, so every test file a step
runs must be listed there, or a change to that test alone never runs the job
(UNI-3306 review round 1: tests/test_goal_analysis_jobs_pg.py was run but not listed)."""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "pgtap-pilot.yml"


def _paths_and_run_files(text: str) -> tuple[list[str], set[str]]:
    block = text.split("pull_request:", 1)[1].split("\n  push:", 1)[0]
    paths = re.findall(r"^\s+- '([^']+)'", block, flags=re.M)
    run_files = set(re.findall(r"(?:tests|supabase/tests)/[\w./-]+\.(?:py|sql)", text.split("\njobs:", 1)[1]))
    return paths, run_files


def test_every_test_file_the_job_runs_triggers_the_job():
    paths, run_files = _paths_and_run_files(WORKFLOW.read_text(encoding="utf-8"))
    assert paths, "no pull_request paths parsed"
    assert run_files, "no test files parsed from the job steps"
    missing = sorted(f for f in run_files if not any(fnmatch.fnmatch(f, p.replace("**", "*")) for p in paths))
    assert missing == [], f"run by pgtap-pilot but not in its pull_request paths: {missing}"


def test_the_check_detects_an_unlisted_test_file():
    text = WORKFLOW.read_text(encoding="utf-8").replace("      - 'tests/test_goal_analysis_jobs_pg.py'\n", "")
    paths, run_files = _paths_and_run_files(text)
    assert "tests/test_goal_analysis_jobs_pg.py" in run_files
    assert not any(fnmatch.fnmatch("tests/test_goal_analysis_jobs_pg.py", p.replace("**", "*")) for p in paths)
