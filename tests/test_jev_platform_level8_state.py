"""Level 8 `ask` sends {path, content}; a template declaring any other state is refused before sending.

Found by the Level 9/10 builder: `ask.build_questions` ignored the template `state` field that
PLAN-scale.md rev 5 added, so a `[task, content]` template could be sent in a body with no `task`.
"""
from __future__ import annotations

from jev_scale_support import GOOD, Recorder, budget, make_repo

from jev_platform import ask


def _ask(tmp_path, tids):
    repo = make_repo(tmp_path, {"src/billing.ts": GOOD})
    post = Recorder()
    out = ask.ask_files(repo, ["src/billing.ts"], tids, post, budget())
    return out, post


def test_level8_content_only_template_still_sends(tmp_path):
    out, post = _ask(tmp_path, ["known-issue"])
    assert "blocked" not in out and len(post.calls) == 1


def test_level8_refuses_a_task_template_with_zero_requests(tmp_path):
    out, post = _ask(tmp_path, ["relevant-to-task"])
    assert "reads" in out["blocked"] and "relevant-to-task" in out["blocked"]
    assert post.calls == []


def test_level8_refuses_a_mixed_batch_with_zero_requests(tmp_path):
    out, post = _ask(tmp_path, ["known-issue", "triage-bundle"])
    assert "triage-bundle" in out["blocked"] and post.calls == []
