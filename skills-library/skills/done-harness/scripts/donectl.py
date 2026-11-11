#!/usr/bin/env python3
"""donectl - the deterministic core of the evidence-bound /done loop.

Everything the LLM says about Done is an opinion. Everything this file returns is
a measurement. The gate trusts this file and nothing else.

Written in Python rather than shell because this estate runs on Windows, where a
shebang is not dispatched (WinError 193) and list-form exec ignores PATHEXT
(WinError 2). Paths here contain spaces; every path operation must survive that.

Subcommands:
  identity      resolve repo/worktree/branch/HEAD/dirty identity, print JSON
  status        the four independent state dimensions for the active work item
  integrity     verify contract + lock + evidence digests still bind
  preflight     the single question the mutation gate asks: may this mutate?
  init          create the project-owned .claude/done tree
  selftest      prove this harness can actually fail (positive control)

  start <goal>  open a work item and bind it to this branch/worktree (-> DRAFT)
  lock          freeze the finish line and bind it to this revision (-> LOCKED)
  refresh       re-observe truth; mark HEAD-bound evidence stale when it moved
  revise <goal> supersede a locked contract with a new version; never edits it.
                This is also how a SECOND work item starts on the same branch: the
                earlier item and its evidence stay on disk under work/<id>
  criteria put --id ID --text TEXT --recipe CMD [--timeout S] [--replace]
                append one criterion to the DRAFT contract (RA-8141). Not `add`:
                "add " contains the gate's "dd " denylist entry, so the mutation
                gate would refuse it.
  contract set --from FILE
                replace the DRAFT contract's criteria from a JSON file: either
                {"criteria": [...]} or a bare list. Only `criteria` is taken.
                Both refuse a LOCKED contract and validate exactly as `lock` does,
                so a headless run (which may not Write under .claude/) can author
                its contract through donectl, the path the mutation gate admits.
  note <text>   append a progress note stamped with clock time and HEAD (notes.jsonl);
                bookkeeping only - it proves nothing and changes no state
  verify        run each criterion recipe and bind exit codes to the exact HEAD
  verify ID...  run only those criteria to diagnose; PARTIAL, never a PASS
                (full output of every recipe: ~/.cache/donectl/<work>/<head>/<id>.log;
                 a criterion may set "timeout": seconds, 1-7200, default 900)
  resume        re-observe real state and replay the last recorded proof
  explain       plain-language account of the current contract
  doctor        harness self-test and enforcement status

The operations above are what /done documents. identity, integrity,
preflight and selftest are the internal measurements they are built on;
doctor is the documented name for selftest.
"""
import hashlib
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import time
import sys
import tempfile
from datetime import datetime, timezone

SCHEMA = "done/1"


