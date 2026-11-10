#!/usr/bin/env python3
"""spm preflight: the snapshot /spm injects before the model reads the skill.

Contract (each line is a test in test_preflight.py):
- Takes no arguments and reads no user text. argv is ignored.
- Makes no network calls. Remote state comes from the last cached fetch only. The board
  probe may start board.py's detached daily refresh; that child, not this run, goes online.
- Each probe gets at most 3s; the whole run gets 10s. A probe that runs out of
  time or raises prints `UNPROVEN: <probe> (<reason>)`.
- Prints at most 16 lines and always exits 0. A non-zero exit would abort the
  whole /spm invocation, which is the stall this exists to remove.

- Any reading it could not take (a probe that failed, a selftest that failed, a
  library or brain repo with no upstream to compare (a target repo
  with no upstream is a normal reading), an unreadable queue line) rules out CLEAN.
  `evidence=UNPROVEN` from donectl is a reading, not a failed read: it says no
  work has been proven yet, which is the normal state before /spm locks a contract.
- Git runs with GIT_OPTIONAL_LOCKS=0, so the snapshot never rewrites a repo's index.

Test hooks (env): SPM_DONECTL, SPM_SETTINGS, SPM_BRAIN, SPM_SKILLS_DIR,
SPM_QUESTIONS, SPM_BOARD (board.py path), SPM_EXTRA_PROBE (a command run as one more
probe). They are kept on the real path on purpose: each only redirects a read the user's
own environment already controls.
"""
import json
import os
import shlex
import socket
import subprocess
import sys
import time
from pathlib import Path

PROBE_TIMEOUT = 3.0
TOTAL_BUDGET = 10.0
MAX_LINES = 16
HOME = Path.home()
START = time.monotonic()
lines = []
gated = []
unproven = []  # probes that could not give a reading; any of these rules out CLEAN
known = []  # counts of findings already shown to the founder: not repeated, but never CLEAN
elsewhere = []  # Markdown findings announced on the Mini only: not shown here, but never CLEAN


def remaining():
    return TOTAL_BUDGET - (time.monotonic() - START)


def run(argv, cwd=None, err=False):
    """Run one probe command under the per-probe and total budgets."""
    budget = min(PROBE_TIMEOUT, remaining())
    if budget <= 0.2:
        raise TimeoutError("budget")
    r = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, stdin=subprocess.DEVNULL,
                       timeout=budget, env=dict(os.environ, GIT_OPTIONAL_LOCKS="0"))
    return (r.returncode, r.stdout.strip(), r.stderr) if err else (r.returncode, r.stdout.strip())


def clean(s):
    """One printed line per entry: control characters (newlines included) become spaces."""
    return "".join(c if c.isprintable() else " " for c in str(s))


def probe(name, fn):
    reason = None
    if remaining() <= 0.2:
        reason = "budget"
    else:
        try:
            lines.append(clean(fn()))
        except subprocess.TimeoutExpired:
            reason = "timeout"
        except TimeoutError:
            reason = "budget"
        except Exception as e:  # any failure is a labelled unknown, never a crash
            reason = type(e).__name__
    if reason:
        lines.append(f"UNPROVEN: {name} ({reason})")
        unproven.append(name)


def p_done():
    donectl = Path(os.environ.get("SPM_DONECTL", HOME / ".claude/skills/done-harness/scripts/donectl.py"))
    if not donectl.is_file():
        raise FileNotFoundError(str(donectl))
    rc, out = run([sys.executable, str(donectl), "status"])
    st = json.loads(out)
    if (rc != 0 or not isinstance(st, dict)
            or not all(isinstance(st.get(k), str) and st[k] for k in ("contract_status", "criterion_evidence"))):
        raise RuntimeError("donectl status unreadable")
    rc2, _ = run([sys.executable, str(donectl), "selftest"])
    if rc2 != 0:
        unproven.append("done selftest")
    return (f"done: contract={st.get('contract_status')} evidence={st.get('criterion_evidence')} "
            f"selftest={'ok' if rc2 == 0 else 'FAIL (ENFORCEMENT_UNPROVEN)'}")


def p_cli():
    rc, out = run(["claude", "--version"])
    if rc != 0 or not out:
        raise RuntimeError(f"claude --version rc={rc}")
    return f"cli: {out.splitlines()[0]}"


MODEL_ENV = ("ANTHROPIC_MODEL", "ANTHROPIC_DEFAULT_OPUS_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL",
             "ANTHROPIC_DEFAULT_HAIKU_MODEL", "CLAUDE_CODE_SUBAGENT_MODEL")


