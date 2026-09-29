#!/usr/bin/env python3
"""ci_mirror — run what GitHub will run on a pull request, locally, before anything is pushed.

WHY (founder, 19/09/2026): PR #782 reached Phill with a red "Smoke Surface Gate" after the
local gate reported 26/26 green. The local gate mirrored ONE workflow (ci.yml); ten other
pull_request workflows were never run before push. RestoreAssist carried the same gap as a
manual skill (ci-quality-parity) that sessions forgot to invoke. A subset that is chosen by
the session will always drift from the set GitHub enforces.

So this enumerates the set GitHub enforces, mechanically:

    every workflow whose `on:` includes pull_request / pull_request_target,
    whose branch and paths filters match this change,
    every job, every step.

Each step ends as exactly one of:
    PASS                     ran, exit 0
    FAIL                     ran and failed, OR could not be run and is not exempted
    SKIP-filter              GitHub would not run it for this change (paths/branches/if:)
    SKIP-setup               checkout / setup-* / cache / dependency install (provisioned locally)
    SKIP-exempt              listed in .github/ci-mirror.exempt.json WITH a reason
    SKIP-test-gap            exempted AND it runs tests; allowed only with "test_gap": true, counted
    WARN-runtime             the pinned Node/Python is not installed here; later steps ran on
                             the local version, and the report names both

A step that cannot run here (a secret, a service container, a third-party action, an
expression this runner cannot resolve) is a FAIL until someone exempts it in writing.
Silence is never a pass.

    python3 ci_mirror.py [--repo DIR] [--base REF] [--json OUT]
Exit 0 only when no step FAILs. The JSON result is what pr_release_gate binds to the head.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import shlex
import subprocess
import sys
import traceback
import tempfile
import time
from pathlib import Path

import yaml

STATE = Path.home() / ".local" / "state" / "pr-release-gate" / "ci-mirror"
EXEMPT_FILE = ".github/ci-mirror.exempt.json"
# Exemptions for repos whose tree we should not edit just to run a local mirror, keyed by
# owner__repo. Reviewed with this skill, same reason rule as the in-repo file.
GLOBAL_EXEMPT_DIR = Path(__file__).resolve().parent.parent / "ci-mirror-exempt"
SETUP_USES = ("actions/checkout", "actions/setup-node", "actions/setup-python", "actions/cache",
              "actions/upload-artifact", "actions/download-artifact", "pnpm/action-setup",
              "actions/setup-java", "actions/setup-go", "astral-sh/setup-uv")
SETUP_LINE = re.compile(
    r"^(npm (ci|install)|pnpm (install|i)\b|yarn( install)?$|corepack enable|"
    r"(python3? -m )?pip3? install|npx playwright install|pnpm exec playwright install|"
    r"python3? -m pip install|uv (sync|pip install)|echo\b|set -[a-z]+$|cd\b)")
EXPR = re.compile(r"\$\{\{\s*(.*?)\s*\}\}")
DEFAULT_SHELL = ["bash", "--noprofile", "--norc", "-eo", "pipefail"]


class Unrunnable(Exception):
    """This step cannot be executed faithfully here."""


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                          check=True).stdout.strip()


def glob_re(pattern: str) -> re.Pattern:
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif pattern.startswith("**", i):
            out, i = out + ".*", i + 2
        elif pattern[i] == "*":
            out, i = out + "[^/]*", i + 1
        elif pattern[i] == "?":
            out, i = out + "[^/]", i + 1
        else:
            out, i = out + re.escape(pattern[i]), i + 1
    return re.compile(out + "$")


def filter_matches(patterns: list[str], candidates: list[str]) -> bool:
    """GitHub semantics: later patterns override earlier; `!` negates."""
    for cand in candidates:
        keep = False
        for pat in patterns:
            neg = pat.startswith("!")
            if glob_re(pat[1:] if neg else pat).match(cand):
                keep = not neg
        if keep:
            return True
    return False


def pr_trigger(wf: dict) -> dict | None:
    on = wf.get("on", wf.get(True))
    if isinstance(on, str):
        on = {on: None}
    if isinstance(on, list):
        on = {k: None for k in on}
    if not isinstance(on, dict):
        return None
    for key in ("pull_request", "pull_request_target"):
        if key in on:
            return on[key] or {}
    return None


def workflow_applies(trig: dict, changed: list[str], base_branch: str) -> str | None:
    """Return None when the workflow runs for this change, else the reason it would not."""
    branches = trig.get("branches")
    if branches and not filter_matches(list(branches), [base_branch]):
        return f"branches filter excludes {base_branch}"
    if trig.get("paths") and not filter_matches(list(trig["paths"]), changed):
        return "paths filter matches no changed file"
    ignore = trig.get("paths-ignore")
    if ignore and all(filter_matches(list(ignore), [c]) for c in changed):
        return "every changed file is paths-ignored"
    return None


class Ctx:
    """Resolves `${{ }}` expressions the way a pull_request run would see them."""

    def __init__(self, root: Path, base: str, head: str, branch: str, base_branch: str):
        self.values = {
            "github.event_name": "pull_request", "github.sha": head, "github.head_ref": branch,
            "github.base_ref": base_branch, "github.ref": f"refs/pull/0/merge",
            "github.workspace": str(root), "github.event.pull_request.base.sha": base,
            "github.event.pull_request.head.sha": head,
            "github.event.pull_request.head.ref": branch,
            "github.event.pull_request.base.ref": base_branch, "runner.os": "macOS",
            "runner.environment": "self-hosted",  # this Mac is one; github-hosted steps skip
            # runner.temp is fresh per run, as each GitHub job's is
            "runner.temp": tempfile.mkdtemp(prefix="ci-mirror-runner-temp-"),
            "github.repository_owner": "CleanExpo",
        }
        slug = repo_slug(root).replace("__", "/")
        self.values.update({"github.repository": slug, "github.actor": "local-mirror",
                            "github.event.pull_request.head.repo.full_name": slug,
                            "github.event.pull_request.base.repo.full_name": slug})
        self.values.update(repo_variables(root))
        self.env: dict[str, str] = {}
        self.matrix: dict[str, object] = {}
        self.outputs: dict[str, dict[str, str]] = {}
        self.job_failed = False

    def lookup(self, name: str) -> str:
        if name in self.values:
            return self.values[name]
        if name.startswith("env."):
            return self.env.get(name[4:], "")
        if name.startswith("matrix."):
            return str(self.matrix.get(name[7:], ""))
        m = re.fullmatch(r"steps\.([\w-]+)\.outputs\.([\w-]+)", name)
        if m:
            return self.outputs.get(m.group(1), {}).get(m.group(2), "")
        raise Unrunnable(f"cannot resolve ${{{{ {name} }}}} locally")

    def sub(self, text: str) -> str:
        def one(m: re.Match) -> str:
            expr = m.group(1)
            fallback = re.fullmatch(r"([\w.-]+)\s*\|\|\s*'([^']*)'", expr)
            if fallback:
                name, literal = fallback.groups()
                if name.startswith("secrets."):
                    return literal
                try:
                    return self.lookup(name) or literal
                except Unrunnable:
                    return literal
            if expr.startswith("vars.") and (expr in self.values or "vars.__listed__" in self.values):
                return self.values.get(expr, "")
            if re.search(r"\b(secrets|vars)\.", expr):
                raise Unrunnable(f"needs a repository secret/variable: {expr}")
            if not re.fullmatch(r"[\w.-]+", expr):
                raise Unrunnable(f"expression too complex to mirror: {expr}")
            return self.lookup(expr)
        return EXPR.sub(one, str(text))

    def condition(self, cond) -> bool:
        """True when GitHub would run it. Unknown conditions run (a false red beats a false green)."""
        if cond is None:
            return not self.job_failed
        c = str(cond).strip()
        c = EXPR.sub(lambda m: m.group(1), c)
        # GitHub ANDs an implicit success() onto any condition with no status function.
        if not re.search(r"\b(always|success|failure|cancelled)\(\)", c) and self.job_failed:
            return False
        c = re.sub(r"\bfailure\(\)", str(self.job_failed), c)
        c = re.sub(r"\bcancelled\(\)", "False", c)
        c = re.sub(r"\bsuccess\(\)", str(not self.job_failed), c)
        def resolve(m: re.Match) -> str:
            try:
                return repr(self.lookup(m.group(0)))
            except Unrunnable:
                return m.group(0)
        c = re.sub(r"\b(?:github|steps|env|matrix|runner)(?:\.[\w-]+)+", resolve, c)
        c = c.replace("&&", " and ").replace("||", " or ").replace("!=", " __NE__ ")
        c = re.sub(r"!(?!=)", " not ", c).replace("__NE__", "!=")
        c = re.sub(r"\balways\(\)", "True", c)
        try:
            return bool(eval(c, {"__builtins__": {}}, {"true": True, "false": False}))
        except Exception:
            return True


def is_setup(step: dict) -> bool:
    uses = str(step.get("uses", ""))
    if uses:
        return uses.split("@")[0] in SETUP_USES
    lines = [ln.strip() for ln in str(step.get("run", "")).splitlines()]
    lines = [ln for ln in lines if ln and not ln.startswith("#")]
    return bool(lines) and all(SETUP_LINE.match(ln) for ln in lines)


def repo_slug(root: Path) -> str:
    try:
        url = git(root, "remote", "get-url", "origin")
    except subprocess.CalledProcessError:
        return ""
    m = re.search(r"[:/]([^/:]+)/([^/]+?)(?:\.git)?$", url)
    return f"{m.group(1)}__{m.group(2)}" if m else ""


def repo_variables(root: Path) -> dict[str, str]:
    """Repository Actions VARIABLES (vars.*), which are not secret. Workflows gate jobs on
    them (e.g. vars.E2E_ENABLED), so guessing them would run or skip the wrong jobs."""
    proc = subprocess.run(["gh", "variable", "list", "--json", "name,value"], cwd=root,
                          capture_output=True, text=True)
    if proc.returncode != 0:
        return {}
    found = {f"vars.{v['name']}": str(v.get("value", "")) for v in json.loads(proc.stdout or "[]")}
    found["vars.__listed__"] = "1"
    return found


NODE_INSTALL = re.compile(r"\b(npm (ci|install)|pnpm (install|i)\b|yarn( install)?\b)")


def needs_install(step: dict, job: dict, wf: dict, root: Path, ctx: "Ctx") -> bool:
    """A Node install step is skipped only when its directory already has node_modules;
    otherwise every later step in that package fails with 'command not found'."""
    run = str(step.get("run", ""))
    if not NODE_INSTALL.search(run):
        return False
    wd = step.get("working-directory") or ((job.get("defaults") or {}).get("run") or {}).get(
        "working-directory") or ((wf.get("defaults") or {}).get("run") or {}).get("working-directory")
    target = root / ctx.sub(wd) if wd else root
    for line in run.splitlines():
        m = re.match(r"\s*cd\s+(\S+)", line)
        if m:
            target = target / m.group(1)
    return not (target / "node_modules").is_dir()


def load_exemptions(root: Path) -> list[dict]:
    entries: list[dict] = []
    for path in (root / EXEMPT_FILE, GLOBAL_EXEMPT_DIR / f"{repo_slug(root)}.json"):
        if not path.is_file():
            continue
        for e in json.loads(path.read_text()).get("exempt", []):
            if not str(e.get("reason", "")).strip():
                raise SystemExit(f"{path}: every exemption needs a reason: {e}")
            entries.append({**e, "source": str(path)})
    return entries


def exemption_entry(exempts: list[dict], wf: str, job: str, step: str) -> dict | None:
    for e in exempts:
        if e.get("workflow") == wf and e.get("job", "*") in ("*", job) and \
                e.get("step", "*") in ("*", step):
            return e
    return None


def exemption_for(exempts: list[dict], wf: str, job: str, step: str) -> str | None:
    e = exemption_entry(exempts, wf, job, step)
    return e["reason"] if e else None


# A step that exercises code. Exempting one means the mirror never ran the tests it
# claims to mirror (review of 1d17806: Unite-Group's spine `Test` step was exempted and
# the mirror still said PASS). That is allowed only as a DECLARED gap -- the entry says
# `"test_gap": true` -- and every such gap is counted in the verdict line.
TEST_STEP = re.compile(r"\b(?:test|tests|jest|vitest|pytest|playwright|mocha|tsc|type-?check"
                       r"|lint|eslint|ruff|e2e)\b", re.IGNORECASE)


def runs_tests(step: dict, name: str) -> bool:
    return bool(TEST_STEP.search(name) or TEST_STEP.search(str(step.get("run") or "")))


def skipped_is_gap(entry: dict, steps: list[tuple[dict, str]]) -> bool:
    """A skip is a counted gap if the entry declares one or the step visibly runs tests.

    The declaration counts on its own: the detector is a pattern, and on 24/09/2026 it
    missed `& python ...test_estate_sync.py` inside a pwsh step, so a declared gap was
    reported as test_gaps=0.
    """
    return entry.get("test_gap") is True or any(runs_tests(st, n) for st, n in steps)


def exemption_problem(entry: dict, steps: list[tuple[dict, str]]) -> str | None:
    """Why this exemption may not skip these steps, or None."""
    if entry.get("test_gap") is True:
        return None
    hit = next((n for st, n in steps if runs_tests(st, n)), None)
    if hit is None:
        return None
    return (f"exemption skips {hit!r}, which runs tests; declare it with "
            f'"test_gap": true or run it ({entry.get("source", "exemption file")})')


def major(version: str) -> str:
    m = re.search(r"(\d+)", str(version))
    return m.group(1) if m else ""


NODE_DIRS = [Path.home() / ".nvm" / "versions" / "node", Path.home() / ".local" / "share" / "node"]


def _shim(target: Path, names: tuple[str, ...]) -> Path:
    shim = Path(tempfile.mkdtemp(prefix="ci-mirror-rt-"))
    for n in names:
        (shim / n).symlink_to(target)
    return shim


def _version_of(binary: str, env: dict) -> subprocess.CompletedProcess:
    """`<binary> --version`, or an empty result when the binary is not on PATH.

    Not installed and not even present under that NAME are the same fact to this
    function, and neither is fatal -- the caller's whole job is to return a WARN note and
    let the step run on whatever this machine has.

    Before 2026-09-23 this was a bare subprocess.run, so a missing binary raised
    FileNotFoundError out of check_runtime, out of run_steps, out of run_job and out of
    main(). On this MacBook `python3` exists and `python` does not, so the ENTIRE mirror
    died on `python --version` -- and because no report was written, the release gate
    reported "a GitHub PR check would fail on this head", a verdict it had never reached.
    One absent binary was rendered as a failing pull request.
    """
    try:
        return subprocess.run([binary, "--version"], capture_output=True, text=True, env=env)
    except (FileNotFoundError, OSError):
        return subprocess.CompletedProcess([binary, "--version"], 127, "", "")


def _version_matches(have: str, need: str) -> bool:
    """3.11 matches 3.11.4; 3.11.1 matches 3.11.1 but never 3.11.10."""
    return have == need or have.startswith(need + ".")


def _reports(exe: Path, need: str, env: dict) -> bool:
    """True when `exe --version` runs and reports the pinned version."""
    got = _version_of(str(exe), env)
    got_v = (got.stdout or got.stderr).split()[-1] if (got.stdout or got.stderr) else ""
    return got.returncode == 0 and _version_matches(got_v, need)


def check_runtime(step: dict, ctx: Ctx, env: dict) -> str | None:
    """Put the pinned runtime first on PATH when installed. Returns a WARN note when it is not:
    the step then runs on the runtime this machine has, and the report says so."""
    uses = str(step.get("uses", "")).split("@")[0]
    want = (step.get("with") or {})
    if uses == "actions/setup-node" and want.get("node-version"):
        need = major(ctx.sub(want["node-version"]))
        have = _version_of("node", env).stdout
        if need and major(have) != need:
            hits = sorted(p for d in NODE_DIRS if d.is_dir() for p in d.glob(f"v{need}.*"))
            if not hits:
                return f"workflow pins Node {need}; none installed, ran on {have.strip()}"
            env["PATH"] = f"{hits[-1] / 'bin'}:{env['PATH']}"
    if uses == "actions/setup-python" and want.get("python-version"):
        need = str(ctx.sub(want["python-version"])).strip().rstrip(".x")
        have = _version_of("python", env)
        have_v = (have.stdout or have.stderr).split()[-1] if (have.stdout or have.stderr) else ""
        if need and not _version_matches(have_v, need):
            # A bare interpreter has none of the job's packages (its install step is
            # SKIP-setup), so a provisioned `.venv-py<version>` in the repo wins.
            # Its own interpreter must report the pinned version: a stale or mislabelled
            # venv would otherwise stand in for the runtime the workflow asked for.
            pinned_venv = Path(env.get("GITHUB_WORKSPACE", "")) / f".venv-py{need}" / "bin"
            if all(_reports(pinned_venv / name, need, env) for name in ("python", "python3")):
                env["PATH"] = f"{pinned_venv}:{env['PATH']}"
                return None
            exe = subprocess.run(["which", f"python{need}"], capture_output=True, text=True,
                                 env=env).stdout.strip()
            if not exe:
                return f"workflow pins Python {need}; none installed, ran on {have_v}"
            env["PATH"] = f"{_shim(Path(exe), ('python', 'python3'))}:{env['PATH']}"
    return None


# GNU `timeout`, which every ubuntu runner has and macOS does not. Without it a
# workflow step fails with 127 here and passes on GitHub. Exit 124 on expiry, as GNU.
TIMEOUT_SHIM = """#!/usr/bin/env python3
import os, re, signal, subprocess, sys
args = sys.argv[1:]
sig, kill_after, preserve = signal.SIGTERM, None, False
def secs(v):
    m = re.fullmatch(r"([0-9.]+)([smhd]?)", v)
    return float(m.group(1)) * {"": 1, "s": 1, "m": 60, "h": 3600, "d": 86400}[m.group(2)]