# --------------------------------------------------------------------------- util
def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def canon(obj) -> bytes:
    """Deterministic UTF-8 JSON. Digest stability depends on this and nothing else."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def digest(obj) -> str:
    return sha256_bytes(canon(obj))


def git(args, cwd=None):
    """Run git and return (rc, stdout). Never raises; a failed probe is data, not a crash.

    On a non-zero exit with no stdout, the text is stderr: identity() has to read git's
    own "not a git repository" to tell a genuine non-repo from a probe that failed."""
    try:
        p = subprocess.run(
            ["git"] + args, cwd=cwd, capture_output=True, text=True, timeout=30
        )
        out = p.stdout.strip()
        if p.returncode != 0 and not out:
            out = p.stderr.strip()
        return p.returncode, out
    except Exception as e:  # noqa: BLE001 - a probe failure must not kill the gate
        return 127, f"{type(e).__name__}: {e}"


# ----------------------------------------------------------------------- identity
def identity(cwd=None):
    """Resolve real identity. Every field is measured; absence is recorded, not guessed."""
    cwd = os.path.realpath(cwd or os.getcwd())
    out = {"schema": SCHEMA, "observed_at_utc": utc(), "physical_cwd": cwd}

    # Three states, not two. Only git running and saying so is "not a repository";
    # a timeout, a missing binary, or any other refusal is a probe that FAILED, and
    # scope is then unknown. Measured 12/10/2026 at load 17-21: a 30 s timeout read as
    # "not a repo" and preflight ALLOWed destructive commands it had to deny.
    rc, root = git(["rev-parse", "--show-toplevel"], cwd)
    out["git_root"] = root if rc == 0 else None
    if rc == 0:
        out["is_git_repo"] = True
    elif rc == 128 and "not a git repository" in root.lower():
        out["is_git_repo"] = False
        out["status"] = "NOT_A_GIT_REPO"
        return out
    else:
        out["is_git_repo"] = None
        out["status"] = "GIT_PROBE_FAILED"
        out["probe_error"] = f"rc={rc} {root[-200:]}"
        return out

    # git answers these RELATIVE to the directory it ran in (".git" at the top level), and
    # every consumer realpath()s them - which resolves against the PROCESS cwd, not `cwd`.
    # A caller judging another directory (a hook checking the repo a Write targets) got a
    # key for a path that does not exist and read a LOCKED contract as ABSENT (20/10/2026).
    # Anchor them to the directory git actually ran in.
    def _anchored(v):
        return v if os.path.isabs(v) else os.path.normpath(os.path.join(cwd, v))
    rc, v = git(["rev-parse", "--git-common-dir"], cwd)
    out["git_common_dir"] = _anchored(v) if rc == 0 else None
    rc, v = git(["rev-parse", "--git-dir"], cwd)
    out["git_dir"] = _anchored(v) if rc == 0 else None
    out["is_worktree"] = bool(
        out["git_dir"] and out["git_common_dir"] and
        os.path.realpath(out["git_dir"]) != os.path.realpath(out["git_common_dir"])
    )

    rc, v = git(["config", "--get", "remote.origin.url"], cwd)
    out["remote_origin"] = v if rc == 0 and v else None
    rc, v = git(["rev-parse", "--abbrev-ref", "HEAD"], cwd)
    out["branch"] = v if rc == 0 else None
    rc, v = git(["rev-parse", "HEAD"], cwd)
    out["head"] = v if rc == 0 else None
    rc, v = git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], cwd)
    out["upstream"] = v if rc == 0 else None

    rc, v = git(["status", "--porcelain=v2", "--branch", "--untracked-files=all"], cwd)
    if rc == 0:
        lines = [ln for ln in v.splitlines() if not ln.startswith("# branch.")]
        out["dirty_count"] = len(lines)
        out["dirty_digest"] = sha256_bytes("\n".join(sorted(lines)).encode("utf-8"))
    else:
        out["dirty_count"] = None
        out["dirty_digest"] = None

    # Product dirt, excluding .claude/done. Evidence binds to the revision of the
    # code, not to the gate's own bookkeeping - and `verify` WRITES state.json into
    # .claude/done, so counting that as dirt made verification invalidate the very
    # evidence it had just recorded.
    # Pathspec "." is relative to the cwd, so run from the git root: from a subdirectory
    # it missed dirt elsewhere in the repository (3-vendor audit, 02/10/2026).
    rc, v = git(["status", "--porcelain", "--untracked-files=all",
                 "--", ".", ":(exclude).claude/done"], out.get("git_root") or cwd)
    if rc == 0:
        out["dirty_count_product"] = len([ln for ln in v.splitlines() if ln.strip()])
    else:
        out["dirty_count_product"] = out["dirty_count"]

    # A repository fingerprint that survives being cloned to another path.
    fp_src = (out["remote_origin"] or out["git_root"] or cwd).lower()
    out["repo_fingerprint"] = sha256_bytes(fp_src.encode("utf-8"))[:16]
    out["status"] = "OK"
    return out


def done_root(ident):
    if not ident.get("git_root"):
        return None
    return os.path.join(ident["git_root"], ".claude", "done")


# ------------------------------------------------------------------------- status
def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def status(cwd=None):
    ident = identity(cwd)
    st = {
        "schema": SCHEMA,
        "observed_at_utc": utc(),
        "identity": ident,
        "contract_status": "ABSENT",
        "criterion_evidence": "UNPROVEN",
        "verification_status": "NOT_RUN",
        "delivery_status": "NOT_STARTED",
        "work_id": None,
        "contract_digest": None,
        "reasons": [],
    }
    root = done_root(ident)
    if not root or not os.path.isdir(root):
        st["reasons"].append("no .claude/done tree at the git root")
        return st

    active = _read_json(os.path.join(root, "ACTIVE.json")) or {}
    key = f"{ident.get('branch')}@{os.path.realpath(ident.get('git_dir') or '')}"
    work_id = active.get("by_identity", {}).get(key)  # no `default`: see _active_work
    st["work_id"] = work_id
    if not work_id:
        st["reasons"].append("no active work item mapped to this branch/worktree")
        return st

    wdir = os.path.join(root, "work", work_id)
    contract = _read_json(os.path.join(wdir, "contract.json"))
    lock = _read_json(os.path.join(wdir, "lock.json"))
    wstate = _read_json(os.path.join(wdir, "state.json")) or {}

    if not contract:
        st["reasons"].append(f"work item {work_id} has no contract.json")
        return st

    st["contract_status"] = "DRAFT"
    st["contract_digest"] = digest(contract)

    if not lock:
        st["reasons"].append("contract exists but is not locked")
        return st

    # The lock records identity_key and nothing ever read it back, so the binding
    # was decorative. Enforce it: a lock agreed for another branch or worktree does
    # not authorise this one, however well its digest matches.
    if lock.get("identity_key") and lock["identity_key"] != f"{ident.get('branch')}@{os.path.realpath(ident.get('git_dir') or '')}":
        st["contract_status"] = "DRAFT"
        st["reasons"].append(
            "this lock was agreed for %s, not %s - it does not authorise this identity"
            % (lock["identity_key"], ident.get("branch")))
        return st

    if lock.get("contract_digest") != st["contract_digest"]:
        st["contract_status"] = "STALE"
        st["reasons"].append("contract bytes changed since lock - digest mismatch")
        return st

    pins_now = recipe_pins(root, wdir, contract)
    pin_problem = _pin_problem(lock, pins_now)
    if pin_problem:
        st["contract_status"] = "STALE"
        st["reasons"].append(pin_problem)
        return st
    legacy = _legacy_pin_note(lock, pins_now)
    if legacy:
        st["reasons"].append(legacy)

    st["contract_status"] = "LOCKED"

    # delivery_status describes the world, not a revision, so it always carries.
    if wstate.get("delivery_status"):
        st["delivery_status"] = wstate["delivery_status"]

    # criterion_evidence and verification_status are REVISION-BOUND claims. They
    # may only be replayed when the revision that produced them is still HEAD.
    # Trusting them across a HEAD move is exactly the stale-PASS this system exists
    # to prevent, and the previous unconditional replay defeated the check above it.
    verified_head = wstate.get("verified_head")
    head = ident.get("head")
    dirty = _product_dirt(ident)
    if verified_head and head and verified_head == head and not dirty:
        for k in ("criterion_evidence", "verification_status"):
            if wstate.get(k):
                st[k] = wstate[k]
    elif verified_head and dirty:
        # `verify` already refuses to PASS on a dirty tree. Replaying an earlier PASS
        # here would have reintroduced exactly what that refusal prevents: uncommitted
        # working-tree content reported as proven, when nothing measured it.
        st["reasons"].append(
            "evidence was bound to %s but the working tree has %d uncommitted "
            "entries - prior verification invalidated" % (verified_head[:9], dirty))
    elif verified_head:
        st["reasons"].append(
            "evidence was bound to %s but HEAD is %s - prior verification invalidated"
            % (verified_head[:9], (head or "?")[:9]))
    elif lock.get("baseline_head") and head != lock["baseline_head"]:
        st["reasons"].append("HEAD moved since lock and no verification is recorded")
    return st


# ------------------------------------------------------------------- recipe pins
# THE VERIFIER IS PART OF THE FINISH LINE (20/10/2026). `lock` digested contract.json and
# nothing else, and product dirt deliberately excludes .claude/done - so a recipe such as
# `sh .claude/done/work/<id>/checks.sh` ran a file NOTHING bound. The builder could rewrite
# the check after the criteria were agreed and `verify` would PASS on the new bytes. The
# same holds for a committed change to that file: HEAD moves, verify re-runs, and the
# re-run measures whatever the verifier now says.
#
# So the lock pins every byte under .claude/done that a recipe can run:
#   1. every regular file in the work item's own directory, recursively (a checks.sh that
#      `source`s a sibling defeats any parse of the recipe text, so the directory is pinned
#      whole), except the gate's own bookkeeping files and bytecode caches;
#   2. every path a recipe NAMES anywhere else under .claude/done, file or directory; a
#      named path that does not exist is pinned as absent and must stay absent.
# Product files outside .claude/done are NOT pinned: they are bound by HEAD and the clean-
# tree rule, and tests written after the lock are the normal red-to-green shape of work.
#
# Residual, recorded rather than hidden: lock.json itself lives in .claude/done, so a
# builder who rewrites BOTH the script and lock.json's pin is not caught here - exactly as
# contract_digest never caught a rewritten lock. Closing that needs the lock digest held
# somewhere the builder cannot write (see HARNESS-IMPROVEMENTS.md).
PIN_BOOKKEEPING = frozenset({"contract.json", "lock.json", "state.json", "notes.jsonl"})
PIN_SKIP_DIRS = frozenset({"__pycache__"})


def _file_pin(path):
    if os.path.islink(path):
        try:
            target = os.readlink(path)
        except OSError:
            target = "?"
        # A link is pinned by where it points AND by what it reaches, so neither can move.
        inner = _file_pin(os.path.realpath(path)) if os.path.exists(path) else "absent"
        return "symlink:%s:%s" % (target, inner)
    try:
        with open(path, "rb") as fh:
            return sha256_bytes(fh.read())
    except OSError as e:
        return "unreadable:%s" % type(e).__name__


def _pin_tree(top, rel_to, pins, skip_names=()):
    for dirpath, dirnames, filenames in os.walk(top, followlinks=False):
        keep = []
        for d in sorted(dirnames):
            full = os.path.join(dirpath, d)
            if d in PIN_SKIP_DIRS:
                continue
            if os.path.islink(full):  # os.walk will not descend; pin the link itself
                pins[os.path.relpath(full, rel_to)] = _file_pin(full)
                continue
            keep.append(d)
        dirnames[:] = keep
        for n in sorted(filenames):
            if dirpath == top and n in skip_names:
                continue
            if n.endswith((".pyc", ".pyo")):
                continue
            full = os.path.join(dirpath, n)
            pins[os.path.relpath(full, rel_to)] = _file_pin(full)


def _recipe_path_tokens(recipe):
    """Every string in a recipe that could name a path. Over-inclusive on purpose: a token
    that is not a path resolves outside .claude/done and is dropped."""
    try:
        toks = shlex.split(recipe, posix=True)
    except ValueError:
        toks = recipe.split()
    out = []
    for t in toks:
        out.append(t)
        # `--file=path`, `VAR=path`, and paths inside a nested `sh -c "..."` string.
        out.extend(p for p in t.split("=")[1:] if p)
        out.extend(re.findall(r"[^\s'\"=;|&()<>`]*\.claude/done/[^\s'\"=;|&()<>`]*", t))
    return [t.rstrip(";|&)") for t in out if t]


def recipe_pins(root, wdir, contract):
    """{path relative to the done root: digest | None for named-but-absent}."""
    pins = {}
    if not root or not wdir:
        return pins
    real_root = os.path.realpath(root)
    real_wdir = os.path.realpath(wdir)
    if os.path.isdir(real_wdir):
        _pin_tree(real_wdir, real_root, pins, skip_names=PIN_BOOKKEEPING)
    git_root = os.path.dirname(os.path.dirname(real_root))  # <git_root>/.claude/done
    bookkeeping = {os.path.join(real_wdir, n) for n in PIN_BOOKKEEPING}
    for c in (contract or {}).get("criteria") or []:
        for tok in _recipe_path_tokens(_c_recipe(c)):
            cand = os.path.expanduser(tok)
            if not os.path.isabs(cand):
                cand = os.path.join(git_root, cand)
            real = os.path.realpath(cand)
            if real == real_root or not real.startswith(real_root + os.sep):
                continue
            if real in bookkeeping or real.startswith(real_wdir + os.sep) or real == real_wdir:
                continue  # already pinned whole above
            rel = os.path.relpath(real, real_root)
            if os.path.isdir(real):
                _pin_tree(real, real_root, pins)
            elif os.path.lexists(real):
                pins[rel] = _file_pin(real)
            else:
                pins[rel] = None
    return pins


def _legacy_pin_note(lock, now):
    """A lock written before pinning cannot say which bytes were agreed. Measured 20/10/2026:
    34 of 143 live contracts on the Mini are such locks with scripts, many mid-flight, so
    failing them closed would have blocked other sessions' work without warning. They are
    reported, not refused; every lock made from now on is pinned and enforced strictly."""
    if lock.get("recipe_pins") is not None:
        return None
    present = sorted(k for k, v in now.items() if v is not None)
    if not present:
        return None
    return ("recipe files UNPINNED: this lock predates recipe-file pinning, so nothing proves "
            "the %d file(s) a recipe can run (%s) are the bytes agreed at lock; `revise` and "
            "`lock` again to pin them" % (len(present), ", ".join(present[:4])))


def _pin_problem(lock, now):
    """Why the recipe files no longer match the lock, or None. A pre-pinning lock has no
    pins to compare and is reported by _legacy_pin_note instead."""
    pinned = lock.get("recipe_pins")
    if pinned is None:
        return None
    if pinned == now:
        return None
    changed = sorted(k for k in set(pinned) | set(now)
                     if pinned.get(k, "<unpinned>") != now.get(k, "<unpinned>"))
    return ("recipe file(s) under .claude/done changed since lock - digest mismatch: %s%s"
            % (", ".join(changed[:6]), " (+%d more)" % (len(changed) - 6) if len(changed) > 6 else ""))


# ---------------------------------------------------------------------- integrity
def integrity(cwd=None):
    """Hard integrity check. Returns rc 0 only when every binding still holds."""
    st = status(cwd)
    problems = list(st["reasons"])
    ok = st["contract_status"] == "LOCKED" and not any(
        "digest mismatch" in p or "tamper" in p for p in problems
    )
    return {
        "schema": SCHEMA,
        "observed_at_utc": utc(),
        "integrity": "VALID" if ok else "INVALID",
        "contract_status": st["contract_status"],
        "problems": problems,
    }, (0 if ok else 1)


# ---------------------------------------------------------------------- preflight
READONLY_PREFIXES = (
    "git status", "git log", "git diff", "git show", "git rev-parse", "git ls-files",
    "git ls-remote", "git branch", "git remote", "git config --get", "git cat-file",
    "ls", "dir", "cat", "head", "tail", "wc", "grep", "rg", "find", "stat", "file",
    "echo", "pwd", "which", "type", "printf", "sort", "uniq", "cut", "awk", "sed -n",
    "node --version", "python --version", "npm ls", "claude --version", "claude doctor",
)


DESTRUCTIVE_SUBSTRINGS = (
    ">", ">>", "|& ", "rm ", "mv ", "cp ", "mkdir", "touch", "chmod",
    "chown", "curl ", "wget ", "npm i", "npm install", "pip install",
    "git commit", "git push", "git add", "git checkout", "git reset",
    "git merge", "git rebase", "git clean", "&&", ";", "`", "$(",
    # Families the original list missed. Each one was measured passing the
    # allowlist while being able to destroy the tree - including .claude/done
    # itself, i.e. the gate could authorise deleting the gate.
    "-delete", "-exec", "-execdir", "-fprint", "-ok",
    "git branch -d", "git branch -m", "git worktree", "git stash",
    "git update-ref", "git symbolic-ref", "git gc", "git prune",
    "sort -o", "tee ", "dd ", "truncate", "ln ", "install ", "xargs",
)


def command_is_readonly(cmd: str) -> bool:
    """Conservative allowlist. Unknown means mutation-capable, which means denied.

    This is deliberately dumb. A cleverer parser is a bigger attack surface, and
    the failure direction of a dumb allowlist is 'blocked work', not 'silent write'.
    """
    c = " ".join((cmd or "").split()).lower()
    if not c:
        return False
    for bad in DESTRUCTIVE_SUBSTRINGS:
        if bad in c:
            return False
    # Prefix match on a TOKEN boundary. Bare startswith let "find . -delete" ride in
    # on the "find" prefix and "git branch -D x" on "git branch"; a prefix that is
    # not followed by end-of-string or a space is a different command.
    return any(c == p or c.startswith(p + " ") for p in READONLY_PREFIXES)


SHELL_SPECIALS = set(";&|<>`$()*?[]{}!\n\r")
# Still expanded by the shell INSIDE double quotes; see `_scan_quotes`.
DOUBLE_QUOTE_ACTIVE = set("`$")

# Exactly the interpreter names that are a stock python. `startswith("python")` was a P0
# (review at f49594d4): it accepts `python-evil`, `pythonx`, anything. Anchored instead.
_PYTHON_NAME = __import__("re").compile(r"^python(\d+(\.\d+)?)?(\.exe)?$")


def _unquoted_specials(cmd: str) -> set:
    """Shell-special characters appearing OUTSIDE single or double quotes.

    A `;` inside "fix bug (issue #1)" is text the shell hands to donectl. A `;` outside
    quotes is a second command. Matching characters without tracking quote state cannot
    tell those apart, and treating them the same denied every goal string with ordinary
    punctuation in it.

    Backslash escapes the next character outside quotes and inside double quotes, which
    is how a deliberately escaped `\\;` stays data rather than becoming an operator.
    """
    specials, _ = _scan_quotes(cmd)
    return specials


def _unquoted_text(cmd: str) -> str:
    """`cmd` with every quoted span blanked out, for scanning by other rules.

    The destructive-substring denylist below is defence in depth against shell
    OPERATORS and command names. Those only mean anything unquoted, so running the
    denylist over the raw string re-created the very lockout the quote-aware scan was
    added to fix: `donectl.py start "do a; then b"` was denied because `;` is on the
    list, even though there it is a character in a sentence.
    """
    _, blanked = _scan_quotes(cmd)
    return blanked


def _scan_quotes(cmd: str):
    """One pass: unquoted shell-specials found, and the string with quotes blanked."""
    found = set()
    out = []
    quote = None          # None, "'" or '"'
    escaped = False
    for ch in cmd:
        if escaped:
            escaped = False
            out.append(" ")
            continue
        if ch == "\\" and quote != "'":
            escaped = True
            out.append(" ")
            continue
        if quote:
            if ch == quote:
                quote = None
            elif quote == '"' and ch in DOUBLE_QUOTE_ACTIVE:
                # P0 at a1d8e2da (gemini/gemini-3.1-pro-preview): DOUBLE quotes do not
                # stop the shell. `$(...)`, backticks and `${...}` all still expand
                # inside them, so blanking a double-quoted span hid a live second
                # command from this scan -- `start "fix bug $(rm -rf /)"` read as an
                # inert goal. Only SINGLE quotes make these literal, which is why the
                # allowance for ordinary punctuation is unchanged for `'...'`.
                found.add(ch)
            out.append(" ")
            continue
        if ch in "'\"":
            quote = ch
            out.append(" ")
            continue
        if ch in SHELL_SPECIALS:
            found.add(ch)
        out.append(ch)
    if quote is not None:
        found.add(quote)      # unterminated quote: unparseable, so untrusted
    return found, "".join(out)


# POSITIVE IDENTIFICATION, NOT A DENYLIST. Two rounds were lost trying to describe
# which python options are dangerous. Round 8 refused code-bearing characters, so
# round 9 used an option that swallows the NEXT token instead: `python3 -W <donectl.py>
# -c'CODE' status` passes the character test, the loop stops at the donectl path and
# calls it a donectl invocation, and python then treats that path as -W's VALUE and
# executes the -c payload. Codex ran it — OPTION_VALUE_BYPASS_EXECUTED_W.
#
# This file already learned this lesson once, about DESTRUCTIVE_SUBSTRINGS, and wrote
# it down: a denylist over free-form shell was always going to lose. So the flags are
# an ALLOWLIST of options that are inert AND take no value. Anything else — unknown,
# future, or merely unusual — is refused. The cost is that an exotic invocation is
# denied; the alternative is that an unknown option opens the mutation gate.
_INERT_VALUELESS_FLAGS = frozenset({
    "-u",     # unbuffered
    "-B",     # no .pyc
    "-E",     # ignore PYTHON* env
    "-I",     # isolated
    "-s",     # no user site
    "-S",     # no site
    "-O", "-OO",
    "-q",     # quiet
    "-b", "-bb",
    "-d",     # parser debug
    "-v", "-vv",
})


def _flag_is_inert(tok: str) -> bool:
    """True only for flags on the allowlist above. Everything else is refused."""
    return tok in _INERT_VALUELESS_FLAGS


def _trusted_interpreter_dirs() -> set:
    """Directories a system-installed python legitimately lives in, resolved."""
    dirs = {"/usr/bin", "/bin", "/usr/local/bin", "/opt/homebrew/bin", "/opt/local/bin"}
    for cand in (sys.executable, os.path.realpath(sys.executable)):
        if cand:
            dirs.add(os.path.dirname(cand))
    base = getattr(sys, "base_prefix", None) or sys.prefix
    if base:
        dirs.add(os.path.join(base, "bin"))
        dirs.add(base)                       # Windows lays python.exe at the prefix root
    return {os.path.realpath(d) for d in dirs}


def _is_trusted_interpreter(path: str) -> bool:
    """True when `path` IS this interpreter, or lives in a system interpreter directory."""
    real = os.path.realpath(path)
    if os.path.normcase(real) == os.path.normcase(os.path.realpath(sys.executable)):
        return True
    return os.path.normcase(os.path.dirname(real)) in {
        os.path.normcase(d) for d in _trusted_interpreter_dirs()}


def command_is_donectl(cmd: str) -> bool:
    """True for an invocation of this very file.

    Without this the loop is unusable the moment the hook is wired: `start` and
    `lock` are the only routes out of ABSENT, both are Bash calls, and neither
    matches the read-only allowlist - so the gate denies the only commands that
    could ever open it. Measured 2026-08-31.

    IDENTIFIED STRUCTURALLY, NEVER BY SUBSTRING. P0 found by the independent review
    at 9d41ad06 (gemini/gemini-3.1-pro-preview): this used to return True for ANY
    command containing the text "donectl.py", with only a denylist of destructive
    substrings standing in the way. That loses to concatenation, and the reviewer
    wrote the exploit out:

        python3 -c 'import os; os.system("r" + "m -rf /")' # donectl.py

    Nothing in that string is on the denylist, and the trailing comment satisfied the
    substring test, so the mutation gate opened for arbitrary code. A denylist over
    free-form shell was never going to hold — see the estate's own note that a Bash
    classifier is a losing arms race — so this is now a positive identification:

      * no shell metacharacters at all, so nothing can be chained, substituted or
        redirected past the parse;
      * argv[0] must be a python interpreter;
      * `-c` and `-m` are refused outright — both execute something OTHER than the
        file named on the command line, which is the whole trick above;
      * the first non-flag argument must RESOLVE, through realpath, to this exact
        file. A comment, a lookalike name, or a copy elsewhere no longer qualifies.

    The destructive-substring check is kept underneath as defence in depth. It is no
    longer load-bearing, and it is not trusted to be complete.
    """
    c = (cmd or "").strip()
    if not c:
        return False

    # Shell-special characters end the analysis — but ONLY when they are UNQUOTED.
    #
    # P1 found by the review at f49594d4: the first version scanned the raw string, so
    # `donectl.py start "fix bug (issue #1)"` was DENIED for the brackets and hash
    # inside a quoted goal. `start` and `lock` are the only routes out of ABSENT, so
    # that locked the loop shut for any goal containing ordinary punctuation — the gate
    # closing the door from the inside, which is the defect the substring rule existed
    # to avoid in the first place.
    #
    # A quoted `;` is data. An unquoted `;` is a second command. Only the second one is
    # a threat, so the scan below tracks quote state instead of matching characters.
    if _unquoted_specials(c):
        return False

    bare = _unquoted_text(c).lower()
    for bad in DESTRUCTIVE_SUBSTRINGS:
        if bad in bare:
            return False

    try:
        parts = shlex.split(c)
    except ValueError:
        return False                      # unbalanced quotes: unparseable, so untrusted
    if len(parts) < 2:
        return False

    # P0 at f49594d4: `exe.startswith("python")` accepts `python-evil`, and a bare name
    # accepts ANY file called python3 — `/tmp/python3 donectl.py` ran the attacker's
    # binary with the gate's blessing. Two conditions now:
    #   * the name is exactly a stock python spelling, anchored at both ends;
    #   * an interpreter given by PATH must resolve to a real executable file, and one
    #     given by path must BE one. A name this gate cannot resolve is not trusted.
    exe_arg = parts[0]
    exe = os.path.basename(exe_arg).lower()
    if not (_PYTHON_NAME.match(exe) or exe in ("py", "py.exe")):
        return False
    by_name = os.path.basename(exe_arg) == exe_arg
    resolved = shutil.which(exe_arg) if by_name else exe_arg
    if not resolved or not os.path.isfile(resolved) or not os.access(resolved, os.X_OK):
        return False
    # P0 at a1d8e2da (gemini/gemini-3.1-pro-preview): the checks above prove the named
    # file EXISTS and is executable, which is not the same as it being a python. Any
    # executable called `python3` in any writable directory ran with the mutation
    # gate's blessing -- `/tmp/python3 donectl.py status` passed.
    #
    # EVERY SPELLING IS CHECKED, INCLUDING A BARE NAME. The first version of this
    # waived the trust check for a bare name, arguing that PATH is this process's own
    # environment and an attacker who controls it has already won. P0 at 1f8cc49a: the
    # codex lane MEASURED that argument on this machine and it is false. The active
    # PATH begins with user-writable directories under ~/.codex/, so a fake `python3`
    # dropped in one of them was resolved by `shutil.which` and accepted. An argument
    # about the environment is not a property of the environment.
    #
    # Still deliberately permissive about WHICH system python, because a gate that only
    # accepts one build locks the loop shut on the next machine -- the failure this file
    # has already made twice.
    if not _is_trusted_interpreter(resolved):
        return False

    i = 1
    while i < len(parts) and parts[i].startswith("-"):
        if not _flag_is_inert(parts[i]):
            return False                  # executes something other than the named file
        i += 1
    if i >= len(parts):
        return False

    me = os.path.realpath(os.path.abspath(__file__))
    try:
        named = os.path.realpath(os.path.abspath(os.path.expanduser(parts[i])))
    except (OSError, ValueError):
        return False
    return os.path.normcase(named) == os.path.normcase(me)


def preflight(tool_name: str, payload: dict, cwd=None):
    """The single question the mutation gate asks. Deny is the default."""
    st = status(cwd)
    ident = st["identity"]
    res = {"schema": SCHEMA, "observed_at_utc": utc(), "tool": tool_name,
           "decision": "DENY", "reason": None, "state": st["contract_status"]}

    mutating = tool_name in ("Write", "Edit", "MultiEdit", "NotebookEdit", "Bash", "PowerShell")
    if not mutating:
        res.update(decision="ALLOW", reason="tool is not mutation-capable")
        return res

    if tool_name in ("Bash", "PowerShell"):
        cmd = payload.get("command", "")
        if command_is_readonly(cmd):
            res.update(decision="ALLOW", reason="read-only command on the allowlist")
            return res
        if command_is_donectl(cmd):
            res.update(decision="ALLOW",
                       reason="the /done driver itself - denying it would make the "
                              "gate impossible to open")
            return res

    # Writes needed to build the contract itself are always permitted.
    # Only a write tool's OWN path field names a target: a Bash payload can carry a forged file_path.
    target = ""
    if tool_name in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        target = payload.get("notebook_path" if tool_name == "NotebookEdit" else "file_path") or ""
    if target:
        # Writes that BUILD the contract are always permitted - otherwise the loop
        # could never escape ABSENT. But the permission must be anchored to THIS
        # repository's done tree. Matching the bare substring "/.claude/done/"
        # anywhere in a path let /tmp/anything/.claude/done/x be written with no
        # contract at all, which is an unconditional hole straight through the
        # "no locked contract => DENY" invariant. Anchor it, and fail closed when
        # there is no repo to anchor to.
        root = done_root(ident)
        if root:
            try:
                real_root = os.path.realpath(root)
                real_target = os.path.realpath(target)
                inside = (real_target == real_root or
                          real_target.startswith(real_root + os.sep))
            except Exception:  # noqa: BLE001 - a path we cannot resolve is not inside
                inside = False
            if inside:
                res.update(decision="ALLOW",
                           reason="write inside this repo's .claude/done (contract construction)")
                return res

    # Scope. This gate is repo-scoped but the hook that consults it is machine-wide.
    # `init` refuses outside a repository, so a non-repo directory can NEVER hold a
    # locked contract - denying there is a permanent block with no route out, in
    # /tmp, on the Desktop, everywhere. A gate that was never switched on in a
    # directory must not be the thing that stops work there.
    # A failed probe proves nothing about scope. It is UNPROVEN, and unproven fails
    # closed - it must never borrow the out-of-scope ALLOW below.
    if ident.get("is_git_repo") is None:
        res.update(reason="UNPROVEN: git probe failed (%s) - cannot tell whether this "
                          "is a repository, failing closed; retry when the probe "
                          "succeeds" % ident.get("probe_error", "no detail"))
        return res

    if ident.get("is_git_repo") is False:
        res.update(decision="ALLOW",
                   reason="not a git repository - the /done gate is out of scope here")
        return res

    root = done_root(ident)
    if not root or not os.path.isdir(root):
        res.update(decision="ALLOW",
                   reason="no .claude/done tree in this repo - /done was never "
                          "started here, so it gates nothing")
        return res

    if st["contract_status"] != "LOCKED":
        res.update(reason=f"no locked contract (state={st['contract_status']}): "
                          + "; ".join(st["reasons"][:2] or ["contract absent"]))
        return res

    res.update(decision="ALLOW", reason="locked contract in force for this identity")
    return res


# ----------------------------------------------------------------------- selftest
def selftest(cwd=None):
    """Positive control. A gate whose green has never been proven able to go red
    is not a gate. This deliberately constructs a case that MUST be denied."""
    checks = []

    # This control must not read ambient state. Measured 2026-08-31: pointing it at the
    # caller's cwd made it invert the moment a contract was legitimately LOCKED, so
    # `doctor` reported ENFORCEMENT_UNPROVEN exactly when the system was in normal use.
    # A control that cries wolf when the subject is healthy teaches people to ignore it.
    # Every preflight control below runs against a throwaway directory with no
    # contract, NOT the caller's cwd. Measured 2026-08-31: reading ambient state made
    # three of these invert the moment a contract was legitimately LOCKED - because a
    # locked contract is exactly when the gate is SUPPOSED to allow mutation - so
    # `doctor` reported ENFORCEMENT_UNPROVEN precisely when the system was healthy.
    # A control that cries wolf on a healthy subject trains people to ignore it.
    probe_dir = tempfile.mkdtemp(prefix="donectl-selftest-")
    probe_setup = None
    try:
        # A real repository with an initialised, EMPTY done tree. A bare temp dir no
        # longer exercises the DENY path at all: a non-repo is deliberately out of
        # scope and returns ALLOW, so testing there would have silently stopped
        # testing anything.
        # The fixture must be proven before anything is asserted against it. Measured
        # 12/10/2026: `git init` on a loaded volume ran past the 30 s timeout, the
        # half-made directory was then genuinely "not a repository", and the DENY
        # controls went red - a fixture failure reported as a gate defect.
        rc, txt = git(["init", "-q", probe_dir])
        os.makedirs(os.path.join(probe_dir, ".claude", "done"), exist_ok=True)
        if rc != 0:
            probe_setup = f"git init failed rc={rc} {txt[-200:]}"
        elif (identity(probe_dir).get("git_root") or "") != os.path.realpath(probe_dir):
            probe_setup = "git init reported success but the probe dir is not its own repository"
        controls = [
            ("mutation with no locked contract must DENY",
             "Write", {"file_path": os.path.join(probe_dir, "product.ts")}, "DENY"),
            ("read-only tool must ALLOW", "Read", {}, "ALLOW"),
            ("allowlisted read command must ALLOW",
             "Bash", {"command": "git status --porcelain"}, "ALLOW"),
            ("destructive command must DENY", "Bash", {"command": "rm -rf build"}, "DENY"),
            ("chained command must DENY", "Bash", {"command": "git status && rm -rf x"}, "DENY"),
        ]
        for name, tool, payload, want in controls:
            if probe_setup:
                # Unavailable is neither passed nor failed: ok=None, never counted green.
                checks.append((name, None, "NOT_RUN: " + probe_setup))
                continue
            d = preflight(tool, payload, probe_dir)
            checks.append((name, d["decision"] == want, d["decision"]))

        # A probe that fails must fail CLOSED. Simulate git timing out and require DENY;
        # the prior code read this as "not a repository" and ALLOWed.
        g = globals()
        real_git = g["git"]
        g["git"] = lambda args, cwd=None: (127, "TimeoutExpired: simulated probe failure")
        try:
            d = preflight("Bash", {"command": "rm -rf build"}, probe_dir)
        finally:
            g["git"] = real_git
        checks.append(("failed git probe must DENY, not read as out of scope",
                       d["decision"] == "DENY", d["decision"]))
    finally:
        shutil.rmtree(probe_dir, ignore_errors=True)

    a, b = {"x": 1, "y": 2}, {"y": 2, "x": 1}
    checks.append(("digest is key-order independent", digest(a) == digest(b), "n/a"))
    checks.append(("digest changes when content changes", digest(a) != digest({"x": 2, "y": 2}), "n/a"))

    passed = sum(1 for _, ok, _ in checks if ok is True)
    out = {
        "schema": SCHEMA, "observed_at_utc": utc(),
        "passed": passed, "total": len(checks),
        "enforcement": "ENFORCED" if passed == len(checks) else "ENFORCEMENT_UNPROVEN",
        "probe_setup": "FAILED: " + probe_setup if probe_setup else "OK",
        "checks": [{"name": n, "ok": ok, "got": got} for n, ok, got in checks],
    }
    if probe_setup:
        out["note"] = ("the selftest fixture could not be built, so the gate was not "
                       "measured - UNPROVEN, not a gate defect; rerun when git is responsive")
    return out, (0 if passed == len(checks) else 1)


# --------------------------------------------------------------------------- init
def init(cwd=None):
    ident = identity(cwd)
    if not ident.get("git_root"):
        return {"error": "not a git repository; refusing to guess a project root"}, 1
    root = done_root(ident)
    made = []
    for sub in ("", "protocol", "schemas", "bin", "work"):
        p = os.path.join(root, sub) if sub else root
        if not os.path.isdir(p):
            os.makedirs(p, exist_ok=True)
            made.append(os.path.relpath(p, ident["git_root"]))
    active = os.path.join(root, "ACTIVE.json")
    if not os.path.exists(active):
        with open(active, "w", encoding="utf-8") as f:
            json.dump({"schema": SCHEMA, "by_identity": {}, "default": None,
                       "created_at_utc": utc()}, f, indent=2)
        made.append(os.path.relpath(active, ident["git_root"]))
    return {"schema": SCHEMA, "git_root": ident["git_root"], "created": made}, 0


# ---------------------------------------------------------------------- work ops
# The operations /done documents. Each one measures; none of them persuades.
# Every write lands under .claude/done, which preflight permits unconditionally,
# so the loop can build its own contract without ever needing the gate open.

def _write_json(path, obj):
    """Atomic replace. Truncate-in-place lost every branch binding in ACTIVE.json
    when a write was interrupted, and the next `start` silently rebuilt it empty."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def identity_key(ident):
    return "%s@%s" % (ident.get("branch"), os.path.realpath(ident.get("git_dir") or ""))