def p_model():
    # Claude Code precedence: project local > project shared > user. Every file is read, so a
    # fable value anywhere (model key or an env block) blocks; the effective model is the first set.
    files = [Path.cwd() / ".claude/settings.local.json", Path.cwd() / ".claude/settings.json",
             Path(os.environ.get("SPM_SETTINGS", HOME / ".claude/settings.json"))]
    # Each source is read on its own: one unreadable file cannot hide fable in another, or in env.
    env = {k: os.environ[k] for k in MODEL_ENV if os.environ.get(k)}
    seen, effective, bad = list(env.values()), None, []
    for f in files:
        try:
            if not f.is_file():
                continue
            d = json.loads(f.read_text())
            if not isinstance(d, dict):
                raise ValueError("not an object")
            # Claude Code skips a bad entry and keeps the rest, so read every key that is readable.
            seen.append(d.get("model"))
            if effective is None and d.get("model"):
                effective = f"{d['model']} ({f.parent.parent.name}/{f.parent.name}/{f.name})"
            if not isinstance(d.get("env", {}), dict):
                raise ValueError("env is not an object")
            seen += [d.get("env", {}).get(k) for k in MODEL_ENV]
        except Exception as e:
            bad.append(f"{f.parent.parent.name}/{f.parent.name}/{f.name} {type(e).__name__}")
    tail = "UNPROVEN: session override (--model, /model) · UNPROVEN: billing"
    if bad:
        unproven.append("model settings")
        tail = f"UNPROVEN: model settings ({'; '.join(bad)}) · {tail}"
    if "fable" in " ".join(str(x) for x in seen if x).lower():
        gated.append("fable")
        return f"BLOCKED: fable (settings={effective} env={env or '-'}) · {tail}"
    return f"model: settings={effective} env={env or '-'} · {tail}"


def git_state(repo, label):
    # A failed read raises, so probe() records UNPROVEN; only git's own answer means "not a repo".
    rc, _, err = run(["git", "-C", str(repo), "rev-parse", "--git-dir"], err=True)
    if rc != 0:
        # A .git entry here or above is a checkout git cannot read (moved main repo, corrupt
        # HEAD), not an absent repo: it may hold uncommitted work, so the read is UNPROVEN.
        if "not a git repository" in err.lower() and not any(
                (p / ".git").exists() or (p / ".git").is_symlink() for p in (repo, *repo.resolve().parents)):
            return f"{label}: not a git repo"
        raise RuntimeError("git rev-parse failed")
    rc, top = run(["git", "-C", str(repo), "symbolic-ref", "--short", "-q", "HEAD"])
    if rc == 1:
        top = "(detached)"
    elif rc != 0:
        raise RuntimeError("git symbolic-ref failed")
    else:
        # rc 1 is git's own "no such ref" (unborn); anything else is a read that failed.
        rc = run(["git", "-C", str(repo), "rev-parse", "-q", "--verify", "HEAD"])[0]
        if rc == 1:
            top = f"{top} (unborn)"
        elif rc != 0:
            raise RuntimeError("git rev-parse HEAD failed")
    rc, dirty = run(["git", "-C", str(repo), "status", "--porcelain"])
    if rc != 0:
        raise RuntimeError("git status failed")
    # No upstream is a reading ("-"); an upstream that cannot be compared is a failed read.
    rc = run(["git", "-C", str(repo), "rev-parse", "-q", "--verify", "@{u}"])[0]
    if rc == 1:
        ahead = behind = "-"
    elif rc != 0:
        raise RuntimeError("git rev-parse @{u} failed")
    else:
        rc, ab = run(["git", "-C", str(repo), "rev-list", "--left-right", "--count", "HEAD...@{u}"])
        if rc != 0 or len(ab.split()) != 2:
            raise RuntimeError("git rev-list failed")
        ahead, behind = ab.split()
    return top, len(dirty.splitlines()) if dirty else 0, ahead, behind


def p_target():
    r = git_state(Path.cwd(), "target")
    if isinstance(r, str):
        return r
    br, dirty, a, b = r
    return f"target: {Path.cwd().name} {br} dirty={dirty} ahead={a} behind={b} (cached)"


def p_library():
    r = git_state(HOME / ".claude", "library")
    if isinstance(r, str):
        unproven.append("library")
        return r
    br, dirty, a, b = r
    if b == "-":
        unproven.append("library upstream")
    elif b != "0":
        gated.append(f"library behind {b}")
    return f"library ~/.claude: {br} dirty={dirty} ahead={a} behind={b} (cached)"


def brain_path():
    if os.environ.get("SPM_BRAIN"):
        return Path(os.environ["SPM_BRAIN"])
    for c in (HOME / "2nd-brain", HOME / "2nd Brain"):
        if (c / ".git").exists():
            return c
    raise FileNotFoundError("brain")


def p_brain():
    repo = brain_path()
    r = git_state(repo, "brain")
    if isinstance(r, str):
        unproven.append("brain")
        return r
    br, dirty, a, b = r
    rc, fh = run(["git", "-C", str(repo), "rev-parse", "--git-path", "FETCH_HEAD"])
    if rc != 0:
        raise RuntimeError("git rev-parse --git-path failed")
    fh = Path(fh) if Path(fh).is_absolute() else repo / fh
    age = f"{(time.time() - fh.stat().st_mtime) / 3600:.0f}h" if fh.exists() else "never"
    if b == "-":
        unproven.append("brain upstream")
    elif a != "0" and b != "0":
        gated.append("brain diverged")
    return f"brain: ahead={a} behind={b} dirty={dirty} last-fetch={age} ago"