while args and args[0].startswith("-"):
    a = args.pop(0)
    if a in ("-s", "--signal"):
        v = args.pop(0); sig = getattr(signal, v if v.startswith("SIG") else "SIG" + v, None) or int(v)
    elif a.startswith("--signal="):
        v = a.split("=", 1)[1]; sig = getattr(signal, v if v.startswith("SIG") else "SIG" + v, None) or int(v)
    elif a in ("-k", "--kill-after"):
        kill_after = secs(args.pop(0))
    elif a.startswith("--kill-after="):
        kill_after = secs(a.split("=", 1)[1])
    elif a == "--preserve-status":
        preserve = True
    elif a in ("--foreground", "-v", "--verbose"):
        pass
    elif a == "--":
        break
duration, cmd = secs(args[0]), args[1:]
proc = subprocess.Popen(cmd)
try:
    sys.exit(proc.wait(timeout=duration or None))
except subprocess.TimeoutExpired:
    proc.send_signal(sig)
    try:
        rc = proc.wait(timeout=kill_after)
    except subprocess.TimeoutExpired:
        proc.kill(); rc = proc.wait()
    sys.exit((128 - rc if rc < 0 else rc) if preserve else 124)
"""


def timeout_shim() -> Path | None:
    if subprocess.run(["which", "timeout"], capture_output=True).returncode == 0:
        return None
    d = Path(tempfile.mkdtemp(prefix="ci-mirror-timeout-"))
    (d / "timeout").write_text(TIMEOUT_SHIM)
    (d / "timeout").chmod(0o755)
    return d


def base_env(root: Path, ctx: Ctx, files: dict[str, Path]) -> dict:
    path = os.environ.get("PATH", "/usr/bin:/bin")
    shim = timeout_shim()
    if shim:
        path = f"{shim}:{path}"
    venv = root / ".venv" / "bin"
    if venv.is_dir():
        path = f"{venv}:{path}"
    # An empty HOME per job, as a runner has. With the real one, a test that read
    # ~/.claude passed here because this Mac's ~/.claude IS the repo, then failed on the
    # Mini runner (25/09/2026: test_find_cred, test_check_memory_index).
    home = tempfile.mkdtemp(prefix="ci-mirror-home-")
    env = {"HOME": home, "PATH": path, "TERM": "dumb", "CI": "true",
           "GITHUB_ACTIONS": "true", "GITHUB_WORKSPACE": str(root),
           "GITHUB_EVENT_NAME": "pull_request", "GITHUB_SHA": ctx.values["github.sha"],
           "GITHUB_BASE_REF": ctx.values["github.base_ref"],
           "GITHUB_HEAD_REF": ctx.values["github.head_ref"],
           "RUNNER_TEMP": ctx.values["runner.temp"], "RUNNER_OS": "macOS",
           "GITHUB_REPOSITORY": ctx.values["github.repository"],
           "GITHUB_REPOSITORY_OWNER": ctx.values["github.repository"].split("/")[0],
           "GITHUB_ACTOR": ctx.values["github.actor"], "GITHUB_REF": ctx.values["github.ref"],
           "GITHUB_SERVER_URL": "https://github.com", "GITHUB_RUN_ID": "0",
           "GITHUB_RUN_NUMBER": "0", "GITHUB_RUN_ATTEMPT": "1",
           # a step that runs a mirror (the release gate's own tests do) is part of THIS run
           "CI_MIRROR_NESTED": "1"}
    env.update({k: str(v) for k, v in files.items()})
    return env


def read_kv_file(path: Path) -> dict[str, str]:
    """Parse GITHUB_ENV / GITHUB_OUTPUT, including KEY<<DELIM heredocs."""
    out, lines = {}, path.read_text().splitlines() if path.exists() else []
    i = 0
    while i < len(lines):
        line = lines[i]
        if "<<" in line and "=" not in line.split("<<")[0]:
            key, delim = line.split("<<", 1)
            buf, i = [], i + 1
            while i < len(lines) and lines[i] != delim:
                buf.append(lines[i])
                i += 1
            out[key] = "\n".join(buf)
        elif "=" in line:
            key, val = line.split("=", 1)
            out[key] = val
        i += 1
    return out


def run_step(step: dict, job: dict, wf: dict, root: Path, ctx: Ctx, job_env: dict,
             files: dict[str, Path], timeout_s: int) -> tuple[str, str]:
    step_env = {k: ctx.sub(v) for k, v in (step.get("env") or {}).items()}
    env = {**job_env, **step_env}
    wd = step.get("working-directory") or ((job.get("defaults") or {}).get("run") or {}).get(
        "working-directory") or ((wf.get("defaults") or {}).get("run") or {}).get("working-directory")
    cwd = root / ctx.sub(wd) if wd else root
    script = ctx.sub(step["run"])
    shell = step.get("shell") or ((job.get("defaults") or {}).get("run") or {}).get("shell")
    pwsh = shell in ("pwsh", "powershell")
    if pwsh:
        # GitHub's own wrapper for `shell: pwsh`: stop on error, exit with the last code
        script = ("$ErrorActionPreference = 'stop'\n" + script +
                  "\nif ((Test-Path -LiteralPath variable:\\LASTEXITCODE)) { exit $LASTEXITCODE }\n")
    with tempfile.NamedTemporaryFile("w", suffix=".ps1" if pwsh else ".sh", delete=False) as fh:
        fh.write(script)
    if pwsh:
        cmd = ["pwsh", "-NoProfile", "-NonInteractive", "-Command", f". '{fh.name}'"]
    elif shell == "python":
        cmd = ["python3", fh.name]
    else:
        cmd = DEFAULT_SHELL + [fh.name]
    try:
        proc = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True,
                              timeout=timeout_s)
    except subprocess.TimeoutExpired:
        return "FAIL", f"timed out after {timeout_s}s"
    except FileNotFoundError:  # `finally` below is the only cleanup (round 20: a second
        # unlink here raised from `finally` and replaced this FAIL with a crash)
        return "FAIL", f"`{cmd[0]}` is not installed here, so this `shell: {shell}` step cannot run"
    finally:
        os.unlink(fh.name)
    job_env.update(read_kv_file(files["GITHUB_ENV"]))
    for extra in (files["GITHUB_PATH"].read_text().split() if files["GITHUB_PATH"].exists() else []):
        job_env["PATH"] = f"{extra}:{job_env['PATH']}"
    if step.get("id"):
        ctx.outputs[step["id"]] = read_kv_file(files["GITHUB_OUTPUT"])
    files["GITHUB_OUTPUT"].write_text("")
    tail = (proc.stdout + proc.stderr).strip().splitlines()[-25:]
    # stderr is appended after stdout, so a noisy stderr pushes the runner's own
    # count lines out of the tail. Pin them back in, stripped of colour codes.
    counts = [re.sub(r"\x1b\[[0-9;]*m", "", ln).strip()
              for ln in (proc.stdout + proc.stderr).splitlines()
              if re.search(r"Test Files |^\s*(\x1b\[[0-9;]*m)*\s*Tests |^# (tests|pass|fail|skipped) |^Ran \d+ tests?"
                           r"|^\s*(\x1b\[[0-9;]*m)*\s*\d+ (passed|failed|skipped|flaky|did not run)\b", ln)]
    if counts:
        tail = ["[counts] " + c for c in counts] + tail
    if proc.returncode != 0 and not step.get("continue-on-error"):
        # A 25-line tail is often all server noise; keep the whole output on disk.
        logs = STATE / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^A-Za-z0-9]+", "-", f"{wf.get('name', '')}-{step.get('name', '')}").strip("-")[:80]
        full = logs / f"{ctx.values['github.sha'][:12]}-{slug}.log"
        full.write_text(proc.stdout + "\n--- stderr ---\n" + proc.stderr)
        return "FAIL", f"exit {proc.returncode} (full output: {full})\n" + "\n".join(tail)
    # Keep the tail on PASS too: a passing step's counts ("Tests 1158 passed") are
    # the evidence a reviewer asks for, and a report with only a verdict can't give it.
    return "PASS", "\n".join(tail)


def start_services(job_id: str, job: dict, ctx: Ctx) -> list[str]:
    """Start each `services:` container with Docker, as the Actions runner does, and wait
    for its healthcheck. Raises Unrunnable with the reason when Docker cannot do it."""
    names: list[str] = []
    for sid, svc in (job.get("services") or {}).items():
        name = f"ci-mirror-{re.sub(r'[^a-z0-9]', '-', job_id.lower())}-{sid}-{os.getpid()}"
        args = ["docker", "run", "-d", "--rm", "--name", name]
        for k, v in (svc.get("env") or {}).items():
            args += ["-e", f"{k}={ctx.sub(v)}"]
        for port in svc.get("ports") or []:
            args += ["-p", str(port)]
        args += shlex.split(str(svc.get("options") or "")) + [ctx.sub(svc["image"])]
        proc = subprocess.run(args, capture_output=True, text=True, timeout=900)
        if proc.returncode != 0:
            stop_services(names)
            raise Unrunnable(f"service {sid} did not start: {proc.stderr.strip()[-300:]}")
        names.append(name)
        deadline = time.time() + 180
        while True:
            state = subprocess.run(
                ["docker", "inspect", "-f",
                 "{{if .State.Health}}{{.State.Health.Status}}{{else}}running{{end}}", name],
                capture_output=True, text=True).stdout.strip()
            if state in ("healthy", "running"):
                break
            if time.time() > deadline:
                stop_services(names)
                raise Unrunnable(f"service {sid} never became healthy (last: {state or 'gone'})")
            time.sleep(2)
    return names


def stop_services(names: list[str]) -> None:
    if names:
        subprocess.run(["docker", "rm", "-f", *names], capture_output=True, text=True)


def first_matrix(job: dict, ctx: Ctx) -> dict:
    matrix = ((job.get("strategy") or {}).get("matrix")) or {}
    if isinstance(matrix, str):
        raise Unrunnable("matrix is computed from an expression")
    pick = {k: v[0] for k, v in matrix.items() if isinstance(v, list) and v and k != "include"}
    return pick


def run_job(wf_name: str, wf: dict, job_id: str, job: dict, root: Path, ctx: Ctx,
            exempts: list[dict], results: list[dict]) -> None:
    def record(step: str, status: str, detail: str = "", secs: float = 0.0) -> None:
        results.append({"workflow": wf_name, "job": job_id, "step": step, "status": status,
                        "detail": detail, "seconds": round(secs, 1)})
    ctx.job_failed = False
    whole = exemption_entry(exempts, wf_name, job_id, "*")
    if whole:
        steps = [(st, str(st.get("name") or st.get("uses") or "")) for st in job.get("steps") or []]
        problem = exemption_problem(whole, steps)
        if problem:
            return record("*", "FAIL", problem)
        status = "SKIP-test-gap" if skipped_is_gap(whole, steps) else "SKIP-exempt"
        return record("*", status, whole["reason"])
    if not ctx.condition(job.get("if")):
        return record("*", "SKIP-filter", f"job if: {job.get('if')}")
    if job.get("container"):
        return record("*", "FAIL", "job runs inside a container image; exempt it with a reason")
    if job.get("uses"):
        return record("*", "FAIL", f"reusable workflow {job['uses']}; exempt it with a reason")
    tmp = Path(tempfile.mkdtemp(prefix="ci-mirror-"))
    files = {k: tmp / k for k in ("GITHUB_ENV", "GITHUB_OUTPUT", "GITHUB_PATH", "GITHUB_STEP_SUMMARY")}
    for f in files.values():
        f.write_text("")
    try:
        ctx.matrix = first_matrix(job, ctx)
        env = base_env(root, ctx, files)
        ctx.env = env
        env.update({k: ctx.sub(v) for k, v in {**(wf.get("env") or {}), **(job.get("env") or {})}.items()})
    except Unrunnable as exc:
        return record("*", "FAIL", str(exc))
    timeout_s = int(job.get("timeout-minutes") or 30) * 60
    try:
        services = start_services(job_id, job, ctx)
    except Unrunnable as exc:
        return record("*", "FAIL", f"cannot run locally: {exc}")
    try:
        run_steps(wf_name, wf, job_id, job, root, ctx, exempts, env, files, timeout_s, record)
    finally:
        stop_services(services)


def run_steps(wf_name, wf, job_id, job, root, ctx, exempts, env, files, timeout_s, record) -> None:
    ctx.job_failed = False
    def record_step(name, status, detail="", secs=0.0):
        if status == "FAIL":
            ctx.job_failed = True
        record(name, status, detail, secs)
    for i, step in enumerate(job.get("steps") or []):
        name = str(step.get("name") or step.get("uses") or f"step {i + 1}")
        entry = exemption_entry(exempts, wf_name, job_id, name)
        if entry:
            problem = exemption_problem(entry, [(step, name)])
            if problem:
                record_step(name, "FAIL", problem)
            else:
                record_step(name, "SKIP-test-gap" if skipped_is_gap(entry, [(step, name)])
                            else "SKIP-exempt",
                            entry["reason"])
            continue
        start = time.time()
        try:
            if not ctx.condition(step.get("if")):
                record_step(name, "SKIP-filter", "an earlier step failed" if ctx.job_failed else f"if: {step.get('if')}")
            elif step.get("uses"):
                warn = check_runtime(step, ctx, env)
                if not is_setup(step):
                    raise Unrunnable(f"third-party action {step['uses']} cannot run locally")
                record_step(name, "WARN-runtime" if warn else "SKIP-setup", warn or "")
            elif is_setup(step) and not needs_install(step, job, wf, root, ctx):
                record_step(name, "SKIP-setup")
            else:
                status, detail = run_step(step, job, wf, root, ctx, env, files, timeout_s)
                record_step(name, status, detail, time.time() - start)
                if git(root, "rev-parse", "--is-shallow-repository") == "true":
                    subprocess.run(["git", "fetch", "-q", "--unshallow", "origin"], cwd=root,
                                   capture_output=True, text=True)
                    if git(root, "rev-parse", "--is-shallow-repository") == "true":
                        raise Unrunnable("this step made the clone shallow and --unshallow failed")
        except Unrunnable as exc:
            record_step(name, "FAIL", f"cannot run locally: {exc}")


def main() -> int:
    STATE.mkdir(parents=True, exist_ok=True)
    lock = open(STATE / ".mirror.lock", "w")
    # A mirror started by one of this mirror's own steps must not wait for the lock its
    # parent holds: on 24/09/2026 the release gate's tests did exactly that and the suite
    # step deadlocked until its 900s timeout.
    # The marker only matters when the lock is busy: a stray CI_MIRROR_NESTED=1 in an
    # operator's shell still takes a free lock, so it cannot bypass serialisation.
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        if os.environ.get("CI_MIRROR_NESTED") == "1":
            print("ci_mirror: nested inside a running mirror; not waiting for its lock", flush=True)
        else:
            print("ci_mirror: another mirror run holds the lock; waiting for it to finish", flush=True)
            fcntl.flock(lock, fcntl.LOCK_EX)
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--repo", default=".")
    ap.add_argument("--base", default="origin/main")
    ap.add_argument("--json", help="write the machine-readable result here")
    ap.add_argument("--only", action="append", default=[], help="limit to these workflow files")
    args = ap.parse_args()
    # Resolve the destination BEFORE anything can fail. The caller prints "see <this
    # path>" on a non-zero exit, so the path has to be known even when the run dies on
    # its first git call. See the try/except that wraps the body below.
    out = Path(args.json) if args.json else None
    head = ""
    try:
        root = Path(git(Path(args.repo), "rev-parse", "--show-toplevel"))
        head = git(root, "rev-parse", "HEAD")
        if out is None:
            out = STATE / f"{head}.json"
        if git(root, "rev-parse", "--is-shallow-repository") == "true":
            raise RuntimeError(
                "shallow clone: base..HEAD ranges are wrong here. Run: git fetch --unshallow origin")
        return _mirror(args, root, head, out)
    except Exception:
        # EVERY exit writes the report. Until 2026-09-23 the report was built eight lines
        # from the end of this function, after every step had run, and nothing wrote it on
        # any abnormal exit: one early return plus a dozen unguarded check=True git calls.
        # pr_release_gate.py then printed "ci-mirror FAILED: a GitHub PR check would fail
        # on this head; see <path>.json" -- naming a file that was never created, and
        # asserting a verdict this program had not reached. On 23/09 the lock file was
        # stamped and no report existed at all.
        #
        # A crash and a failing step are different facts. Recording the traceback is what
        # lets the caller tell them apart instead of fusing them into one sentence.
        if out is None:
            out = STATE / "crash.json"
        report = {"schema": 1, "root": str(Path(args.repo).resolve()), "head_sha": head,
                  "base_sha": "", "changed_files": 0, "verdict": "CRASH",
                  "results": [{"workflow": "-", "job": "-", "step": "-", "status": "CRASH",
                               "detail": traceback.format_exc(), "seconds": 0}]}
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2) + "\n")
        print(f"\nCI_MIRROR_CRASH head={head or '?'} report={out}", file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)
        return 1


def _mirror(args, root: Path, head: str, out: Path) -> int:
    base = git(root, "merge-base", args.base, "HEAD")
    branch = git(root, "rev-parse", "--abbrev-ref", "HEAD")
    base_branch = args.base.split("/", 1)[-1]
    changed = [c for c in git(root, "diff", "--name-only", f"{base}...HEAD").splitlines() if c]
    ctx = Ctx(root, base, head, branch, base_branch)
    stat = git(root, "diff", "--numstat", f"{base}...HEAD").splitlines()
    ctx.values.update({
        "github.event.pull_request.changed_files": str(len(changed)),
        "github.event.pull_request.additions": str(sum(int(x.split()[0]) for x in stat if x.split()[0].isdigit())),
        "github.event.pull_request.deletions": str(sum(int(x.split()[1]) for x in stat if x.split()[1].isdigit())),
        "github.event.pull_request.draft": "false",
    })
    exempts = load_exemptions(root)
    untracked_before = set(git(root, "ls-files", "--others", "--exclude-standard").splitlines())
    results: list[dict] = []
    wf_dir = root / ".github" / "workflows"
    wf_files = sorted(list(wf_dir.glob("*.yml")) + list(wf_dir.glob("*.yaml"))) if wf_dir.is_dir() else []
    for path in wf_files:
        if args.only and path.name not in args.only:
            continue
        wf = yaml.safe_load(path.read_text()) or {}
        trig = pr_trigger(wf)
        if trig is None:
            continue
        why_not = workflow_applies(trig, changed, base_branch)
        if why_not:
            results.append({"workflow": path.name, "job": "*", "step": "*", "status": "SKIP-filter",
                            "detail": why_not, "seconds": 0})
            continue
        for job_id, job in (wf.get("jobs") or {}).items():
            run_job(path.name, wf, job_id, job or {}, root, ctx, exempts, results)
    created = set(git(root, "ls-files", "--others", "--exclude-standard").splitlines()) - untracked_before
    for rel in sorted(c for c in created if c):
        (root / rel).unlink(missing_ok=True)
        print(f"cleaned   {rel} (written by a mirrored step)")
    fails = [r for r in results if r["status"] == "FAIL"]
    verdict = "PASS" if not fails and results else "FAIL"
    if not results:
        fails.append({"workflow": "-", "job": "-", "step": "-", "status": "FAIL",
                      "detail": "no pull_request workflows found: nothing was mirrored"})
    report = {"schema": 1, "root": str(root), "head_sha": head, "base_sha": base,
              "changed_files": len(changed), "verdict": verdict, "results": results,
              "test_gaps": sum(r["status"] == "SKIP-test-gap" for r in results)}
    STATE.mkdir(parents=True, exist_ok=True)
    # The caller names the path; it does not have to have created the directory. Before
    # this, a --json under a fresh directory raised FileNotFoundError after every step had
    # already run, and the release gate read that as "a GitHub PR check would fail on this
    # head" -- a mirror that passed, reported as a red PR.
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n")
    for r in results:
        line = f"{r['status']:<12} {r['workflow']} :: {r['job']} :: {r['step']}"
        print(line + (f"  ({r['detail'].splitlines()[0]})" if r["detail"] and r["status"] not in ("FAIL", "PASS") else ""))
    for r in fails:
        print(f"\n--- FAIL {r['workflow']} :: {r['job']} :: {r['step']}\n{r['detail']}")
    print(f"\nCI_MIRROR_{verdict} head={head} steps={len(results)} fails={len(fails)} "
          f"test_gaps={report['test_gaps']} report={out}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