DEFAULT_CRITERION_TIMEOUT = 900
MAX_CRITERION_TIMEOUT = 7200
REPORT_TAIL = 4000  # 400 lost the one line that named a surviving mutant (02/10/2026)


def _guid_bytes(d1: int, d2: int, d3: int, tail: bytes) -> bytes:
    """A Windows GUID's IN-MEMORY layout: three little-endian integers, then 8 bytes.

    Built from the documented fields rather than hand-packed. P1 at 234b1f24, EXECUTED
    by the codex lane: the first version of this pasted a 16-byte literal that was simply
    the WRONG IDENTIFIER — not FOLDERID_Profile at all. A fake SHGetKnownFolderPath that
    accepted only the documented GUID returned E_INVALIDARG, `_owner_home` returned None,
    and an ordinary Windows host would then get NO home for any recipe. The same
    supported-platform false negative the previous round was meant to close, one layer
    down, because a magic constant nobody can read is a claim nobody can check.
    """
    import struct
    return struct.pack("<IHH", d1, d2, d3) + tail


# FOLDERID_Profile = {5E6C858F-0E22-4760-9AFE-EA3317B67173}
# learn.microsoft.com/en-us/windows/win32/shell/knownfolderid
FOLDERID_PROFILE_BYTES = _guid_bytes(
    0x5E6C858F, 0x0E22, 0x4760, b"\x9a\xfe\xea\x33\x17\xb6\x71\x73")