def p_skills():
    sd = Path(os.environ.get("SPM_SKILLS_DIR", HOME / ".claude/skills"))
    dangling = sorted(p.name for p in sd.iterdir() if p.is_symlink() and not p.exists())
    if dangling:
        gated.append(f"{len(dangling)} dangling skills")
    return f"skills: dangling={len(dangling)}" + (f" ({', '.join(dangling[:4])}{'…' if len(dangling) > 4 else ''})" if dangling else "")


def p_questions():
    q = Path(os.environ.get("SPM_QUESTIONS", HOME / ".local/state/spm/questions.jsonl"))
    if not q.exists():
        return "founder questions: open=0 (no queue yet)"
    open_n = bad = 0
    for ln in q.read_text().splitlines():
        try:
            open_n += json.loads(ln).get("status") == "open"
        except (ValueError, AttributeError):
            bad += 1
    if bad:
        unproven.append("questions")
        return f"founder questions: open={open_n} · UNPROVEN: {bad} unreadable line(s)"
    return f"founder questions: open={open_n}"


BOARD_KEYS = {"line", "new", "new_unproven", "known", "known_unproven"}


def p_board():
    # The Skills Library Board's cached verdict (clean home, vendor freshness, md hygiene).
    # board.py probe is offline; when its cache is over 24h old it starts its own detached
    # refresh, so the network call never happens inside this process or its budget.
    board = Path(os.environ.get("SPM_BOARD", Path(__file__).resolve().parent / "board.py"))
    if not board.is_file():
        raise FileNotFoundError(str(board))
    # The probe records what it showed only while it has 0.5s of our wait left, so a kill by
    # our timeout can repeat a finding but never lose one. Too little time: skip, labelled.
    budget = min(PROBE_TIMEOUT, remaining())
    if budget < 1.5:
        raise TimeoutError("budget")
    rc, out = run([sys.executable, str(board), "probe", "--record", "--limit", "5",
                   "--budget", f"{budget - 0.2:.2f}"])
    # The probe always exits 0 by design, so any other code means it crashed or was killed:
    # whatever it printed first is not a reading, however clean it looks.
    if rc != 0:
        raise RuntimeError(f"rc={rc}")
    d = json.loads(out)
    # board.py always emits these fields with a non-empty line; anything less is not a reading.
    if (not isinstance(d, dict) or not BOARD_KEYS <= d.keys()
            or not isinstance(d["line"], str) or not d["line"].strip()
            or not all(isinstance(d[k], list) for k in ("new", "new_unproven"))
            or not all(type(d[k]) is int and d[k] >= 0
                       for k in ("known", "known_unproven", "more_new", "elsewhere") if k in d)):
        raise ValueError("probe output")
    # Only findings the founder has not been shown before are gated; the probe records exactly
    # the ones it returned as shown, so anything over the limit stays new for the next run.
    gated.extend(f"board new: {clean(g)}" for g in list(d.get("new") or [])[:5])
    unproven.extend(f"board: {clean(u)}" for u in list(d.get("new_unproven") or [])[:5])
    # A gap already shown is not re-listed, but it is still a gap: the verdict counts it as UNPROVEN.
    ku = int(d.get("known_unproven") or 0)
    if ku:
        unproven.append(f"board: {ku} known gaps")
    n = int(d.get("known") or 0)
    if n:
        known.append(n)
    e = int(d.get("elsewhere") or 0)
    if e:
        elsewhere.append(e)
    more = int(d.get("more_new") or 0)
    return clean(d["line"]) + (f" · {more} more new next run" if more else "")


def p_extra():
    rc, out = run(shlex.split(os.environ["SPM_EXTRA_PROBE"]))
    if rc != 0:
        raise RuntimeError(f"rc={rc}")
    return f"extra: rc={rc}"


def main():
    lines.append(clean(f"SPM PREFLIGHT {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} host={socket.gethostname()} (offline, cached)"))
    probe("donectl", p_done)
    probe("cli", p_cli)
    probe("model", p_model)
    probe("target", p_target)
    probe("library", p_library)
    probe("brain", p_brain)
    probe("skills", p_skills)
    probe("questions", p_questions)
    probe("board", p_board)
    if os.environ.get("SPM_EXTRA_PROBE"):
        probe("extra", p_extra)
    parts = ([f"GATED {len(gated)} ({'; '.join(gated)})"] if gated else []) + \
            ([f"UNPROVEN {len(unproven)} ({'; '.join(unproven)})"] if unproven else []) + \
            ([f"KNOWN {sum(known)} (shown before, not repeated)"] if known else []) + \
            ([f"KNOWN ELSEWHERE {sum(elsewhere)} (md cases, announced on the Mini)"] if elsewhere else [])
    verdict = " · ".join(parts) or "CLEAN"
    verdict_line = clean(f"verdict: {verdict} · FIXABLE 0 · took {time.monotonic() - START:.1f}s")
    print("\n".join(lines[:MAX_LINES - 1] + [verdict_line]))


if __name__ == "__main__":
    try:
        main()
    except BaseException as e:  # never abort the /spm invocation
        print(f"UNPROVEN: preflight ({type(e).__name__})")
    sys.exit(0)
