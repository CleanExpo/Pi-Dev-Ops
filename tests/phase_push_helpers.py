"""Shared harness for the `_phase_push` auto-PR tests.

Split out of tests/test_phase_push_auto_pr.py when that file crossed the
300-line convention. Nothing here asserts anything — it only stands in for the
boundaries `_phase_push` touches (git, the session emitter, the GitHub API) so
the tests can watch what the real code does with them.
"""
from __future__ import annotations

import json
import types
from pathlib import Path

from app.server import session_phases


TOKEN = "ghs_faketoken0000000000000000000000000000"
REMOTE = "https://github.com/CleanExpo/Pi-Dev-Ops.git"
AUTHED = f"https://x-access-token:{TOKEN}@github.com/CleanExpo/Pi-Dev-Ops.git"


class _Recorder:
    """Collects everything the phase did, so assertions read against one object."""

    def __init__(self) -> None:
        self.cmds: list[tuple[str, ...]] = []
        self.pr_payloads: list[dict] = []
        self.pr_urls: list[str] = []
        self.linear_calls: list[tuple] = []
        self.messages: list[str] = []


def _make_session(tmp_path: Path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "main.py").write_text("print('x')\n")
    return types.SimpleNamespace(
        id="23a6e82e840f0000",
        workspace=str(ws),
        evaluator_score=9,
        evaluator_confidence=88,
    )


def _fake_run_cmd(rec: _Recorder, push_rc: int, diff_out: str):
    """A git that answers only the calls `_phase_push` actually makes."""

    async def run(cwd, *args, timeout=60, env=None):
        rec.cmds.append(args)
        if args[:2] == ("git", "status"):
            return 0, "", ""
        if args[:2] == ("git", "log") and "--oneline" in args:
            return 0, "abc1234 feat: pi ceo build", ""
        if args[:3] == ("git", "remote", "get-url"):
            # After set-url the block must read back the AUTHED url — that is the
            # form the token-stripping line has to cope with.
            seen_set = any(a[:3] == ("git", "remote", "set-url") for a in rec.cmds)
            return 0, (AUTHED if seen_set else REMOTE), ""
        if args[:3] == ("git", "remote", "set-url"):
            return 0, "", ""
        if args[:2] == ("git", "checkout"):
            return 0, "", ""
        if args[0] == "git" and args[1] == "push":
            return push_rc, "", ("" if push_rc == 0 else "remote rejected")
        if args[:3] == ("git", "diff", "--name-only"):
            return 0, diff_out, ""
        if args[:2] == ("git", "log") and "--pretty=%s" in args:
            return 0, "fix(x): the last commit subject", ""
        return 0, "", ""

    return run


def _fake_urlopen(rec: _Recorder, urlopen_raises: bool):
    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"html_url": "https://github.com/CleanExpo/Pi-Dev-Ops/pull/742",
                               "number": 742}).encode()

    def urlopen(req, timeout=15):
        if urlopen_raises:
            raise RuntimeError("422 Unprocessable Entity")
        rec.pr_urls.append(req.full_url)
        rec.pr_payloads.append(json.loads(req.data.decode()))
        return _Resp()

    return urlopen


def _install(monkeypatch, rec: _Recorder, *, push_rc: int = 0, diff_out: str = "app/x.py\n",
             token: str = TOKEN, urlopen_raises: bool = False):
    """Patch every boundary `_phase_push` touches. Assertions read off `rec`."""
    monkeypatch.setattr(session_phases, "run_cmd", _fake_run_cmd(rec, push_rc, diff_out))
    monkeypatch.setattr(session_phases, "em",
                        lambda s, kind, msg="": rec.messages.append(f"{kind}:{msg}"))
    monkeypatch.setattr(session_phases, "_emit_phase_metric",
                        lambda *a, **k: None, raising=False)
    monkeypatch.setattr(session_phases, "_route_linear_ticket_to_target_project",
                        lambda *a: rec.linear_calls.append(a), raising=False)

    async def allows_push(session, run_cmd, em):
        return True

    monkeypatch.setattr(session_phases.board_review, "allows_push", allows_push)
    monkeypatch.setenv("GITHUB_TOKEN", token)

    import urllib.request

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen(rec, urlopen_raises))


async def _run(session, total_phases: int = 6):
    return await session_phases._phase_push(session, total_phases)


class _HostileSession(types.SimpleNamespace):
    """A session whose `pr_url` setter raises, and only that one.

    Not hypothetical. `session` is a live object that other code hangs
    persistence and dashboard hooks off, which is why the pre-extraction code
    wrapped the `pr_url` assignment in its OWN try/except, separate from the
    three RA-7216 attribution keys. Collapsing the two into one try changes
    behaviour precisely here: the keys a merge event needs to find its
    gate_checks row would be skipped because an unrelated assignment failed
    first. Independent review (gemini, P1, session_push_pr.py:72) caught this in
    an extraction whose commit message claimed it was behaviour-preserving.
    """

    @property
    def pr_url(self):
        return getattr(self, "_pr_url", "")

    @pr_url.setter
    def pr_url(self, value):
        raise RuntimeError("persistence hook rejected pr_url")