def _owner_home():
    """The home directory the OPERATING SYSTEM reports, or None.

    Never `os.path.expanduser` and never the caller's HOME/USERPROFILE: P1 at c6d5f40c
    showed a fallback that read those was a fallback that asked the attacker, and every
    shell and interpreter treats that directory as executable configuration.

    P1 at 4f70816a then showed the other half. Returning None on Windows — where there is
    no passwd database — left HOME unset, and the C5 recipe evaluated `Path.home()` at
    import and raised `RuntimeError: Can't determine home directory`. A deterministic
    false negative on a supported platform, with no attacker involved, is worse than the
    hole it came from. So Windows is ASKED PROPERLY, through the shell API, which is
    system-derived in exactly the way the passwd database is.
    """
    if os.name == "nt":
        try:
            import ctypes
            buf = ctypes.c_wchar_p()
            guid = ctypes.create_string_buffer(FOLDERID_PROFILE_BYTES,
                                               len(FOLDERID_PROFILE_BYTES))
            rc = ctypes.windll.shell32.SHGetKnownFolderPath(
                ctypes.byref(guid), 0, None, ctypes.byref(buf))
            if rc == 0 and buf.value:
                return buf.value
        except Exception:  # noqa: BLE001 - fall through to the refusal below
            pass
        return None
    try:
        import pwd
        return pwd.getpwuid(os.getuid()).pw_dir or None
    except Exception:  # noqa: BLE001 - a uid with no passwd entry
        return None


