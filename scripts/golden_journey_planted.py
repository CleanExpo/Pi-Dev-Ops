"""UNI-2652 planted failure — kill mid-claim and prove recovery.

Local, no Claude, no prod. A first machine claims an interrupted session,
is killed before it can finish, and a second machine must be the only one
that can resume after the lease expires. The killed run must not report PASS.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote


@dataclass
class PlantedProof:
    worktree_retained: bool = False
    claim_released_after_expiry: bool = False
    second_machine_resumed: bool = False
    no_duplicate_claim: bool = False
    no_false_green: bool = False
    errors: list[str] = field(default_factory=list)

    def all_passed(self) -> bool:
        return (
            self.worktree_retained
            and self.claim_released_after_expiry
            and self.second_machine_resumed
            and self.no_duplicate_claim
            and self.no_false_green
            and not self.errors
        )


class LeaseTable:
    """In-process stand-in for the sessions claim PATCH (same filter as prod)."""

    def __init__(self, rows: list[dict]) -> None:
        self.rows = {r["id"]: dict(r) for r in rows}

    def request(self, method, path, body=None, prefer="return=minimal"):
        if method != "PATCH":
            return 200, None
        hit = [r for r in self.rows.values() if _matches(r, path)]
        for row in hit:
            row.update(body or {})
        return 200, [dict(r) for r in hit] if "representation" in prefer else None


def run_planted_failure(root: Path) -> PlantedProof:
    """Kill the first claimant mid-work and prove the five recovery facts."""
    from app.server import session_lease, supabase_log

    proof = PlantedProof()
    worktree = _make_worktree(root)
    table = LeaseTable([_interrupted_row("s1")])
    orig_cfg, orig_req = supabase_log._cfg, supabase_log._request
    supabase_log._cfg = lambda: ("https://x.supabase.co", "svc-key")  # type: ignore[method-assign]
    supabase_log._request = table.request  # type: ignore[method-assign]
    try:
        _drive_planted(proof, table, worktree, session_lease)
    finally:
        supabase_log._cfg, supabase_log._request = orig_cfg, orig_req
    return proof


def _drive_planted(proof: PlantedProof, table: LeaseTable, worktree: Path, lease) -> None:
    if not lease.claim_interrupted_session("s1", "machine-a", lease_minutes=10):
        proof.errors.append("machine-a failed to claim")
        return
    proof.no_false_green = _kill_mid_claim(worktree) != "PASS"
    proof.worktree_retained = _worktree_alive(worktree)
    if not proof.worktree_retained:
        proof.errors.append(f"worktree lost after kill: {worktree}")
    table.rows["s1"]["lease_expires_at"] = _past()
    proof.claim_released_after_expiry = lease.claim_interrupted_session(
        "s1", "machine-b", lease_minutes=10
    )
    proof.second_machine_resumed = (
        proof.claim_released_after_expiry and table.rows["s1"]["claimed_by"] == "machine-b"
    )
    third = lease.claim_interrupted_session("s1", "machine-c", lease_minutes=10)
    proof.no_duplicate_claim = third is False and table.rows["s1"]["claimed_by"] == "machine-b"
    if not proof.all_passed():
        proof.errors.append(_summarise(proof))


def _make_worktree(root: Path) -> Path:
    repo = root / "origin"
    repo.mkdir(parents=True)
    wt = root / "worktree"
    _git(repo, "init", "-b", "main")
    (repo / "README").write_text("golden-journey planted failure\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "init")
    _git(repo, "worktree", "add", str(wt), "-b", "claim/s1")
    return wt


def _kill_mid_claim(worktree: Path) -> str:
    """Start a dummy runner in the worktree and SIGKILL it before it can print PASS."""
    marker = worktree / "CLAIMED"
    script = (
        "import pathlib, time, sys\n"
        f"pathlib.Path({str(marker)!r}).write_text('claimed\\n')\n"
        "time.sleep(30)\n"
        "print('PASS')\n"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", script],
        cwd=str(worktree),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    _wait_for(marker)
    proc.kill()
    out, _err = proc.communicate(timeout=5)
    return "PASS" if "PASS" in (out or "") else "KILLED"


def _worktree_alive(worktree: Path) -> bool:
    if not worktree.is_dir():
        return False
    return (worktree / "README").is_file() and (worktree / ".git").exists()


def _interrupted_row(sid: str) -> dict:
    return {"id": sid, "status": "interrupted", "claimed_by": None, "lease_expires_at": None}


def _past() -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat(timespec="seconds")


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _wait_for(path: Path, timeout_s: float = 5.0) -> None:
    deadline = datetime.now(timezone.utc).timestamp() + timeout_s
    while datetime.now(timezone.utc).timestamp() < deadline:
        if path.exists():
            return
        time.sleep(0.05)
    raise FileNotFoundError(f"runner never claimed {path}")


def _matches(row: dict, query: str) -> bool:
    sid = re.search(r"id=eq\.([^&]+)", query)
    if sid and row["id"] != sid.group(1):
        return False
    status = re.search(r"status=eq\.([^&]+)", query)
    if status and row.get("status") != status.group(1):
        return False
    or_clause = re.search(r"or=\(claimed_by\.is\.null,lease_expires_at\.lt\.([^)]+)\)", query)
    if not or_clause:
        return True
    if row.get("claimed_by") is None:
        return True
    expiry = row.get("lease_expires_at")
    if not expiry:
        return False
    cutoff = datetime.fromisoformat(unquote(or_clause.group(1)))
    return datetime.fromisoformat(expiry) < cutoff


def _summarise(proof: PlantedProof) -> str:
    flags = {
        "worktree_retained": proof.worktree_retained,
        "claim_released_after_expiry": proof.claim_released_after_expiry,
        "second_machine_resumed": proof.second_machine_resumed,
        "no_duplicate_claim": proof.no_duplicate_claim,
        "no_false_green": proof.no_false_green,
    }
    return json.dumps(flags)
