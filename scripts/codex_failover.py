#!/usr/bin/env python3
"""Codex review failover: a dead Mini Codex login hands the review to the MacBook (RA-8191, AR-05).

`review` runs one Codex review brief on this machine (the Mini). If the Codex login here is
dead, it appends a HEADROOM `auth_expired` event (AR-02) so the picker (AR-03) holds the Mini,
then runs the same brief on the MacBook against the same commit, carried over ssh as a bundle.

It only detects. It never signs in or out (`guard` refuses any such command), never reads a
token value, never falls back to an API key, and never touches the MacBook's own checkout.

A dead login is told apart from every other failure like this:
- auth.json missing, unreadable, or not ChatGPT plan auth: dead before anything runs.
- Otherwise a run that wrote a final model message authenticated, whatever it printed.
- With no final message, a line STARTING with a known HEADROOM auth string
  (`unexpected status 401 Unauthorized`, `workspace is out of credits`) is a dead login.
Quota and every other failure are not auth: no failover, exit 1.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import headroom_events as he  # noqa: E402

REMOTE_HOST = os.environ.get("CODEX_FAILOVER_HOST", "macbook")  # ~/.ssh/config alias
REMOTE_BASE = "agent-work/codex-failover"  # under the MacBook home; never ~/Pi-Dev-Ops
REMOTE_PATH = 'PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"'
SSH = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15"]
CODEX_EXEC = ["codex", "exec", "--skip-git-repo-check", "--sandbox", "workspace-write"]
REVIEW_TIMEOUT_S = 3600
EXIT_OK, EXIT_REVIEW_FAILED, EXIT_USAGE, EXIT_AUTH_FAILED = 0, 1, 2, 3
EXIT_FAILOVER_UNAVAILABLE, EXIT_BOTH_DOWN = 4, 5
_SHA = re.compile(r"^[0-9a-f]{40}$")
_SIGN_IN = re.compile(r"\bcodex\s+(?:log(?:in|out))\b|^log(?:in|out)$")

Run = Callable[..., tuple]  # (argv, stdin=bytes|None, cwd=str|None, timeout=s) -> (rc, stdout, stderr)


class ForbiddenCommand(RuntimeError):
    """A sign-in or sign-out reached the runner. Re-auth is human-only (RA-8191)."""


def guard(argv: list[str]) -> None:
    """Refuse any command that would sign Codex in or out, locally or inside an ssh string."""
    words = [str(a) for a in argv]
    if words and Path(words[0]).name == "codex" and any(_SIGN_IN.search(w) for w in words[1:2]):
        raise ForbiddenCommand("codex sign-in/out is human-only")
    if any(_SIGN_IN.search(w) and " " in w for w in words):
        raise ForbiddenCommand("codex sign-in/out is human-only")


def subprocess_run(argv, stdin=None, cwd=None, timeout=None) -> tuple:
    guard(argv)
    try:
        p = subprocess.run(argv, input=stdin, cwd=cwd, capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        return (255, b"", type(e).__name__.encode())
    return (p.returncode, p.stdout, p.stderr)


def _codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")


def auth_file_state(home: Optional[Path] = None) -> str:
    """ok | missing | unreadable | not_chatgpt. Reads the mode only; never a token value."""
    path = (home or _codex_home()) / "auth.json"
    if not path.is_file():
        return "missing"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "unreadable"
    if not isinstance(data, dict):
        return "unreadable"
    return "ok" if data.get("auth_mode") == "chatgpt" and not data.get("OPENAI_API_KEY") else "not_chatgpt"


def detect(transcript: str, last_message: str, auth_state: str, now: float) -> dict:
    """{status: ok|auth_failed|failed, pattern_id}. Pure."""
    if auth_state != "ok":
        return {"status": "auth_failed", "pattern_id": "codex.auth_file"}
    if last_message.strip():
        return {"status": "ok", "pattern_id": None}
    for hit in he.classify(transcript, "codex", now):
        if hit["event"] == "auth_expired":
            return {"status": "auth_failed", "pattern_id": hit["pattern_id"]}
    return {"status": "failed", "pattern_id": None}


def _text(b) -> str:
    return (b or b"").decode("utf-8", "replace")


def run_local(brief: bytes, repo: Path, out: Path, run: Run) -> tuple:
    """Run the brief with Codex here. Returns (rc, transcript, last_message)."""
    last = Path(str(out) + ".last.md")
    last.unlink(missing_ok=True)
    rc, so, se = run([*CODEX_EXEC, "--output-last-message", str(last), "-"], stdin=brief,
                     cwd=str(repo), timeout=REVIEW_TIMEOUT_S)
    transcript = _text(so) + _text(se)
    out.write_text(transcript, encoding="utf-8")
    return rc, transcript, last.read_text(encoding="utf-8", errors="replace") if last.is_file() else ""


def record(machine: str, hit: dict, job: Optional[str], rc: Optional[int], now: float) -> str:
    """Append one HEADROOM auth_expired record. Never raises: a missing log must not stop the review."""
    rec = he.build_record({"event": "auth_expired", "pattern_id": hit["pattern_id"],
                           "source": "observed", "reset_at": None},
                          machine=machine, provider="codex", job=job, exit_code=rc, now=now)
    try:
        he.append_events([rec], Path(os.environ.get("HEADROOM_LOG") or he.DEFAULT_LOG))
    except OSError as e:
        return f"failed: {type(e).__name__}"
    return "written"


def _ssh(run: Run, cmd: str, stdin: Optional[bytes] = None, timeout: int = 600) -> tuple:
    # stdin b"" when there is no data, so ssh never reads the caller's own stdin.
    return run([*SSH, REMOTE_HOST, cmd], stdin=b"" if stdin is None else stdin, timeout=timeout)


def _stage_remote(repo: Path, head: str, brief: bytes, rdir: str, run: Run) -> str:
    """Copy the commit and brief to a fresh MacBook folder. '' on success, else a reason."""
    rc, bundle, _ = run(["git", "-C", str(repo), "bundle", "create", "-", "HEAD"], timeout=600)
    if rc != 0 or not bundle:
        return "bundle_failed"
    q = shlex.quote(rdir)
    steps = [(f"mkdir -p {q} && cat > {q}/head.bundle", bundle), (f"cat > {q}/brief.md", brief)]
    for cmd, data in steps:
        if _ssh(run, cmd, data)[0] != 0:
            return "transport_failed"
    rc, so, _ = _ssh(run, f"cd {q} && git init -q repo && git -C repo fetch -q ../head.bundle HEAD"
                          f" && git -C repo checkout -q --detach {head} && git -C repo rev-parse HEAD")
    if rc == 255:
        return "transport_failed"
    return "" if rc == 0 and _text(so).strip() == head else "head_mismatch"


def run_remote(repo: Path, head: str, brief: bytes, job: str, run: Run, now: float) -> tuple:
    """(status, rc, transcript, last). status: ok|failed|auth_failed|transport_failed|head_mismatch|..."""
    rdir = f"{REMOTE_BASE}/{job}-{head[:12]}-{int(now)}"
    why = _stage_remote(repo, head, brief, rdir, run)
    if why:
        return why, None, "", ""
    q = shlex.quote(rdir)
    rc, so, se = _ssh(run, f"cd {q}/repo && {REMOTE_PATH} {' '.join(CODEX_EXEC)}"
                           f" --output-last-message ../last.md - < ../brief.md", timeout=REVIEW_TIMEOUT_S)
    if rc == 255:
        return "transport_failed", rc, "", ""
    last = _text(_ssh(run, f"cat {q}/last.md 2>/dev/null; true")[1])
    transcript = _text(so) + _text(se)
    return detect(transcript, last, "ok", now)["status"], rc, transcript, last


def _safe_job(job: Optional[str]) -> str:
    j = he._job_id(job)
    return j if j and re.fullmatch(r"[A-Z]{2,10}-\d{1,6}", j) else "adhoc"


def _failover(repo, head, brief, out, job, run, now, summary) -> int:
    status, rc, transcript, last = run_remote(repo, head, brief, job, run, now)
    summary["macbook"] = status
    if status in ("ok", "failed"):
        out.write_text(transcript, encoding="utf-8")
        Path(str(out) + ".last.md").write_text(last, encoding="utf-8")
        summary["lane"] = "macbook"
        return EXIT_OK if status == "ok" else EXIT_REVIEW_FAILED
    if status == "auth_failed":
        hit = detect(transcript, last, "ok", now)
        summary["headroom"]["macbook"] = record("macbook", hit, None if job == "adhoc" else job, rc, now)
        return EXIT_BOTH_DOWN
    return EXIT_FAILOVER_UNAVAILABLE


def review(*, brief: Path, out: Path, repo: Path, job: Optional[str], run: Run = subprocess_run,
           now: Optional[float] = None) -> tuple[int, dict]:
    now = time.time() if now is None else now
    rc, so, _ = run(["git", "-C", str(repo), "rev-parse", "HEAD"])
    head = _text(so).strip()
    if rc != 0 or not _SHA.match(head):
        return EXIT_USAGE, {"error": "repo HEAD unreadable"}
    data, job = brief.read_bytes(), _safe_job(job)
    summary: dict = {"head": head, "job": job, "lane": None, "headroom": {}}
    state = auth_file_state()
    lrc, transcript, last = run_local(data, repo, out, run) if state == "ok" else (None, "", "")
    hit = detect(transcript, last, state, now)
    summary["mini"] = hit["status"]
    if hit["status"] != "auth_failed":
        summary["lane"] = "mini"
        return (EXIT_OK if hit["status"] == "ok" else EXIT_REVIEW_FAILED), summary
    summary["headroom"]["mini"] = record("mini", hit, None if job == "adhoc" else job, lrc, now)
    return _failover(repo, head, data, out, job, run, now, summary), summary


def _parse(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("review", help="run a brief here; on a dead login, record it and run on the MacBook")
    r.add_argument("--brief", type=Path, required=True)
    r.add_argument("--out", type=Path, required=True, help="transcript; the final message goes to <out>.last.md")
    r.add_argument("--repo", type=Path, default=Path.cwd())
    r.add_argument("--job", help="ticket id, e.g. RA-8191")
    d = sub.add_parser("detect", help="classify an existing Codex run; exit 0 ok, 1 failed, 3 auth_failed")
    d.add_argument("--transcript", type=Path, required=True)
    d.add_argument("--last-message", type=Path)
    return ap.parse_args(argv)


def main(argv=None) -> int:
    a = _parse(argv)
    if a.cmd == "detect":
        last = a.last_message.read_text(errors="replace") if a.last_message and a.last_message.is_file() else ""
        hit = detect(a.transcript.read_text(errors="replace"), last, auth_file_state(), time.time())
        print(json.dumps(hit))
        return {"ok": EXIT_OK, "failed": EXIT_REVIEW_FAILED}.get(hit["status"], EXIT_AUTH_FAILED)
    if not a.brief.is_file():
        print(json.dumps({"error": "brief not found"}))
        return EXIT_USAGE
    rc, summary = review(brief=a.brief, out=a.out, repo=a.repo, job=a.job)
    print(json.dumps(summary, sort_keys=True))
    return rc


if __name__ == "__main__":
    sys.exit(main())