def _run(cmd, cwd=None, timeout=900):
    """Run a criterion recipe. A crashed recipe is a FAILED criterion, never a pass.

    Runs in its own process group. Without that, `subprocess.run`'s timeout kills
    only the shell and then blocks again draining the pipe until EOF - and EOF needs
    every grandchild holding the inherited stdout to exit. A recipe that leaves a
    worker or a server behind (jest, a dev server) therefore hung PAST its own
    timeout with no ceiling at all. On timeout the whole group is signalled.
    """
    kw = {}
    if os.name != "nt":
        kw["start_new_session"] = True
    # A RECIPE RUNS WITH A SYSTEM PATH, NOT THE CALLER'S. P1 at 801d3df0, EXECUTED by the
    # codex lane: the C5 recipe had just been hardened to resolve `git` from a fixed set
    # of system locations — and that only takes effect once the recipe is RUNNING. The
    # contract launches it as the bare command `python3 .../c5_report.py`, through
    # `shell=True` with the caller's inherited PATH, so a fake `python3` earlier on PATH
    # replaced the entire oracle before a line of it ran. Codex demonstrated
    # `C5 PASS: forged...` from a real invocation.
    #
    # That is the seventh route in this run to defeat a check by not going through it,
    # and every one had the same shape: something resolved by NAME rather than identity.
    # Fixing it here rather than in the recipe fixes it for EVERY recipe, and needs no
    # change to the digest-bound contract text.
    # AN ALLOWLIST, BECAUSE THE DENYLIST HAS NOW LOST EIGHT TIMES. P1 at c0e0c70f,
    # EXECUTED: fixing PATH closed executable-NAME substitution and left every other
    # caller-controlled variable in place, so a correctly-resolved interpreter still ran
    # attacker code before the recipe body. Codex added only PYTHONPATH, pointing at a
    # `sitecustomize.py` that printed a forged pass and called `os._exit(0)`, and the
    # exact C5 command returned RC=0 with `C5 PASS: forged`.
    #
    # Every route found in this run has been the same shape — something resolved by NAME
    # rather than identity — and every fix that named the routes was beaten by the next
    # one not on the list: shell metacharacters, python flags, quota phrasings, git's
    # environment, the git binary, the recipe's interpreter, and now the interpreter's
    # startup. So this stops enumerating what is dangerous and states what is NEEDED. A
    # recipe here is a local check against this checkout; it needs a home, a path, a
    # temp directory and a locale. Anything else the caller set can only change the
    # answer, and a variable nobody has thought of yet is excluded by default.
    # COMSPEC is NOT kept: with shell=True on Windows it names the shell itself.
    # PATHEXT is NOT kept: cmd appends it when resolving a bare command name, so the
    # caller could add an extension and choose which file wins. P1 at c6d5f40c.
    keep = ("TMPDIR", "TEMP", "TMP", "USER", "LOGNAME", "LANG", "TERM")
    env = {k: v for k, v in os.environ.items()
           if k in keep or k.startswith("LC_")}

    # HOME COMES FROM THE OPERATING SYSTEM, NOT FROM THE CALLER. P1 at 2728a957,
    # EXECUTED: disabling python's user site closed ONE consumer of HOME and left it
    # active for every other program. zsh reads $ZDOTDIR/.zshenv or $HOME/.zshenv before
    # the named script, and C1's locked recipe is a zsh command — codex put a .zshenv in
    # a temporary HOME and the real recipe returned rc=0 with FORGED-BY-ZSHENV.
    #
    # The previous round's lesson was that keeping a variable because it is NEEDED is not
    # keeping it because it is INERT, and the fix that followed treated one consumer
    # instead of the variable. Recipes DO need a home to resolve paths from; they need
    # the OWNER's home, which the passwd database knows and an environment variable only
    # claims. ZDOTDIR is simply absent from the allowlist.
    # AND THE FALLBACK MUST NOT ASK THE CALLER EITHER. P1 at c6d5f40c, EXECUTED: the
    # branch for Windows or a uid with no passwd entry called
    # `os.path.expanduser("~")` — which reads caller HOME on POSIX and caller
    # USERPROFILE / HOMEDRIVE+HOMEPATH on Windows — and installed the result as the
    # child's HOME, reopening the whole startup-file route whenever pwd was unavailable.
    # A fallback that asks the attacker is not a fallback.
    #
    # If the operating system cannot say whose home this is, NO home is set. A recipe
    # that needs one then fails loudly, which is the correct outcome: an unknown home is
    # unproven, not a default.
    home = _owner_home()
    if home:
        env["HOME"] = home
        if os.name == "nt":
            # Windows programs read these rather than HOME; they are set FROM the
            # OS-derived value, never copied from the caller.
            env["USERPROFILE"] = home
            drive, rest = os.path.splitdrive(home)
            if drive:
                env["HOMEDRIVE"] = drive
                env["HOMEPATH"] = rest or "\\"

    # PYTHONNOUSERSITE WAS REMOVED, AND THAT IS THE POINT OF FIXING CAUSES. It was added
    # at affdd703 because a hostile HOME let python import a user-site sitecustomize.py
    # before the recipe body — a fix aimed at ONE CONSUMER of a variable that was still
    # the caller's. Two rounds later HOME stopped coming from the caller at all: it is
    # read from the passwd database, so the user-site directory it points at is the
    # OWNER's, which is not an attack surface.
    #
    # Keeping the workaround after removing its cause was not free. Measured on this
    # machine by `donectl verify`: /usr/bin/python3 has pytest 8.4.2 only through the
    # user site, so C7's recipe returned "No module named pytest" and the criterion
    # became UNPROVABLE. Three of codex's last four findings were exactly this shape —
    # a security fix creating a false negative on a supported path — and this one was
    # mine, found by running the real contract rather than the tests.

    # AND THE SAME SHAPE APPEARED ONE LEVEL DOWN, IN THIS VERY LIST. Found 05/09/2026,
    # founder-authorised. The allowlist was system directories only, and on this estate
    # node is installed at <owner home>/.local/bin/node — on none of them. So every
    # recipe that shelled out to node got ENOENT, and an ENOENT inside a test stub
    # produces empty output, which a suite scores as a pass, a crash, or "never
    # executed" — never as the missing tool. It silently disabled three timeout tests in
    # Unite-Group, and then the entire positive control of a mutation harness written
    # hours later. That is the PYTHONNOUSERSITE lesson above, recurring: a security
    # decision producing a false negative on a supported path.
    #
    # The owner's directory is added from the PASSWD DATABASE, exactly as HOME is above,
    # so this adds no caller-controlled input — the same reasoning that already accepted
    # the owner's user-site directory. What makes it safe is the POSITION: it goes LAST,
    # after every system directory, so a file dropped in ~/.local/bin can never answer
    # for git, python3 or any other system tool. test_recipe_path_hardening.py asserts
    # that ordering, not merely the membership; membership alone would be the hole.
    if os.name != "nt":
        _dirs = ["/usr/bin", "/bin", "/usr/sbin", "/sbin", "/usr/local/bin", "/opt/homebrew/bin"]
        if home:
            _dirs.append(os.path.join(home, ".local", "bin"))
        env["PATH"] = ":".join(d for d in _dirs if os.path.isdir(d))
    else:
        # P1 at affdd703, EXECUTED: the system PATH was applied only on POSIX, so the
        # Windows branch copied the caller's entire PATH while COMSPEC — the shell that
        # shell=True invokes — was also kept. Both are system-derived now, and neither
        # comes from the caller.
        # AND ITS ROOT OF TRUST IS NOT THE CALLER'S EITHER. P1 at 2728a957, EXECUTED:
        # the branch derived PATH and COMSPEC from SYSTEMROOT and took SYSTEMROOT from
        # the environment, so setting it to C:\ATTACKER moved all three. There is no
        # passwd database to ask here, so the standard location is used unless the
        # caller's value is one of the two real ones — an allowlist again, because that
        # is what has held every time a list of bad values has not.
        _claimed = os.environ.get("SYSTEMROOT") or os.environ.get("SystemRoot") or ""
        root = (_claimed if _claimed.rstrip("\\/").lower()
                in (r"c:\windows", r"c:\winnt") else r"C:\Windows")
        env["SYSTEMROOT"] = root
        env["PATH"] = ";".join((
            os.path.join(root, "System32"),
            root,
            os.path.join(root, "System32", "Wbem"),
            os.path.join(root, "System32", "WindowsPowerShell", "v1.0"),
        ))
        env["COMSPEC"] = os.path.join(root, "System32", "cmd.exe")
        # AND THE VERIFIER WROTE INTO THE REPOSITORY IT WAS JUDGING. Found 02/11/2026 on
        # Unite-Group work w_e660be3fd416: a criterion recipe running npm left a directory
        # literally named "%SystemDrive%" in the worktree, holding the shell's own cache
        # under ProgramData\Microsoft\Windows\Caches. The name is the diagnosis -- a
        # component held %SystemDrive%\ProgramData from the registry and could not expand
        # it, because SYSTEMDRIVE was not in the environment, so it created the unexpanded
        # name relative to cwd. That dirtied the tree, and verify refuses on a dirty tree
        # and runs nothing: the gate was failing its own work for dirt the gate made.
        # Measured both ways before this line was written -- of the seven recipes only the
        # npm one did it, 9 files without SYSTEMDRIVE and none with it.
        # Derived from root rather than taken from the caller, so no new caller-controlled
        # value enters the environment: root is already the allowlisted one above.
        env["SYSTEMDRIVE"] = os.path.splitdrive(root)[0] or "C:"
        # AND THE 05/09/2026 FALSE NEGATIVE, ONE PLATFORM OVER. Found 17/10/2026 on
        # Synthex work w_700ccb6f54bf: the list above is System32, the Windows directory,
        # Wbem and WindowsPowerShell and nothing else, so a recipe written as `node ...`
        # fails with "'node' is not recognized" and the criterion reads FAILED for a
        # tooling reason that looks exactly like a real failure. All three criteria at
        # b5e5bb369 did, until the contract was revised to name C:\nvm\nodejs\node.exe
        # by absolute path. The POSIX branch closed the same gap by appending the
        # owner's ~/.local/bin from the passwd database; there is no passwd database
        # here, so the two FIXED install locations are used instead - the standard
        # installer's and nvm-windows's symlink - read from nowhere the caller controls
        # (not NVM_SYMLINK, not ProgramFiles) and only when present. What makes them
        # safe is the POSITION: LAST, after every system directory, so a file dropped
        # in either can never answer for cmd, where or any other system tool.
        # test_recipe_path_hardening.py asserts that ordering, not merely membership.
        _node_dirs = [r"C:\Program Files\nodejs", r"C:\nvm\nodejs"]
        env["PATH"] = ";".join([env["PATH"]] + [d for d in _node_dirs if os.path.isdir(d)])
        # CMD SEARCHES THE CURRENT DIRECTORY FIRST. P1 at c6d5f40c: every recipe is an
        # opaque string run with shell=True and cwd set to the REVIEWED REPOSITORY, so a
        # committed `python3.cmd` in the repo root would win before any fixed system
        # directory — the reviewed code choosing the tool that judges it. This is the
        # documented switch that stops that search, and PATHEXT is fixed here rather
        # than inherited so the caller cannot choose which extension wins.
        env["NoDefaultCurrentDirectoryInExePath"] = "1"
        env["PATHEXT"] = ".COM;.EXE;.BAT;.CMD"
    try:
        p = subprocess.Popen(cmd, shell=True, cwd=cwd, text=True, env=env,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **kw)
    except Exception as e:  # noqa: BLE001
        return 127, "%s: %s" % (type(e).__name__, e)

    def _kill_group():
        try:
            if os.name != "nt":
                os.killpg(os.getpgid(p.pid), signal.SIGKILL)
            else:
                p.kill()
        except Exception:  # noqa: BLE001
            try:
                p.kill()
            except Exception:  # noqa: BLE001
                pass

    try:
        out, _ = p.communicate(timeout=timeout)
        rc = p.returncode
    except subprocess.TimeoutExpired:
        _kill_group()
        try:
            out, _ = p.communicate(timeout=15)
        except Exception:  # noqa: BLE001
            out = ""
        return 124, ("recipe exceeded %ss and its process group was killed\n%s"
                     % (timeout, out or "")).strip()
    except Exception as e:  # noqa: BLE001
        _kill_group()
        return 127, "%s: %s" % (type(e).__name__, e)

    return rc, (out or "").strip()  # whole output: the evidence log keeps all of it


def _require_tree(cwd=None):
    ident = identity(cwd)
    if not ident.get("git_root"):
        return None, None, ({"error": "not a repository; refusing to guess a project root"}, 1)
    root = done_root(ident)
    if not root or not os.path.isdir(root):
        return None, None, ({"error": "no .claude/done tree at the root; run `init` first"}, 1)
    return ident, root, None


def _withdraw(wdir, vstatus="NOT_RUN", cev="UNPROVEN"):
    """Newer evidence says the last proof may not hold: drop it. Only a full verify restores PASS."""
    state = _read_json(os.path.join(wdir, "state.json")) or _fresh_state()
    state.update({"verification_status": vstatus, "criterion_evidence": cev,
                  "verified_head": None, "updated_at_utc": utc()})
    _write_json(os.path.join(wdir, "state.json"), state)
    return state


