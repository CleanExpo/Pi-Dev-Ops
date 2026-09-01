"""tests/test_mesh_runner_claim_reporting.py — a claim the runner cannot work
must be reported, not silently dropped (RA-7394).

`run_claim()` resolves a repo directory, then bails when it has no `.git`. That
branch used to `return` a `state: failed` dict **without telling the server**,
unlike the `git worktree add failed` branch eleven lines below it, which POSTs
`/api/mesh/claim/update` first. `main()` does not compensate — it only prints
the returned dicts.

The cost is not a lost log line. The claim stays `claimed` in
`mesh_work_claims`, so:

  * `_reap_stale_claims()` skips it — it deliberately leaves claims alone while
    the claiming machine's heartbeat is fresh, and the machine IS heartbeating,
    because `bootstrap.sh` installs the heartbeat daemon beside the runner.
  * the `mesh_work_claims_one_open` partial unique index then stops every other
    node claiming that ticket.
  * `get_work()` -> `my_claims()` re-reads the same `claimed` ticket next pass
    and fails it again, forever.

So a ticket is taken out of the pool, never worked, never reported, and locked
away from the rest of the fleet — while `/api/mesh/fleet` lists it under
`claims[]` as work in progress.

WHY THIS FILE IS SEPARATE: `tests/test_mesh_runner_idle_autoclaim.py` owns the
loop harness, and it sits exactly on its 539-line size-gate baseline, so it
cannot grow. The harness here is deliberately small — these tests need one
claim and one bounded loop, not the full fake fleet.

NOTHING HERE MAY HANG. There is no pytest-timeout in this repo, so a regression
must fail fast rather than wedge CI. The loop test caps `MAX_CLAIMS`, which
turns "retries forever" into a clean `DID NOT RAISE` instead of a hang.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


from mesh_helpers import Break as _Break  # noqa: E402
from mesh_helpers import ImmediateProc as _DoneProc  # noqa: E402
from mesh_helpers import load_module as _load  # noqa: E402


class FakeServer:
    """The three `/api/mesh/*` calls `run_claim` and `get_work` actually make."""

    def __init__(self, queue=(), repo_dir=None):
        """`queue` is the pool `claim/self` hands out, top-priority first.

        `repo_dir`, when given, is attached to each handed-out claim the way the
        dispatcher attaches one, so tests can exercise the explicit path rather
        than the module-level default.
        """
        self.queue = list(queue)
        self.repo_dir = repo_dir
        self.claims: dict[str, str] = {}
        self.calls: list[tuple[str, str, dict]] = []

    def api(self, method, path, body=None):
        """Stand in for `_api`, recording every call so reporting is assertable."""
        self.calls.append((method, path, body or {}))
        if path == "/api/mesh/fleet":
            rows = [{"linear_id": k, "machine": "TESTNODE", "state": v}
                    for k, v in self.claims.items() if v in ("claimed", "working")]
            if self.repo_dir:
                for row in rows:
                    row["repo_dir"] = self.repo_dir
            return {"claims": rows, "agents": []}
        if path == "/api/mesh/claim/self":
            if not self.queue:
                return {"claimed": None}
            lid = self.queue.pop(0)
            self.claims[lid] = "claimed"
            claim = {"linear_id": lid, "machine": "TESTNODE"}
            if self.repo_dir:
                claim["repo_dir"] = self.repo_dir
            return {"claimed": claim}
        if path == "/api/mesh/claim/update":
            self.claims[body["linear_id"]] = body["state"]
            return {"ok": True}
        return {}

    def reported(self, linear_id: str) -> list[str]:
        """Every state this ticket was reported as, in order."""
        return [b["state"] for _, p, b in self.calls
                if p == "/api/mesh/claim/update" and b.get("linear_id") == linear_id]


@pytest.fixture
def runner(monkeypatch, tmp_path):
    """The runner module with every side effect neutralised except reporting."""
    # Same hermeticity RA-7370 needed next door: DEFAULT_REPO_DIR is read at
    # module scope, so an ambient MESH_REPO_DIR would both redirect every claim
    # and trip RA-7375's startup guard before any loop test could run.
    monkeypatch.delenv("MESH_REPO_DIR", raising=False)
    mod = _load("mesh_runner_reporting", "mesh/runner.py")
    monkeypatch.setattr(mod, "HOST", "TESTNODE")
    monkeypatch.setattr(mod, "HARD_STOP", tmp_path / "HARD_STOP")
    monkeypatch.setattr(mod, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(mod, "MAX_PARALLEL", 4)
    monkeypatch.setattr(mod, "IDLE_RECLAIM_DELAY", 0)
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: None)
    return mod


def _no_git(tmp_path) -> str:
    """A real directory that is not a git checkout — the condition under test."""
    d = tmp_path / "not-a-checkout"
    d.mkdir()
    assert not (d / ".git").exists()
    return str(d)


# ── the regression ───────────────────────────────────────────────────────────


def test_a_repo_missing_claim_is_reported_failed_to_the_server(runner, tmp_path):
    """THE REGRESSION TEST.

    Returning `state: failed` to the caller is not reporting. Until this POST
    lands, the server still believes the ticket is claimed and being worked.
    """
    server = FakeServer()
    server.claims["UNI-A"] = "claimed"
    runner._api = server.api

    plan = runner.run_claim({"linear_id": "UNI-A", "repo_dir": _no_git(tmp_path)},
                            dry_run=False)

    assert plan["state"] == "failed"
    assert server.reported("UNI-A") == ["failed"], server.calls
    assert server.claims["UNI-A"] == "failed"


def test_a_reported_failure_frees_the_ticket_for_another_node(runner, tmp_path):
    """The point of reporting: `mesh_work_claims_one_open` covers only
    `claimed`/`working`, so `failed` is what releases the ticket. A claim left
    `claimed` is invisible to the reaper too, because that skips machines whose
    heartbeat is fresh — and a runner failing this way is very much alive."""
    server = FakeServer()
    server.claims["UNI-A"] = "claimed"
    runner._api = server.api

    runner.run_claim({"linear_id": "UNI-A", "repo_dir": _no_git(tmp_path)}, dry_run=False)

    still_open = [c["linear_id"] for c in server.api("GET", "/api/mesh/fleet")["claims"]]
    assert still_open == []


def test_the_runner_does_not_retry_a_repo_missing_ticket_forever(runner, monkeypatch, tmp_path):
    """The loop must drain rather than re-serve the same doomed ticket.

    `get_work()` -> `my_claims()` returns any ticket still `claimed` for this
    host, so an unreported failure comes straight back next pass. Bounded by
    MAX_CLAIMS so a regression ends as `DID NOT RAISE` rather than hanging CI —
    there is no pytest-timeout here.

    The doomed path is now an EXPLICIT `repo_dir` on the claim, not the default.
    RA-7375's startup guard refuses to run at all when DEFAULT_REPO_DIR is not a
    checkout of this project, so that route can no longer reach the loop — but a
    server-assigned `repo_dir` bypasses the guard by design, and remains the
    reachable way for `run_claim` to meet a directory with no `.git`.
    """
    bad = _no_git(tmp_path)
    server = FakeServer(queue=["UNI-A"], repo_dir=bad)
    runner._api = server.api
    monkeypatch.setattr(runner, "MAX_CLAIMS", 6)

    def _sleep(_seconds):
        """End the loop at its first poll sleep, which it only reaches once the
        queue has drained — so reaching here IS the assertion that it drained."""
        raise _Break

    monkeypatch.setattr(runner.time, "sleep", _sleep)
    monkeypatch.setattr(sys, "argv", ["runner"])

    with pytest.raises(_Break):
        runner.main()

    assert server.reported("UNI-A") == ["failed"], server.calls


# ── green control ────────────────────────────────────────────────────────────


def test_a_working_repo_reports_the_full_working_then_done_sequence(runner, tmp_path, monkeypatch):
    """GREEN CONTROL. A fix that reported `failed` unconditionally, or that
    refused every claim, would satisfy all three tests above while breaking
    every real run.

    Raised by CodeRabbit: this asserted only `reported(...)[0] == "working"`,
    and the claim was in fact ending `failed`. `subprocess.Popen` was left
    unstubbed, so it tried to spawn the agent with `cwd` set to a worktree that
    was never created, raised, and landed in run_claim's except branch. The
    real sequence was `["working", "failed"]` — the test passed by looking only
    at the first element, so a green control was itself green for the wrong
    reason.

    Stubbing the agent process makes the happy path complete, and the whole
    sequence is asserted so the ending cannot drift unnoticed again.
    """
    repo = tmp_path / "checkout"
    (repo / ".git").mkdir(parents=True)
    server = FakeServer()
    server.claims["UNI-A"] = "claimed"
    runner._api = server.api
    monkeypatch.setattr(runner.subprocess, "Popen", lambda *a, **k: _DoneProc())

    plan = runner.run_claim({"linear_id": "UNI-A", "repo_dir": str(repo)}, dry_run=False)

    assert plan["state"] == "done", plan
    assert server.reported("UNI-A") == ["working", "done"], server.calls