def _verify_lock(work_id):
    """Exclusive per-work-item lock, so two verifies cannot interleave and the later writer
    restore a proof the earlier one withdrew (review r4). None = held elsewhere; True = no
    locking on this platform."""
    try:
        import fcntl
    except ImportError:
        return True
    d = os.path.join(os.path.expanduser("~"), ".cache", "donectl", str(work_id))
    os.makedirs(d, exist_ok=True)
    fh = open(os.path.join(d, "verify.lock"), "w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        return None
    return fh


def _product_dirt(ident):
    """Entries of product dirt; 1 when it could not be measured. An unmeasured tree is
    never a clean one: `or 0` here let a failed `git status` bind a PASS (audit 02/10/2026)."""
    for k in ("dirty_count_product", "dirty_count"):
        if ident.get(k) is not None:
            return ident[k]
    return 1


def _active_work(root, ident):
    active = _read_json(os.path.join(root, "ACTIVE.json")) or {}
    # No `default` fallback. It was a cross-identity authorisation bug: a contract
    # locked on branch A resolved for branch B, whose bytes and digest matched, so
    # B read as LOCKED and the gate opened for a branch that never agreed a finish
    # line. A miss must be ABSENT, which fails closed.
    return active.get("by_identity", {}).get(identity_key(ident))


def _work_dir(root, work_id):
    return os.path.join(root, "work", work_id)


def _bind_active(root, ident, work_id):
    active_path = os.path.join(root, "ACTIVE.json")
    active = _read_json(active_path)
    if active is None:
        if os.path.exists(active_path):
            # It exists and would not parse. Rebuilding it blank here silently
            # deleted every other branch's and worktree's binding.
            raise SystemExit(json.dumps(
                {"error": "ACTIVE.json exists but does not parse; refusing to "
                          "overwrite it and lose every binding it holds",
                 "path": active_path}, indent=2))
        active = {"schema": SCHEMA, "by_identity": {}}
    active.setdefault("by_identity", {})[identity_key(ident)] = work_id
    active.pop("default", None)
    _write_json(os.path.join(root, "ACTIVE.json"), active)


def _fresh_state():
    return {"schema": SCHEMA, "criterion_evidence": "UNPROVEN",
            "verification_status": "NOT_RUN", "delivery_status": "NOT_STARTED",
            "verified_head": None, "updated_at_utc": utc()}


def _new_work(root, ident, goal, supersedes=None, version=1):
    key = identity_key(ident)
    work_id = "w_" + digest({"goal": goal, "key": key, "at": utc(), "v": version})[:12]
    wdir = _work_dir(root, work_id)
    os.makedirs(wdir, exist_ok=True)
    contract = {
        "schema": SCHEMA, "work_id": work_id, "version": version,
        "supersedes": supersedes, "goal": goal.strip(), "created_at_utc": utc(),
        "identity_key": key,
        "baseline_observed": {"head": ident.get("head"), "branch": ident.get("branch"),
                              "dirty_count": ident.get("dirty_count")},
        "criteria": [],
    }
    _write_json(os.path.join(wdir, "contract.json"), contract)
    _write_json(os.path.join(wdir, "state.json"), _fresh_state())
    _bind_active(root, ident, work_id)
    return work_id, wdir, contract


CRITERION_HINT = ("add criteria - each needs an id, text, and a recipe (a shell command whose "
                  "exit code IS the evidence) - with `criteria put --id ID --text TEXT "
                  "--recipe CMD` or `contract set --from FILE`, then run `lock`")


def start(goal, cwd=None):
    """Open a work item and bind it to this branch/worktree. Refuses to clobber a lock."""
    ident, root, err = _require_tree(cwd)
    if err:
        return err
    if not goal or not goal.strip():
        return {"error": 'a goal is required: start "<what done means>"'}, 2

    existing = _active_work(root, ident)
    if existing:
        if _read_json(os.path.join(_work_dir(root, existing), "lock.json")):
            return {"error": "work item %s is already LOCKED for this identity; "
                             "use `revise` to supersede it - a locked contract is never edited"
                             % existing, "work_id": existing}, 1

    work_id, wdir, contract = _new_work(root, ident, goal, supersedes=existing)
    return {"schema": SCHEMA, "work_id": work_id, "contract_status": "DRAFT",
            "goal": contract["goal"], "identity_key": contract["identity_key"],
            "contract_path": os.path.join(wdir, "contract.json"),
            "next": CRITERION_HINT}, 0



# Criterion field names. Real contracts in this estate are authored with `statement` and
# `oracle`; this reader was written against an older `text` / `recipe` pair. Measured
# 01/09/2026 on backlog-drain-20260831: six fully-written criteria rendered as
#   [C1] (no text)  (proven by: NOTHING - unmeasurable as written)
# which makes a specified contract indistinguishable from an empty one. `verify` failed
# closed and produced no false green, so the damage was confined to the readout - but a
# readout that shows a real contract as vacuous is how someone rewrites or discards one.
#
# `oracle` is DELIBERATELY not fed to _run(). Oracles in these contracts are prose
# ("read the tail summary and the named failing gates"), not shell. Executing prose would
# turn a readout bug into an execution bug. A criterion with an oracle but no runnable
# recipe stays UNPROVEN - it just now says WHY, instead of claiming nothing measures it.
def _c_text(c):
    return (c.get("statement") or c.get("text") or "").strip()


def _c_timeout(c):
    """Seconds a recipe may run: the contract's own `timeout`, else the default. None = invalid."""
    t = c.get("timeout", DEFAULT_CRITERION_TIMEOUT)
    if isinstance(t, bool) or not isinstance(t, int) or not 1 <= t <= MAX_CRITERION_TIMEOUT:
        return None
    return t


def _evidence_log(work_id, head, cid, out):
    """Full recipe output to a log OUTSIDE the repository (no tree dirt). Returns its path."""
    safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in str(cid))[:60]
    safe += "-" + sha256_bytes(str(cid).encode("utf-8"))[:12]  # C/1 and C?1 must not share a file
    # Content-addressed: a later run never overwrites the bytes an earlier proof's digest names (review r5).
    safe += "-" + sha256_bytes(out.encode("utf-8", "replace"))[:16]
    d = os.path.join(os.path.expanduser("~"), ".cache", "donectl", str(work_id), (head or "nohead")[:12])
    try:
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, safe + ".log")
        with open(p, "w", encoding="utf-8", errors="replace") as fh:
            fh.write(out)
        return p
    except OSError:
        return None


def _c_recipe(c):
    return (c.get("recipe") or "").strip()


def _c_oracle(c):
    return (c.get("oracle") or "").strip()


CONTRACT_LOCK_WAIT = 30.0


class _ExclFile(object):
    """Portable fallback lock (no fcntl, e.g. Windows): O_CREAT|O_EXCL marker file."""

    def __init__(self, path):
        self.path = path

    def close(self):
        try:
            os.unlink(self.path)
        except OSError:
            pass


def _contract_lock(cwd=None):
    """Exclusive lock shared by `lock`, `criteria put` and `contract set` for one done
    root, so an authoring write can never land after `lock` froze the contract (RA-8141
    review r1). fcntl.flock where available, else an O_EXCL lock file (review r2: no
    platform runs unserialised). Returns (handle or None, error or None); a caller that
    gets an error must not write (fail closed). None/None = no tree, nothing to guard."""
    ident, root, err = _require_tree(cwd)
    if err or not root:
        return None, None
    d = os.path.join(os.path.expanduser("~"), ".cache", "donectl", "contract-locks")
    os.makedirs(d, exist_ok=True)
    key = hashlib.sha256(os.path.realpath(str(root)).encode()).hexdigest()[:24]
    path = os.path.join(d, key + ".lock")
    try:
        import fcntl
    except ImportError:
        fcntl = None
    # review r4: never follow a planted symlink at the lock dir or the lock file.
    if os.path.islink(d) or os.path.realpath(d) != os.path.join(
            os.path.realpath(os.path.dirname(d)), os.path.basename(d)):
        return None, ({"error": "contract lock directory %s is a symlink; refusing to write"
                                % d}, 1)
    if fcntl is not None:
        try:
            fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
        except OSError as e:
            return None, ({"error": "contract lock file unusable (%s; a symlink?); refusing "
                                    "to write" % type(e).__name__}, 1)
        fh = os.fdopen(fd, "r+")
        fcntl.flock(fh, fcntl.LOCK_EX)
        return fh, None
    excl = path + ".excl"
    end = time.time() + CONTRACT_LOCK_WAIT
    while True:
        try:
            os.close(os.open(excl, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
            return _ExclFile(excl), None
        except FileExistsError:
            if time.time() >= end:
                return None, ({"error": "contract lock busy for %ds (%s); refusing to write. "
                                        "If no donectl is running, remove that file."
                                        % (CONTRACT_LOCK_WAIT, excl)}, 1)
            time.sleep(0.05)
        except OSError as e:
            return None, ({"error": "contract lock unavailable (%s); refusing to write"
                                    % type(e).__name__}, 1)


def _under_contract_lock(fn, *a, **kw):
    fh, lerr = _contract_lock(kw.get("cwd"))
    if lerr:
        return lerr
    try:
        return fn(*a, **kw)
    finally:
        if fh is not None:
            fh.close()


def lock(cwd=None):
    """Freeze the finish line and bind it to this revision."""
    return _under_contract_lock(_lock, cwd=cwd)


def _lock(cwd=None):
    ident, root, err = _require_tree(cwd)
    if err:
        return err
    work_id = _active_work(root, ident)
    if not work_id:
        return {"error": 'no active work item; run start "<goal>" first'}, 1
    wdir = _work_dir(root, work_id)
    contract = _read_json(os.path.join(wdir, "contract.json"))
    if not contract:
        return {"error": "work item %s has no contract.json" % work_id}, 1

    existing = _read_json(os.path.join(wdir, "lock.json"))
    if existing:
        if existing.get("contract_digest") == digest(contract):
            # Same contract bytes, but the verifier it runs may have moved since: saying
            # "nothing to do" here would bless the edit by omission.
            now = recipe_pins(root, wdir, contract)
            moved = _pin_problem(existing, now) or _legacy_pin_note(existing, now)
            if moved:
                return {"error": "%s; `lock` never re-freezes a changed verifier - use "
                                 "`revise` to open a new version" % moved,
                        "work_id": work_id}, 1
            return {"schema": SCHEMA, "work_id": work_id, "contract_status": "LOCKED",
                    "note": "already locked at this exact contract; nothing to do"}, 0
        return {"error": "the contract changed after it was locked; `lock` never re-freezes "
                         "an edited contract - use `revise` to open a new version",
                "work_id": work_id}, 1

    criteria = contract.get("criteria") or []
    if not criteria:
        return {"error": "refusing to lock a contract with no criteria - Done would mean "
                         "nothing and every later PASS would be vacuous",
                "work_id": work_id,
                "contract_path": os.path.join(wdir, "contract.json"),
                "next": CRITERION_HINT}, 2
    bad = [c.get("id") or "<no id>" for c in criteria if not _c_text(c)]
    if bad:
        return {"error": "every criterion needs text describing what must be true",
                "work_id": work_id, "criteria_missing_text": bad}, 2
    bad = [c.get("id") or "<no id>" for c in criteria if _c_timeout(c) is None]
    if bad:
        return {"error": "a criterion timeout must be a whole number of seconds, 1-%d"
                         % MAX_CRITERION_TIMEOUT, "work_id": work_id, "criteria_bad_timeout": bad}, 2
    ids = [c.get("id") for c in criteria]
    if len(set(ids)) != len(ids):
        return {"error": "criterion ids must be unique; evidence is keyed by id",
                "work_id": work_id}, 2

    lk = {"schema": SCHEMA, "work_id": work_id,
          "contract_digest": digest(contract),
          "baseline_head": ident.get("head"),
          "identity_key": identity_key(ident),
          "locked_at_utc": utc(),
          "criteria_count": len(criteria),
          "recipe_pins": recipe_pins(root, wdir, contract)}
    _write_json(os.path.join(wdir, "lock.json"), lk)
    return {"schema": SCHEMA, "work_id": work_id, "contract_status": "LOCKED",
            "baseline_head": lk["baseline_head"], "contract_digest": lk["contract_digest"],
            "criteria_count": len(criteria)}, 0



# ---- contract authoring (RA-8141) -------------------------------------------------
# Headless Claude Code refuses Write/Edit under .claude/, and the mutation gate admits
# donectl's own Bash invocation. So an unattended run could `start` a work item but
# never give it criteria: `lock` refused the empty contract and the run stalled at
# ABSENT/DRAFT. These two commands write the DRAFT contract through donectl itself.
# They never touch a LOCKED contract (that stays `revise`-only) and they validate each
# criterion exactly as `lock` will, so a contract they write is one `lock` accepts.

def _criteria_problems(criteria):
    """Same rules `lock` applies, plus: a recipe must be a string (RA-7838)."""
    if not isinstance(criteria, list) or not criteria:
        return "criteria must be a non-empty list"
    for c in criteria:
        if not isinstance(c, dict):
            return "every criterion must be a JSON object"
        cid = c.get("id")
        if not isinstance(cid, str) or not cid.strip():
            return "every criterion needs a non-empty string id"
        t = c.get("statement") or c.get("text") or ""
        if not isinstance(t, str) or not t.strip():
            return "criterion %s needs text describing what must be true" % cid
        r = c.get("recipe")
        if r is not None and not isinstance(r, str):
            return "criterion %s: recipe must be a shell command string" % cid
        if _c_timeout(c) is None:
            return "criterion %s: timeout must be a whole number of seconds, 1-%d" % (
                cid, MAX_CRITERION_TIMEOUT)
    ids = [c["id"] for c in criteria]
    if len(set(ids)) != len(ids):
        return "criterion ids must be unique; evidence is keyed by id"
    return None


def _draft_contract(cwd=None):
    """(wdir, contract, None) for the active DRAFT, else (None, None, (err, rc))."""
    ident, root, err = _require_tree(cwd)
    if err:
        return None, None, err
    work_id = _active_work(root, ident)
    if not work_id:
        return None, None, ({"error": 'no active work item; run start "<goal>" first'}, 1)
    import re
    if not isinstance(work_id, str) or not re.fullmatch(r"w_[0-9a-f]{12}", work_id):
        return None, None, ({"error": "active work id is not a donectl work id; refusing "
                                      "to write"}, 1)
    wdir = _work_dir(root, work_id)
    # review r3: never realpath the work dir before comparing (a symlinked `work` would be
    # followed on both sides); no symlink at work/ or the leaf; resolved path must be exact.
    expected = os.path.join(os.path.realpath(root), "work", work_id)
    if (os.path.islink(os.path.join(root, "work")) or os.path.islink(wdir)
            or os.path.realpath(wdir) != expected):
        return None, None, ({"error": "work item %s resolves outside the done tree; refusing "
                                      "to write" % work_id}, 1)
    if os.path.lexists(os.path.join(wdir, "lock.json")):   # present at all = locked (r2)
        return None, None, ({"error": "work item %s is LOCKED; a locked contract is never "
                                      "edited - use `revise` to open a new version" % work_id,
                             "work_id": work_id}, 1)
    cpath = os.path.join(wdir, "contract.json")
    if os.path.islink(cpath):
        return None, None, ({"error": "contract.json is a symlink; refusing to write"}, 1)
    contract = _read_json(cpath)
    if not isinstance(contract, dict):
        return None, None, ({"error": "work item %s has no readable contract.json" % work_id}, 1)
    if contract.get("work_id") != work_id or contract.get("identity_key") != identity_key(ident):
        return None, None, ({"error": "contract.json does not belong to this branch's active "
                                      "work item; refusing to write", "work_id": work_id}, 1)
    return wdir, contract, None


def _write_contract_nofollow(path, obj):
    """Atomic write that never follows a planted symlink (review r3): the temp file is a
    fresh O_EXCL random name in the same dir (mkstemp), then os.replace onto the target,
    which replaces a link rather than writing through it."""
    d = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(prefix=".contract.", suffix=".tmp", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, indent=2, ensure_ascii=False)   # same bytes as _write_json
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _save_criteria(wdir, contract, criteria):
    contract["criteria"] = criteria
    _write_contract_nofollow(os.path.join(wdir, "contract.json"), contract)
    return {"schema": SCHEMA, "work_id": contract.get("work_id"), "contract_status": "DRAFT",
            "criteria_count": len(criteria), "criteria_ids": [c["id"] for c in criteria],
            "contract_path": os.path.join(wdir, "contract.json"),
            "next": "add more criteria, or run `lock`"}, 0


def criteria_add(cid, text, recipe, timeout=None, replace=False, cwd=None):
    return _under_contract_lock(_criteria_add, cid, text, recipe, timeout=timeout,
                                replace=replace, cwd=cwd)


def _criteria_add(cid, text, recipe, timeout=None, replace=False, cwd=None):
    crit = {"id": (cid or "").strip(), "text": (text or "").strip(), "recipe": (recipe or "").strip()}
    if not crit["id"] or not crit["text"] or not crit["recipe"]:
        return {"error": "criteria put needs --id, --text and --recipe, all non-empty"}, 2
    if timeout is not None:
        crit["timeout"] = timeout
    wdir, contract, err = _draft_contract(cwd)
    if err:
        return err
    existing = [c for c in (contract.get("criteria") or []) if isinstance(c, dict)]
    if any(c.get("id") == crit["id"] for c in existing):
        if not replace:
            return {"error": "criterion %s already exists; pass --replace to overwrite it"
                             % crit["id"]}, 2
        new = [crit if c.get("id") == crit["id"] else c for c in existing]
    else:
        new = existing + [crit]
    problem = _criteria_problems(new)
    if problem:
        return {"error": problem}, 2
    return _save_criteria(wdir, contract, new)


def contract_set(src, cwd=None):
    return _under_contract_lock(_contract_set, src, cwd=cwd)


def _contract_set(src, cwd=None):
    if not src:
        return {"error": "contract set needs --from <file.json>"}, 2
    try:
        with open(os.path.expanduser(src), encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as e:
        return {"error": "could not read %s as JSON: %s" % (src, type(e).__name__)}, 2
    criteria = data.get("criteria") if isinstance(data, dict) else data
    problem = _criteria_problems(criteria)
    if problem:
        return {"error": problem}, 2
    wdir, contract, err = _draft_contract(cwd)
    if err:
        return err
    return _save_criteria(wdir, contract, criteria)


def _authoring_cli(argv):
    """`criteria put ...` / `contract set ...`. argv starts at the noun."""
    import argparse

    class _P(argparse.ArgumentParser):
        def error(self, message):
            raise ValueError(message)

    noun, verb, rest = argv[0], (argv[1] if len(argv) > 1 else ""), argv[2:]
    try:
        if noun == "criteria" and verb == "put":
            p = _P(prog="donectl criteria put", add_help=False)
            p.add_argument("--id", required=True)
            p.add_argument("--text", required=True)
            p.add_argument("--recipe", required=True)
            p.add_argument("--timeout", type=int)
            p.add_argument("--replace", action="store_true")
            a = p.parse_args(rest)
            return criteria_add(a.id, a.text, a.recipe, a.timeout, a.replace)
        if noun == "contract" and verb == "set":
            p = _P(prog="donectl contract set", add_help=False)
            p.add_argument("--from", dest="src", required=True)
            a = p.parse_args(rest)
            return contract_set(a.src)
    except ValueError as e:
        return {"error": str(e)}, 2
    return {"error": "usage: criteria put --id ID --text TEXT --recipe CMD [--timeout S] "
                     "[--replace] | contract set --from FILE"}, 2


def verify(cwd=None, only=None):
    """Serialised wrapper: see _verify."""
    ident, root, err = _require_tree(cwd)
    if err:
        return err
    work_id = status(cwd).get("work_id")
    lock = _verify_lock(work_id) if work_id else True
    if lock is None:
        return {"schema": SCHEMA, "work_id": work_id, "verification_status": "BLOCKED",
                "criterion_evidence": "UNPROVEN",
                "blockers": ["another verify of this work item is running; nothing was run"]}, 1
    try:
        return _verify(cwd, only)
    finally:
        if lock is not True:
            lock.close()


def _verify(cwd=None, only=None):
    """Run every criterion recipe and bind the exit codes to the exact HEAD.

    `only` (criterion ids) runs a subset for diagnosis. A subset is PARTIAL: it never
    sets verification_status or verified_head, so it can never stand in for a PASS."""
    ident, root, err = _require_tree(cwd)
    if err:
        return err
    st = status(cwd)
    if st["contract_status"] != "LOCKED":
        if st.get("work_id") and root:
            _withdraw(_work_dir(root, st["work_id"]), "BLOCKED", "UNPROVEN")
        return {"schema": SCHEMA, "verification_status": "BLOCKED",
                "contract_status": st["contract_status"],
                "reason": "a contract that is %s cannot be verified; only a LOCKED "
                          "finish line can be proven" % st["contract_status"],
                "reasons": st["reasons"]}, 1

    work_id = st["work_id"]
    wdir = _work_dir(root, work_id)
    contract = _read_json(os.path.join(wdir, "contract.json")) or {}
    head = ident.get("head")

    # A dirty or unmeasurable tree cannot bind evidence, so say so BEFORE running recipes
    # that can take an hour, not after them (audit 02/10/2026).
    if _product_dirt(ident):
        # A refused verify is newer evidence that the last proof no longer holds: withdraw it, so
        # cleaning the tree cannot bring an old PASS back without a fresh full run (review r3).
        _withdraw(wdir, "BLOCKED", "UNPROVEN")
        return {"schema": SCHEMA, "work_id": work_id, "head": head,
                "verification_status": "BLOCKED", "criterion_evidence": "UNPROVEN",
                "blockers": ["working tree is dirty or could not be measured (outside "
                             ".claude/done) - commit first; nothing was run"]}, 1
    criteria = contract.get("criteria") or []
    if only:
        known = {c.get("id") for c in criteria}
        missing = [i for i in only if i not in known]
        if missing:
            return {"error": "unknown criterion id(s): %s" % ", ".join(missing),
                    "known": sorted(k for k in known if k)}, 2
        criteria = [c for c in criteria if c.get("id") in only]

    matrix = []
    for c in criteria:
        cid = c.get("id") or "<no id>"
        required = bool(c.get("required", True))
        recipe = _c_recipe(c)
        if not recipe:
            oracle = _c_oracle(c)
            matrix.append({"id": cid, "required": required, "evidence": "UNPROVEN",
                           "oracle": oracle or None,
                           "reason": ("has an oracle but no machine-runnable recipe; a "
                                      "human or agent must run it and record the result")
                                     if oracle else
                                     "no recipe - nothing can measure this criterion"})
            continue
        if _c_timeout(c) is None:  # a contract locked by an older donectl; never run unbounded
            matrix.append({"id": cid, "required": required, "evidence": "FAILED", "recipe": recipe,
                           "exit_code": 2, "reason": "invalid timeout %r in the locked contract; "
                           "revise it (1-%d s)" % (c.get("timeout"), MAX_CRITERION_TIMEOUT)})
            continue
        started = time.monotonic()
        rc, out = _run(recipe, cwd=ident.get("git_root"), timeout=_c_timeout(c))
        matrix.append({"id": cid, "required": required,
                       "evidence": "PROVEN" if rc == 0 else "FAILED",
                       "recipe": recipe, "exit_code": rc, "timeout_s": _c_timeout(c),
                       "duration_s": round(time.monotonic() - started, 1),
                       "output_digest": sha256_bytes(out.encode("utf-8", "replace")),
                       "output_log": _evidence_log(work_id, head, cid, out),
                       "output_tail": out[-REPORT_TAIL:]})

    # The tree must be the one measured at the start: a commit (autogit) or an edit
    # landing mid-run means later recipes measured something the verdict does not bind to.
    after = identity(cwd)
    moved = after.get("head") != head or _product_dirt(after) != 0
    # A recipe that rewrote a pinned file (its own script included) measured bytes the lock
    # never agreed. status() catches it on the next read; this catches it in THIS verdict.
    lock_rec = _read_json(os.path.join(wdir, "lock.json")) or {}
    pins_moved = bool(lock_rec.get("recipe_pins") is not None and
                      _pin_problem(lock_rec, recipe_pins(root, wdir, contract)))
    moved = moved or pins_moved

    if only:
        state = _read_json(os.path.join(wdir, "state.json")) or _fresh_state()
        state["last_partial"] = {"head": head, "at_utc": utc(), "ids": list(only), "matrix": matrix,
                                 "tree_moved": moved}
        ok = not moved and all(m["evidence"] == "PROVEN" for m in matrix)
        _write_json(os.path.join(wdir, "state.json"), state)
        if not ok:  # newer evidence contradicts any earlier PASS: withdraw it until a full verify
            failed = any(m["evidence"] == "FAILED" and m["required"] for m in matrix)
            _withdraw(wdir, "FAIL" if failed else "NOT_RUN", "FAILED" if failed else "UNPROVEN")
        return {"schema": SCHEMA, "work_id": work_id, "observed_at_utc": utc(), "head": head,
                "verification_status": "PARTIAL",
                "note": "a subset run proves nothing about Done; run `verify` with no ids for that",
                "subset_result": "PROVEN" if ok else "FAILED", "tree_moved": moved,
                "matrix": matrix}, (0 if ok else 1)

    required = [m for m in matrix if m["required"]]
    blockers = []
    if not required:
        vstatus, cev = "BLOCKED", "UNPROVEN"
        blockers.append("no required criteria to prove")
    elif any(m["evidence"] == "FAILED" for m in required):
        vstatus, cev = "FAIL", "FAILED"
    elif any(m["evidence"] == "UNPROVEN" for m in required):
        vstatus, cev = "BLOCKED", "UNPROVEN"
        blockers.append("a required criterion has no recipe")
    else:
        vstatus, cev = "PASS", "PROVEN"

    # Evidence must bind to a revision. A tree that moved while recipes ran is not one.
    product_dirty = 1 if moved else 0
    if moved:
        if vstatus == "PASS":
            vstatus, cev = "BLOCKED", "UNPROVEN"
        if pins_moved:
            blockers.append("a recipe file under .claude/done changed while recipes ran - "
                            "evidence does not bind to the verifier agreed at lock")
        blockers.append("the tree moved while recipes ran (HEAD %s -> %s, or new dirt) - "
                        "evidence does not bind to one revision" % ((head or "?")[:9],
                                                                    (after.get("head") or "?")[:9]))

    state = _read_json(os.path.join(wdir, "state.json")) or _fresh_state()
    state.update({"criterion_evidence": cev, "verification_status": vstatus,
                  "verified_head": head if not product_dirty else None,
                  "updated_at_utc": utc(),
                  "last_verify": {"head": head, "at_utc": utc(), "matrix": matrix,
                                  "blockers": blockers}})
    _write_json(os.path.join(wdir, "state.json"), state)

    return {"schema": SCHEMA, "work_id": work_id, "observed_at_utc": utc(),
            "head": head, "verification_status": vstatus, "criterion_evidence": cev,
            "blockers": blockers, "matrix": matrix}, (0 if vstatus == "PASS" else 1)


def refresh(cwd=None):
    """Re-observe truth and drop any revision-bound claim the revision no longer supports."""
    ident, root, err = _require_tree(cwd)
    if err:
        return err
    work_id = _active_work(root, ident)
    if not work_id:
        return {"error": "no active work item mapped to this branch/worktree"}, 1
    lock = _verify_lock(work_id)  # a refresh must not interleave with a verify (review r5)
    if lock is None:
        return {"error": "a verify of this work item is running; refresh after it finishes",
                "work_id": work_id}, 1
    try:
        return _refresh(cwd, ident, root, work_id)
    finally:
        if lock is not True:
            lock.close()


def _refresh(cwd, ident, root, work_id):
    wdir = _work_dir(root, work_id)
    state = _read_json(os.path.join(wdir, "state.json")) or _fresh_state()
    head = ident.get("head")
    stale = []
    if state.get("verified_head") and state["verified_head"] != head:
        stale.append("verification was bound to %s but HEAD is %s"
                     % (state["verified_head"][:9], (head or "?")[:9]))
        state.update({"criterion_evidence": "UNPROVEN", "verification_status": "NOT_RUN",
                      "verified_head": None})
    pd = _product_dirt(ident)
    if pd:
        stale.append("working tree is dirty or unmeasurable (%d entries outside .claude/done)" % pd)
    if status(cwd)["contract_status"] != "LOCKED":
        stale.append("the contract is no longer LOCKED as agreed")
    state["updated_at_utc"] = utc()
    _write_json(os.path.join(wdir, "state.json"), state)
    if pd or status(cwd)["contract_status"] != "LOCKED":
        _withdraw(wdir)
    return {"schema": SCHEMA, "work_id": work_id, "head": head,
            "marked_stale": stale, "state": status(cwd)}, 0


def revise(goal, cwd=None):
    """Supersede the current contract with a new version. Never edits the locked one."""
    ident, root, err = _require_tree(cwd)
    if err:
        return err
    if not goal or not goal.strip():
        return {"error": 'a goal is required: revise "<what changed and what done now means>"'}, 2
    prev = _active_work(root, ident)
    version = 1
    if prev:
        pc = _read_json(os.path.join(_work_dir(root, prev), "contract.json")) or {}
        version = int(pc.get("version") or 1) + 1
    work_id, wdir, contract = _new_work(root, ident, goal, supersedes=prev, version=version)
    return {"schema": SCHEMA, "work_id": work_id, "contract_status": "DRAFT",
            "version": version, "supersedes": prev,
            "note": "the superseded contract is left intact on disk; it is never edited",
            "contract_path": os.path.join(wdir, "contract.json"),
            "next": CRITERION_HINT}, 0


def note(text, cwd=None):
    """Append a progress note stamped from the clock and git, never from the text.

    Hand-typed progress times were wrong twice in one session (20/10/2026). A note is
    bookkeeping, not evidence: it changes no state dimension and proves nothing."""
    if not text or not text.strip():
        return {"error": 'note text is required: note "<what happened>"'}, 2
    ident, root, err = _require_tree(cwd)
    if err:
        return err
    work_id = _active_work(root, ident)
    if not work_id:
        return {"error": "no active work item mapped to this branch/worktree"}, 1
    entry = {"at_utc": utc(), "head": ident.get("head"), "branch": ident.get("branch"),
             "dirty_count_product": ident.get("dirty_count_product"), "text": text.strip()}
    with open(os.path.join(_work_dir(root, work_id), "notes.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, sort_keys=True) + "\n")
    return dict(entry, schema=SCHEMA, work_id=work_id), 0


def resume(cwd=None):
    """Re-observe real state and replay the last recorded proof, without re-running it."""
    ident, root, err = _require_tree(cwd)
    if err:
        return err
    st = status(cwd)
    work_id = st.get("work_id")
    last = None
    if work_id:
        state = _read_json(os.path.join(_work_dir(root, work_id), "state.json")) or {}
        last = state.get("last_verify")
    _pd = _product_dirt(ident)
    # verified_head is withdrawn when newer evidence (a failing partial run) contradicts the last proof
    replayable = bool(last and last.get("head") == ident.get("head") and not _pd
                      and state.get("verified_head") == ident.get("head")
                      and st.get("contract_status") == "LOCKED")
    return {"schema": SCHEMA, "observed_at_utc": utc(), "work_id": work_id,
            "state": st,
            "last_verify": last,
            "replayable": replayable,
            "note": ("the recorded proof binds to the current HEAD" if replayable else
                     "no proof binds to the current HEAD - run `verify`")}, 0


def explain(cwd=None):
    """Plain-language account of the current contract. No adjectives, only what is measured."""
    ident, root, err = _require_tree(cwd)
    if err:
        return err
    st = status(cwd)
    work_id = st.get("work_id")
    if not work_id:
        return {"schema": SCHEMA, "contract_status": st["contract_status"],
                "plain": ["There is no active work item for this branch and worktree.",
                          'Nothing is being tracked as Done. Run start "<goal>" to open one.'],
                "reasons": st["reasons"]}, 0
    wdir = _work_dir(root, work_id)
    contract = _read_json(os.path.join(wdir, "contract.json")) or {}
    state = _read_json(os.path.join(wdir, "state.json")) or {}
    criteria = contract.get("criteria") or []

    plain = ["Goal: %s" % (contract.get("goal") or "(none recorded)"),
             "Contract %s, version %s, status %s."
             % (work_id, contract.get("version"), st["contract_status"]),
             "Done means all %d criteria below hold; it is NOT done if any fails or "
             "cannot be measured." % len(criteria)]
    for c in criteria:
        plain.append("  [%s] %s  (proven by: %s)"
                     % (c.get("id") or "?", _c_text(c) or "(no text)",
                        _c_recipe(c) or (("oracle (not machine-run): " + _c_oracle(c))
                                         if _c_oracle(c) else
                                         "NOTHING - unmeasurable as written")))
    plain.append("Verification is %s; criterion evidence is %s; delivery is %s."
                 % (st["verification_status"], st["criterion_evidence"], st["delivery_status"]))
    if state.get("verified_head"):
        plain.append("Evidence binds to revision %s." % state["verified_head"][:9])
    else:
        plain.append("No evidence is bound to any revision.")
    for r in st["reasons"]:
        plain.append("Note: %s" % r)
    return {"schema": SCHEMA, "work_id": work_id, "plain": plain, "state": st}, 0


def doctor(cwd=None):
    """Harness self-test plus the enforcement status the self-test cannot see."""
    out, rc = selftest(cwd)
    settings = os.path.join(os.path.expanduser("~"), ".claude", "settings.json")
    wired, detail = False, "settings.json not readable"
    try:
        with open(settings, encoding="utf-8") as f:
            raw = f.read()
        wired = "mutation-gate" in raw or "donectl" in raw
        detail = ("mutation gate is registered in settings.json" if wired else
                  "mutation gate is NOT registered in settings.json - donectl measures, "
                  "but nothing consults it before a write")
    except Exception as e:  # noqa: BLE001
        detail = "%s: %s" % (type(e).__name__, e)
    out["hook_wired"] = wired
    out["hook_detail"] = detail
    out["enforcement_effective"] = bool(wired) and out.get("enforcement") == "ENFORCED"
    if not wired:
        out["enforcement"] = "ENFORCEMENT_UNPROVEN"
    return out, rc


# --------------------------------------------------------------------------- main
# Every documented operation dispatches here. A name that /done documents and this
# table does not implement is a lie the harness tells about itself, so the two lists
# are kept identical on purpose.
NULLARY = {
    "identity": lambda: (identity(), 0),
    "status": lambda: (status(), 0),
    "integrity": integrity,
    "selftest": selftest,
    "doctor": doctor,
    "init": init,
    "lock": lock,
    "verify": verify,
    "refresh": refresh,
    "resume": resume,
    "explain": explain,
}
UNARY = {"start": start, "revise": revise, "note": note}


def main(argv):
    # Help must be read-only, before any dispatch (including mutators).
    if any(arg in ("-h", "--help") for arg in argv[1:]):
        print(__doc__)
        return 0
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd = argv[1]

    if cmd == "verify" and len(argv) > 2:
        out, rc = verify(only=[a for a in argv[2:] if a])
        print(json.dumps(out, indent=2))
        return rc

    if cmd in ("criteria", "contract"):
        out, rc = _authoring_cli(argv[1:])
        print(json.dumps(out, indent=2))
        return rc

    if cmd in NULLARY:
        out, rc = NULLARY[cmd]()
        print(json.dumps(out, indent=2))
        return rc

    if cmd in UNARY:
        # Accept both `start "a goal"` and `start a goal` - a quoting slip must not
        # silently open a work item whose goal is one word.
        goal = " ".join(a for a in argv[2:] if a is not None).strip()
        out, rc = UNARY[cmd](goal)
        print(json.dumps(out, indent=2))
        return rc

    if cmd == "preflight":
        payload = json.loads(argv[3]) if len(argv) > 3 else {}
        print(json.dumps(preflight(argv[2] if len(argv) > 2 else "Write", payload), indent=2))
        return 0

    print(json.dumps({"error": f"unknown subcommand: {cmd}",
                      "known": sorted(list(NULLARY) + list(UNARY) + ["preflight", "criteria", "contract"])}, indent=2))
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
