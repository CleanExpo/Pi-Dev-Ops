#!/usr/bin/env python3
"""Skills Library Board: the three standing checks /spm runs first.

  1. home   - the work happens in the clean canonical home (Mini external SSD clone),
              main matches origin/main, and no stale worktrees are piling up.
  2. fresh  - installed Claude Code, Codex and Cursor match the latest each vendor ships,
              with the newest Claude Code changelog entry.
  3. md     - the library's Markdown carries nothing that stalls an agent: machine-absolute
              paths, dangling references or symlinks, commands the gates refuse, retired
              model IDs, broken frontmatter.

Usage:
  board.py probe [--record] [--limit N]  one JSON line for preflight.py:
                     {"line", "new", "more_new", "new_unproven", "known", "known_unproven",
                     "elsewhere"}. Offline, <0.1s. With --record (preflight only) it prints
                     first, then records what it printed; without it the shown-list is untouched.
                     Starts the detached refresh when the cache is missing, malformed,
                     older than 24h, or a partial reading's retry time has passed.
  board.py refresh   network + file scan; writes the cache. Holds an flock, so only one
                     refresh ever runs; a second one exits at once.
  board.py summary   human-readable lines from the cache (offline).
  board.py report    the full cached findings, every case with file:line.

New versus known (founder rule, 22/10/2026): the founder sees each finding once. Every case
has a stable key (Markdown: class + file + hash of the line text, so it survives edits
elsewhere in the file). `probe` returns only cases not shown before, at most N groups, and
with --record records exactly those as shown. A remembered case is forgotten only when its own section
was read cleanly and the case is gone; an unread section keeps its memory, so a network
blip never makes an old finding look new. A case that clears and later returns is new.

Never edits, deletes, installs or updates anything. A reading that could not be taken is
reported as unproven, never as clean or current.
Env: SPM_BOARD_HOME (canonical clone), SPM_BOARD_CACHE (cache file), SPM_BOARD_LIBRARY
(tree the md audit scans), SPM_BOARD_OFFLINE=1 (refresh skips network and fetch),
SPM_BOARD_NO_SPAWN=1 (probe never starts a refresh; tests), SPM_BOARD_GATE_REF (the reviewed
gate revision the md detector must match; default origin/main).
"""
import time as _time
T0 = _time.monotonic()  # process start: the probe budget is measured from here, imports included
import errno
import hashlib
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

try:
    import fcntl
except ImportError:  # Windows: no flock; a refresh then runs unlocked
    fcntl = None
if os.environ.get("SPM_BOARD_NO_FLOCK") == "1":  # tests: behave as on Windows
    fcntl = None

SCHEMA = "spm-board/3"
HOME = Path.home()
SSD = Path("/Volumes/Mini Mini 2T Storage")
CANON = Path(os.environ.get("SPM_BOARD_HOME", SSD / "code/skills-library"))
# Founder rule: on the Mini every write goes to the external SSD, never the internal disk.
# The location is pinned per machine (not per mount), so the shown-list never switches.
def _host_names():
    names = [socket.gethostname()]
    if "SPM_BOARD_CACHE" in os.environ or "mac-mini" in names[0].lower():
        return " ".join(names).lower()
    try:
        r = subprocess.run(["scutil", "--get", "LocalHostName"], capture_output=True, text=True, timeout=2)
        names.append(r.stdout.strip())
    except (OSError, subprocess.TimeoutExpired):
        pass
    return " ".join(names).lower()


ON_MINI = "mac-mini" in _host_names()
# Markdown findings are the same on every machine (the library is synced), but each machine
# keeps its own shown-list. So they are announced only on the Mini, the one clean home; other
# machines count them on the md line and never call them new. Versions and worktrees differ per
# machine and are announced where they are found.
MD_NEW_HERE = {"1": True, "0": False}.get(os.environ.get("SPM_BOARD_MD_NEW", ""), ON_MINI)
_DEFAULT_STATE = SSD / "hot/state/spm" if ON_MINI else HOME / ".local/state/spm"
CACHE = Path(os.environ.get("SPM_BOARD_CACHE", _DEFAULT_STATE / "board.json"))
SEEN = CACHE.with_name(CACHE.stem + "-seen.json")
SEEN_LOCK = CACHE.with_name(CACHE.stem + "-seen.lock")
LOCK = CACHE.with_name(CACHE.stem + ".lock")
LOCK_MARK = CACHE.with_name(CACHE.stem + ".refreshing")  # stands in for the lock without flock
LAST = CACHE.with_name(CACHE.stem + "-last.json")  # outcome of the latest refresh attempt
# On the Mini the state lives on the SSD; with the SSD unplugged there is nowhere to write.
SSD_MISSING = ON_MINI and "SPM_BOARD_CACHE" not in os.environ and not SSD.is_dir()
LIBRARY = Path(os.environ.get("SPM_BOARD_LIBRARY", HOME / ".claude"))
OFFLINE = os.environ.get("SPM_BOARD_OFFLINE") == "1"
MAX_AGE_H = 24
RETRY_H = 1  # a reading with a transient gap is retried after this, not trusted for a day
REFRESH_DEADLINE_S = 240  # a whole refresh, network included; past it nothing is written
STUCK_S = 600  # a refresh holding the lock longer than this is reported as stuck
MARK_GRACE_S = 30  # an unreadable marker younger than this may be one being written right now
GATE_REF = os.environ.get("SPM_BOARD_GATE_REF", "refs/remotes/origin/main")  # the reviewed gate the detector must match
UA = {"User-Agent": "spm-board/3"}
NOT_HERE = "home: canonical clone not on this host"  # structural, not transient: no hourly retry
# Gaps a retry within the hour cannot close (nothing on the network changes them). Only the
# others (fetch failures, unread pages, crashes) shorten the next retry to RETRY_H.
LASTING = (NOT_HERE, "not found on PATH", "retired-models list missing", "HOMES.json unreadable", "folders unreadable", "files unreadable",
           "no Markdown found", "md: fallback", "home: origin not fetched")


def sh(argv, cwd=None, timeout=5):
    try:
        r = subprocess.run(argv, cwd=cwd, capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, timeout=timeout)
        return r.returncode, r.stdout.strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return -1, type(e).__name__


class _Redirect(urllib.request.HTTPRedirectHandler):
    """Python before 3.11 does not follow 308; treat it as 307. Redirects stay on https."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not newurl.startswith("https://"):
            return None
        return super().redirect_request(req, fp, 307 if code == 308 else code, msg, headers, newurl)
    http_error_308 = urllib.request.HTTPRedirectHandler.http_error_302


def fetch(url, timeout=8, limit=400_000, headers=None, want_type=False):
    """Plain unauthenticated GET; at most `limit` bytes. want_type: (text, content-type)."""
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    with urllib.request.build_opener(_Redirect).open(req, timeout=timeout) as r:
        text = r.read(limit).decode("utf-8", "replace")
        return (text, r.headers.get("Content-Type", "")) if want_type else text


# ---------- 1. home ----------

def bucket(n):
    n = int(n)
    return next(f">={b}" for b in (200, 50, 10, 1) if n >= b) if n > 0 else "0"


def check_home():
    """Clean-home facts. Reads only; the fetch updates remote-tracking refs and nothing else.
    read: which scopes gave a full reading (home-canon, home-wt)."""
    out = {"canonical": str(CANON), "present": CANON.is_dir(), "problems": [], "unproven": [], "read": []}
    if not out["present"]:
        out["unproven"].append(NOT_HERE)
    else:
        fetched = False
        if OFFLINE:
            out["unproven"].append("home: origin not fetched")
        else:
            rc, _ = sh(["git", "-c", "gc.auto=0", "-c", "maintenance.auto=false", "-C", str(CANON),
                        "fetch", "-q", "--no-prune", "--no-recurse-submodules", "origin"], timeout=30)
            fetched = rc == 0
            if not fetched:
                out["unproven"].append("home: origin fetch failed")
        rc, dirty = sh(["git", "--no-optional-locks", "-C", str(CANON), "status", "--porcelain", "--untracked-files=no"],
                       timeout=15)
        rc2, ab = sh(["git", "-C", str(CANON), "rev-list", "--left-right", "--count", "main...origin/main"])
        if rc != 0 or rc2 != 0:
            out["unproven"].append("home: canonical clone unreadable")
        else:
            a, b = (ab.split() + ["?", "?"])[:2]
            out["dirty"] = len(dirty.splitlines()) if dirty else 0
            out["main_ahead"], out["main_behind"] = a, b
            # Each entry: [group, text, case keys]. Counts are bucketed so growth is shown again.
            if out["dirty"]:
                out["problems"].append(["home-dirty", f"canonical clone has {out['dirty']} tracked changes",
                                        [f"home-dirty|{bucket(out['dirty'])}"]])
            if b != "0":
                out["problems"].append(["home-behind", f"canonical main {b} behind origin",
                                        [f"home-behind|{bucket(b)}"]])
            if a != "0":
                out["problems"].append(["home-ahead", f"canonical main {a} ahead of origin, unpushed",
                                        [f"home-ahead|{bucket(a)}"]])
            if fetched:
                out["read"].append("home-canon")
    rc, wl = sh(["git", "-C", str(LIBRARY), "worktree", "list", "--porcelain"])
    if rc != 0:
        out["unproven"].append("home: worktree list failed")
    else:
        extra = [b for b in wl.split("\n\n") if b.strip()][1:]  # the first block is the main checkout
        path = lambda b: b.splitlines()[0].removeprefix("worktree ").strip()
        prunable = [path(b) for b in extra if "\nprunable" in b]
        detached = [path(b) for b in extra if "\ndetached" in b]
        out["worktrees"], out["prunable"], out["detached"] = len(extra), len(prunable), len(detached)
        # One case per worktree, so the list the founder approves for removal is the real list.
        if prunable:
            out["problems"].append(["home-prunable", f"{len(prunable)} prunable worktrees",
                                    [f"home-prunable|{p}" for p in prunable]])
        if detached:
            out["problems"].append(["home-detached", f"{len(detached)} detached review worktrees to clear",
                                    [f"home-detached|{p}" for p in detached]])
        out["read"].append("home-wt")
    return out


# ---------- 2. fresh ----------

def ver(s):
    m = re.search(r"\d{4}\.\d{1,2}\.\d{1,2}(?:-[0-9a-f]+)?|\d+\.\d+\.\d+", s or "")
    return m.group(0) if m else None


def vkey(v):
    return tuple(int(x) for x in re.findall(r"\d+", v.split("-")[0]))


def compare(installed, latest):
    if installed == latest:
        return "current"
    a, b = vkey(installed), vkey(latest)
    if a == b:
        return "build-differs"  # same version, different build hash: read, but no order to tell
    return "update" if a < b else "ahead"


def installed_cli(cmd):
    """(version, ok). ok=False when the binary exists but would not report a version."""
    p = shutil.which(cmd) or next(
        (str(c) for c in (HOME / ".local/bin" / cmd, Path("/opt/homebrew/bin") / cmd, Path("/usr/local/bin") / cmd)
         if c.is_file() and os.access(c, os.X_OK)), None)  # a PATH without ~/.local/bin is not "not installed"
    if not p:
        return None, True
    v = ver(os.path.realpath(p)) if cmd == "cursor-agent" else None
    if v:
        return v, True
    rc, out = sh([p, "--version"])
    v = ver(out) if rc == 0 else None
    return v, v is not None


CC_TAGS = "https://registry.npmjs.org/-/package/@anthropic-ai/claude-code/dist-tags"
CC_LOG = "https://raw.githubusercontent.com/anthropics/claude-code/main/CHANGELOG.md"
CODEX_TAGS = "https://registry.npmjs.org/-/package/@openai/codex/dist-tags"
CODEX_RSS = "https://developers.openai.com/codex/changelog/rss.xml"
CURSOR_INSTALL = "https://cursor.com/install"
CURSOR_LOG = "https://cursor.com/docs/cli/changelog.md"
DEPRECATIONS = "https://platform.claude.com/docs/en/about-claude/model-deprecations.md"
TRIVIAL = "bug fixes and reliability improvements"
SEMVER = re.compile(r"\d+\.\d+\.\d+")


def npm_latest(body):
    """dist-tags 'latest' only; never alpha/beta/native. None when it is not a plain release."""
    v = json.loads(body).get("latest")
    return v if isinstance(v, str) and SEMVER.fullmatch(v) else None


def cursor_build(body):
    """The one lab build the install script downloads; None unless exactly one distinct match."""
    m = set(re.findall(r"downloads\.cursor\.com/lab/(\d{4}\.\d{2}\.\d{2}-[0-9a-f]{7})/", body))
    return m.pop() if len(m) == 1 else None


def cc_entries(body):
    """Newest 3 complete changelog entries [{version, bullets}]; the last section may be cut by
    the byte range, so it is always dropped."""
    secs = re.split(r"^## ", body, flags=re.M)[1:-1]
    out = []
    for sec in secs[:3]:
        head, *rest = sec.splitlines()
        out.append({"version": head.strip(), "bullets": [b[2:].strip() for b in rest if b.startswith("- ")][:3]})
    return out


def _text(fragment):
    import html
    t = re.sub(r"</?(?:code|a|b|i|em|strong|span)\b[^>]*>", "", fragment)  # inline: no gap
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", html.unescape(t)).strip()


def codex_news(body):
    """First 'Codex CLI Release: x.y.z' item of the RSS: {version, items}. None when absent."""
    import html
    for item in re.findall(r"<item>(.*?)</item>", body, flags=re.S):
        t = re.search(r"<title>(.*?)</title>", item, flags=re.S)
        m = t and re.fullmatch(r"Codex CLI Release: (\d+\.\d+\.\d+)", html.unescape(t.group(1)).strip())
        if not m:
            continue
        c = re.search(r"<content:encoded>(.*?)</content:encoded>", item, flags=re.S)
        raw = c.group(1) if c else ""
        raw = re.sub(r"^\s*<!\[CDATA\[|\]\]>\s*$", "", raw)
        raw = html.unescape(raw)  # the entity-escaped form; a CDATA body is already HTML
        lis = re.findall(r"<li[^>]*>(.*?)</li>", raw, flags=re.S)
        items = [_text(x) for x in lis] if lis else [_text(x) for x in raw.splitlines()]
        items = [re.sub(r"\s*\(\s*(?:#\d+[,\s]*)+\)$", "", x) for x in items if x]
        return {"version": m.group(1), "items": items[:3]} if items else None
    return None


def cursor_news(body):
    """First '## vYYYY.MM.DD' section: {version, sections: [{title, first}]}. None when absent."""
    m = re.search(r"^## v(\d{4}\.\d{2}\.\d{2})[ \t]*$", body, flags=re.M)
    if not m:
        return None
    nxt = re.search(r"^## ", body[m.end():], flags=re.M)
    sec = body[m.end():m.end() + nxt.start()] if nxt else body[m.end():]
    subs = []
    for part in re.split(r"^### ", sec, flags=re.M)[1:]:
        title, *rest = part.splitlines()
        first = next((b[2:].strip() for b in rest if b.startswith("- ")), "")
        subs.append({"title": title.strip(), "first": first})
    return {"version": "v" + m.group(1), "sections": subs} if subs else None


def dated(text):
    """Whether scripts/fetch-retired-models.py can read this retirement date (its parse_date
    formats). A date it cannot read ("To be announced", "TBD", "Q2 2027", empty) never reaches the
    list, so a deprecated model with one is not a gap the list could fill."""
    import datetime as _dt
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d"):
        try:
            _dt.datetime.strptime(text.strip().replace("Sept ", "Sep "), fmt)
            return True
        except ValueError:
            pass
    return False


def deprecation_rows(body):
    """[(model id, state, retirement date)] from the pipe table whose header names 'API model name'
    and 'Current state'; the date is None when the table has no retirement-date column. Empty when
    no such table."""
    rows, cols = [], None
    for line in body.splitlines() + [""]:
        if not line.lstrip().startswith("|"):
            if rows:
                return rows
            cols = None
            continue
        cells = [c.strip().strip("`").strip() for c in line.strip().strip("|").split("|")]
        if cols is None:
            low = [c.lower() for c in cells]
            ret = next((n for n, c in enumerate(low) if "retirement" in c), None)
            cols = (low.index("api model name"), low.index("current state"), ret) \
                if "api model name" in low and "current state" in low else ()
            continue
        if not cols or all(re.fullmatch(r":?-+:?", c) for c in cells if c):
            continue
        if len(cells) > max(cols[0], cols[1]) and cells[cols[0]]:
            rows.append((cells[cols[0]], cells[cols[1]],
                         None if cols[2] is None else (cells[cols[2]] if len(cells) > cols[2] else "")))
    return rows


def check_fresh():
    """Installed vs latest for Claude Code, Codex and Cursor, what changed in each, and whether
    the library's retired-model list covers what Anthropic retired. Anything not read is noted
    in 'unproven'; nothing unread is ever 'current'."""
    srcs = {"claude": (CC_TAGS, {}), "codex": (CODEX_TAGS, {}), "cursor-agent": (CURSOR_INSTALL, {}),
            "cc_log": (CC_LOG, {"headers": {"Range": "bytes=0-32767"}, "limit": 32768}),
            "codex_rss": (CODEX_RSS, {"limit": 1_200_000}), "cursor_log": (CURSOR_LOG, {}),
            "deprecations": (DEPRECATIONS, {"want_type": True})}
    got = {}
    if not OFFLINE:
        from concurrent.futures import ThreadPoolExecutor
        pool = ThreadPoolExecutor(len(srcs))
        futs = {k: pool.submit(fetch, url, **kw) for k, (url, kw) in srcs.items()}
        for k, fu in futs.items():
            try:
                got[k] = fu.result()
            except Exception as e:
                got[k] = e
        pool.shutdown(wait=False)

    def body(k):
        b = got.get(k)
        return None if b is None or isinstance(b, Exception) else b

    tools, notes = {}, []
    parse = {"claude": npm_latest, "codex": npm_latest, "cursor-agent": cursor_build}
    for name, fn in parse.items():
        t = {}
        t["installed"], ok = installed_cli(name)
        if not ok:
            t["error"] = "installed version unreadable"
        t["latest"] = None
        if not OFFLINE:
            b = got.get(name)
            if isinstance(b, Exception):
                t["error"] = f"latest: {type(b).__name__}"
            else:
                try:
                    t["latest"] = fn(b)
                except Exception as e:
                    t["error"] = f"latest: {type(e).__name__}"
                if t["latest"] is None and "error" not in t:
                    t["error"] = "latest: no match"
        if t.get("installed") and t.get("latest"):
            try:
                t["status"] = compare(t["installed"], t["latest"])
            except ValueError:
                t["status"] = "unknown"
        elif t.get("installed") is None and ok:
            t["status"] = "absent"
        else:
            t["status"] = "unknown"
        tools[name] = t
    news, news_ok, pick, entries = [], False, None, []
    if body("cc_log") is not None:
        entries = cc_entries(body("cc_log"))
        if entries and entries[0]["version"] == tools["claude"]["latest"]:
            news_ok = True
            chosen = next((e for e in entries if e["bullets"] and
                           [b.lower().rstrip(".") for b in e["bullets"]] != [TRIVIAL]), entries[0])
            pick = chosen["version"]
            news = [entries[0]["version"]] + chosen["bullets"]
    cx = cursor = retired = None
    if body("codex_rss") is not None:
        cx = codex_news(body("codex_rss"))
    if not cx:
        notes.append("fresh: codex changelog")
    if body("cursor_log") is not None:
        cursor = cursor_news(body("cursor_log"))
    if not cursor:
        notes.append("fresh: cursor changelog")
    dep = body("deprecations")
    rows = []
    if dep is not None:
        text, ctype = dep
        if "text/markdown" in (ctype or "").lower() or text.lstrip().startswith("#"):
            rows = deprecation_rows(text)
    # "Retired (Oct 2025)" counts; a table with no retired or deprecated model was not read right.
    # A deprecated model whose retirement date is not set yet ("To be announced") still answers,
    # and scripts/fetch-retired-models.py leaves it out on purpose, so it is not a gap in the list.
    marked = [(i, s, r) for i, s, r in rows if s.lower().startswith(("retired", "deprecated"))]
    flagged = sorted({i for i, s, r in marked if s.lower().startswith("retired") or r is None or dated(r)})
    if not marked:
        notes.append("fresh: model deprecations page unread")
    else:
        listed = retired_models()
        if listed is None:
            notes.append("fresh: retired-models list missing")
        retired = {"rows": len(rows), "flagged": flagged, "ok": listed is not None,
                   "missing": [i for i in flagged if listed is not None and i not in listed]}
    return {"tools": tools, "claude_changelog": news, "changelog_ok": news_ok, "claude_pick": pick,
            "claude_entries": entries, "codex_news": cx, "cursor_news": cursor, "retired": retired,
            "unproven": notes}


# ---------- 3. md ----------

def retired_models():
    f = LIBRARY / "scripts/retired-models.txt"
    if not f.is_file():
        return None
    return {l.split()[0] for l in f.read_text().splitlines()
            if l.strip() and not l.startswith("#") and len(l.split()[0]) > 6}


MD_RULES = [
    # (class, regex, why it stalls an agent)
    ("abs-path", re.compile(r"/Users/(?:phill-mac|phillmcgurk)\b|C:\\+Users\\"),
     "machine-absolute path: wrong on every other machine"),
    # force push: same command segment only (stops at ` ; & |), `git -C repo push`, combined flags (-fu),
    # a +refspec that names a ref (not "+1"); --force-with-lease matches (the release gate refuses it too),
    # --no-verify-ssl does not
    # `git commit -n` (or combined, -an) is the short form of --no-verify
    ("refused-cmd", re.compile(r"--no-verify(?![\w-])|\bgit(?:\s+-[Cc]\s+\S+)*\s+commit\b[^`;&|\n]*?"
                               r"\s-[a-zA-Z]*n[a-zA-Z]*(?![\w-])|\bgit(?:\s+-[Cc]\s+\S+)*\s+push\b[^`;&|\n]*?"
                               r"(?:\s-[a-zA-Z]*f[a-zA-Z]*(?![\w-])|--force(?:-with-lease)?(?![\w-])|\s\+[A-Za-z_./][\w/.:-]*)|"
                               r"ssh\s+-o\s[^\n]*mini-ts|PR_RELEASE_GATE_HUMAN_OVERRIDE=|"
                               r"--dangerously-skip-permissions"),
     "tells the agent to run something the gates refuse or the rules forbid"),
    # .env must start a path component (`~/x/.env`, `.env.local`), not sit inside a token like process\.env\.
    # source/head/tail/less read the path right after them (flags allowed): "the source of truth is .env..."
    # and "head over to the .env docs" are English, not reads
    ("env-read", re.compile(r"(?:\b(?:cat|grep)\b[^`;&|\n]*?\s|\b(?:source|head|tail|less)(?:\s+-\S+(?:\s+\d+)?)*\s+"
                            r"|^\s*\.\s+)[\"']?(?:\S*/)?(?:\.env(?!(?:\.[\w-]+)*\.(?:example|sample|template)(?![\w-]))"
                            r"(?:\.[\w-]+)*(?![.\w])|\.zshenv)|"
                               r"railway\s+variables\b|list_variables"),
     "reads a secret store the gates block"),
]
GITSUB_FALLBACK = re.compile(r"\$\([^)]*\b(?:git|gh)\b")
SKIP_DIRS = {".trash", "synced", "tests", "test", "fixtures", "node_modules", "examples", "evals",
             ".git", ".venv", "venv", "__pycache__", "dist", "build"}
# "no" only as a standalone word: the "no" inside a flag (`--no-edit`, `--no-session-persistence`) forbids nothing
PROHIBITION = re.compile(r"\b(?:never|don['’]t|do not|must not|should not|shouldn['’]t|cannot|can['’]t|"
                         r"forbidden|banned|not allowed|without|avoid|instead of|blocks|denies)\b"
                         r"|(?<![\w-])no(?![\w-])", re.I)
# these forbid only when they directly govern the match: same clause (no comma between) and at most three
# words between -- "No `--no-verify`", "without `--force`", "The gate blocks `cat .env`" forbid;
# "Without an upstream, run ...", "With no upstream yet, run ...", "Because the hook blocks it, run ..." do not
WEAK_PROHIBITION = re.compile(r"no|without|instead of|blocks|denies", re.I)
# a literal path right after "hardcoded" describes a past defect, it is not an instruction to use the path
PAST_DEFECT = re.compile(r"\bhard-?coded\s*[`'\"]?$", re.I)
# a forbidding word that only negates a requirement or an idiom is no ban: "Don't forget to run", "Never skip
# these steps:", "Don't hesitate to", "Do not worry, just run", "never mind"
# (whole words with their inflections only: "Never mindlessly run X" is still a ban)
NOT_A_BAN = re.compile(r"\s+(?:skip|forget|omit|miss|hesitate|neglect|fail|worry|mind)(?:s|ped|ping|ting|ed|ing)?\b",
                       re.I)
# ...except that skipping a hook or check is what every refused command does, so it is a ban on its own:
# "NEVER skip hooks (--no-verify)", "Never skip hooks or `git push --force`", "Never skip hooks:"
SKIP_HOOKS = re.compile(r"\s+(?:skip|bypass|disable)(?:s|ped|ping|d|ed|ing)?\s+(?:(?:the|any|all|your|git|"
                        r"pre-commit|commit|pre-push)\s+)*(?:hooks?|checks?|verifications?|gates?)\b", re.I)
# ...and a skip/fail done WITH something names that something as the forbidden means, but only when the
# instrument attaches to skip/fail itself and its object (if any) is a hook/check/gate/CI: "Never skip CI by
# passing --no-verify", "Do not fail open with `git push --force`". "Don't skip the step using X",
# "Don't forget the step with X" and "Don't worry and run it with X" stay requirements.
INSTRUMENT = re.compile(r"(?:\s+(?:the|any|all|your|git|pre-commit|commit|pre-push|open|closed))*"
                        r"(?:\s+(?:hooks?|checks?|verifications?|gates?|ci|tests?))?\s+(?:with|by|via|using|passing)\b",
                        re.I)


def released_ban(s, pos, end):
    """True when the forbidding word ending at `pos` only negates a requirement or an idiom (NOT_A_BAN), and
    nothing before `end` turns it back into a ban (skipping hooks, or skip/fail with an instrument)."""
    m = NOT_A_BAN.match(s, pos)
    if not m or SKIP_HOOKS.match(s, pos):
        return False
    verb = m.group(0).strip().lower()
    return not (verb.startswith(("skip", "fail")) and INSTRUMENT.match(s[:end], m.end()))


# "To avoid conflicts run X": a purpose clause, "avoid" governs the conflicts, not X -- but only when the
# purpose clause has ended (a comma or a verb) before X: "To avoid `git push --force` mistakes, check the
# branch" and "In order to avoid --no-verify, fix the hook" forbid
PURPOSE = re.compile(r"\s*(?:in\s+order\s+)?to\s+", re.I)
# (a verb right after "to" -- "the need to use", "having to run" -- is still inside the purpose clause)
PURPOSE_END = re.compile(r",|\b(?:run|use|pass|add|call|execute|invoke|try|prefer|type|then|just)\b", re.I)
SENTENCE_END = re.compile(r"[.;:!?](?:\s|$)|\s—\s")
SHELL_FENCES = {"bash", "sh", "zsh", "shell", "console", "shell-session", "terminal"}
LINK = re.compile(r"\]\((?!https?:|mailto:|#|~|/)([^)\s#]+)")
FENCE = re.compile(r"^\s*(`{3,}|~{3,})\s*([\w+-]*)")


def forbidden_before(line, start):
    """True when a forbidding word precedes `start` in the same sentence, and is not inside a conditional
    clause ("If there is no upstream yet, run ..." -- "no" belongs to the if-clause, not the command)."""
    head = line[:start]
    cut = 0
    for m in SENTENCE_END.finditer(head):
        cut = m.end()
    frag = head[cut:]
    for w in PROHIBITION.finditer(frag):
        clause = frag[frag.rfind(",", 0, w.start()) + 1:w.start()]
        if CONDITIONAL.search(clause):
            continue
        if released_ban(line, cut + w.end(), start):
            continue
        rest = frag[w.end():]
        if w.group(0).lower() == "avoid" and PURPOSE.fullmatch(clause) and any(
                not re.search(r"\bto\s+$", rest[:e.start()], re.I) for e in PURPOSE_END.finditer(rest)):
            continue
        if WEAK_PROHIBITION.fullmatch(w.group(0)):
            between = frag[w.end():]
            if "," in between or len(re.findall(r"[\w'-]+", between)) > 3:
                continue
        return True
    return False


# after the match: "`--no-verify` is forbidden", "force push is refused", "... is never allowed";
# a conditional between the match and the word ("run X if the push is refused") is not a prohibition
PROHIBITION_AFTER = re.compile(r"\b(?:forbidden|refused?|banned|prohibited|blocks|blocked|denied|"
                               r"(?:not|never)\s+(?:allowed|permitted))\b", re.I)
CONDITIONAL = re.compile(r"\b(?:if|when|whenever|unless|until|once)\b", re.I)
# "Never do any of these:" / "Do not:" / "Forbidden:" -- every list item that follows forbids.
# "refused" is not a lead-in word: "To recover from a refused push:" introduces steps to run.
LEAD_IN = re.compile(r"\b(?:never|don['’]t|do not|must not|should not|shouldn['’]t|cannot|can['’]t|"
                     r"forbidden|banned|prohibited|not allowed)\b", re.I)
# under a forbidding heading, prose that itself forbids ("Also never run these:", "The release gate refuses
# each of these.") keeps the items after it forbidden; other prose ("Instead, do this:") ends them
FORBIDS = re.compile(r"\b(?:refuse[sd]?|rejects?|blocks|forbids|prohibits)\b", re.I)
# a lead-in that tells the reader to act BEFORE its forbidding phrase ("Run these in order and never skip
# one:") is not forbidding; action words the phrase governs ("Do not follow these steps:", "Never run or
# do these:") are part of the prohibition
IMPERATIVE = re.compile(r"\b(?:run|do|steps?|follow)\b", re.I)
# a heading made only of a forbidding phrase ("## Never", "### Do not") forbids every list item under it
FORBID_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(?:never|don['’]t|do not|must not|forbidden|banned|prohibited|"
                            r"not allowed)\s*:?\s*#*\s*$", re.I)
HEADING = re.compile(r"^\s{0,3}#{1,6}\s")
LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s")


def forbidden_after(line, end):
    """True when a forbidding word follows `end` in the same sentence, with no conditional between."""
    tail = line[end:]
    m = SENTENCE_END.search(tail)
    tail = tail[:m.start()] if m else tail
    w = PROHIBITION_AFTER.search(tail)
    return bool(w) and not CONDITIONAL.search(tail[:w.start()])


def forbidding_lead_in(line):
    """A line like "Never do any of these:" that introduces a list of forbidden things."""
    s = line.rstrip()
    w = next((w for w in LEAD_IN.finditer(s) if not released_ban(s, w.end(), len(s))), None)
    return (s.endswith(":") and bool(w) and not CONDITIONAL.search(s)
            and not IMPERATIVE.search(s[:w.start()]))


class ForbidLists:
    """Tracks, line by line, whether a list item sits under a forbidding lead-in. A heading lead-in
    ("## Never") holds until the next heading; a colon lead-in ("Never do any of these:") holds for the
    list right after it (blank lines allowed before its first item) and ends at a blank or plain line.
    Indented continuation lines of an item (also after a blank line, as in a loose list) keep the list going
    and share the item's status. Under a forbidding heading, prose that itself forbids keeps the heading's hold.
    Call step() only for lines outside code fences (a `# comment` in a fence is not a heading); call fence()
    for the line that opens one."""

    def __init__(self):
        self.mode, self.in_item, self.clean, self.item_open = None, False, False, False

    def fence(self, line):
        """Whether a code block opening on `line` is forbidden: directly under a forbidding heading (only blank
        lines and forbidden items since it), right after a colon lead-in (blank lines allowed), or indented
        inside a forbidden item. An unindented fence ends a lead-in's list and is not governed by it."""
        if self.in_item and line[:1].isspace():
            return self.mode is not None
        self.in_item = False
        if self.mode == "heading":
            return self.clean
        forbidden, self.mode = self.mode == "pending", None
        return forbidden

    def step(self, line):
        """Returns True when `line` is (part of) a forbidden list item."""
        is_item = bool(LIST_ITEM.match(line))
        is_cont = (not is_item and self.item_open and line[:1].isspace() and bool(line.strip())
                   and not HEADING.match(line))
        part = is_item or is_cont
        # under a forbidding heading, a plain prose line ("Instead, do this:") ends the forbidden list
        forbidden = self.mode is not None and part and (self.mode != "heading" or self.clean)
        if HEADING.match(line):
            self.mode = "heading" if FORBID_HEADING.match(line) else None
            self.clean = True
        elif self.mode == "heading":
            forbids = forbidding_lead_in(line) or (bool(FORBIDS.search(line)) and not CONDITIONAL.search(line))
            self.clean = (self.clean and (part or not line.strip())) or (not part and forbids)
        elif forbidding_lead_in(line):
            self.mode = "pending"
        elif self.mode == "pending":
            self.mode = "list" if is_item else ("pending" if not line.strip() else None)
        elif self.mode == "list" and not part:
            self.mode = None
        self.in_item = part
        self.item_open = part or (self.item_open and not line.strip())
        return forbidden


# dead-link: links written inside inline code are examples, and FILE.md / <file> / {name} are placeholders
CODE_SPAN = re.compile(r"`[^`\n]*`")


def installer_only(d):
    """A skills/ folder holding only install/ and/or hooks/ (the synced installers AGENTS.md requires)."""
    try:
        names = {c.name for c in d.iterdir() if not c.name.startswith(".")}
    except OSError:
        return False
    return bool(names) and names <= {"install", "hooks"} and all((d / n).is_dir() for n in names)


def skill_container(d):
    """A skills/ folder whose subfolders hold skills (e.g. skills/claude.ai/<skill>/SKILL.md)."""
    try:
        return any(c.is_dir() and (c / "SKILL.md").is_file() for c in d.iterdir())
    except OSError:
        return False
PLACEHOLDER = re.compile(r"^(?:<[^>]*>?|.*[{}].*|(?:.*/)?(?:FILE|PATH|NAME|FOO|BAR|X)(?:\.\w+)?)$")


def prohibited(line, start, end, in_forbid_list=False):
    return in_forbid_list or forbidden_before(line, start) or forbidden_after(line, end)


GATE_RUNNER = r"""
import json, sys, types
req = json.load(sys.stdin)
mod = types.ModuleType("_spm_board_prg")
mod.__file__ = req["path"]
sys.modules["_spm_board_prg"] = mod
exec(compile(req["src"], req["path"], "exec"), mod.__dict__)
fn = mod.substitution_near_git
if fn("x=$(git rev-parse HEAD)") is not True or fn("git status") is not False:
    print(json.dumps({"error": "control"})); sys.exit(0)
print(json.dumps({"hits": [i for i, c in enumerate(req["lines"]) if fn(c)]}))
"""


def gate_hits(candidates):
    """(set of candidate indexes the installed gate refuses, detector name). The gate file is read
    once; those exact bytes run, in a separate isolated, no-bytecode process with a timeout, and
    only if their git object ID equals the reviewed gate at GATE_REF (origin/main). Anything else
    falls back to the regex and says so."""
    f = LIBRARY / "skills/pr-release-gate/scripts/pr_release_gate.py"
    rel = "skills/pr-release-gate/scripts/pr_release_gate.py"
    fallback = lambda why: ({i for i, c in enumerate(candidates) if GITSUB_FALLBACK.search(c)}, f"fallback: {why}")
    try:
        src = f.read_bytes()
    except OSError:
        return fallback("gate not installed")
    rc, want = sh(["git", "--no-replace-objects", "-C", str(LIBRARY), "rev-parse", "--verify", "-q",
                   f"{GATE_REF}:{rel}"])
    have = hashlib.sha1(b"blob %d\0" % len(src) + src).hexdigest()
    if rc != 0 or want != have:
        return fallback(f"installed gate differs from {GATE_REF}")
    try:
        r = subprocess.run([sys.executable, "-I", "-B", "-c", GATE_RUNNER],
                           input=json.dumps({"src": src.decode("utf-8"), "path": str(f), "lines": candidates}),
                           capture_output=True, text=True, timeout=60)
        d = json.loads(r.stdout or "{}")
    except (OSError, subprocess.TimeoutExpired, ValueError) as e:  # UnicodeDecodeError is a ValueError
        return fallback(f"gate run {type(e).__name__}")
    if "hits" not in d:
        return fallback(f"gate {d.get('error', 'no answer')}")
    return set(d["hits"]), "gate"


def md_files():
    """(Markdown files to scan, number of folders os.walk could not read, skill folders left out because
    skills/HOMES.json gives them another home repo, Markdown files under a skill's nested library/ that
    are counted but not scanned, Markdown files in recorded run outputs (harness/runs/) counted but not
    scanned, the skill -> home map, whether HOMES.json was read, symlinked skill folders left out).
    An unreadable HOMES.json scans everything."""
    root = LIBRARY
    bad_dirs = []
    skipped_homes = skipped_nested = skipped_records = skipped_links = 0
    picks = [root / "CLAUDE.md", root / "AGENTS.md"] + sorted((root / "rules").glob("*.md"))
    sk = root / "skills"
    homes, homes_ok = {}, True
    try:
        homes = json.loads((sk / "HOMES.json").read_text())["homes"]
        if not isinstance(homes, dict):
            raise ValueError("homes is not a map")
    except (OSError, ValueError, KeyError, TypeError):
        homes, homes_ok = {}, False
    if sk.is_dir():
        for d in sorted(sk.iterdir()):
            if not d.is_dir() or d.name in SKIP_DIRS or d.name.startswith("."):
                continue
            if d.is_symlink():
                skipped_links += 1
                continue
            if homes.get(d.name, "library") != "library":
                skipped_homes += 1
                continue
            for dirpath, dirnames, filenames in os.walk(d, onerror=bad_dirs.append):
                rel = Path(dirpath).relative_to(d).parts
                if not rel and "library" in dirnames:
                    for _, _, nested in os.walk(Path(dirpath) / "library", onerror=bad_dirs.append):
                        skipped_nested += sum(f.endswith(".md") for f in nested)
                if Path(dirpath).name == "harness" and "runs" in dirnames:
                    for _, _, recs in os.walk(Path(dirpath) / "runs", onerror=bad_dirs.append):
                        skipped_records += sum(f.endswith(".md") for f in recs)
                dirnames[:] = [n for n in dirnames if n not in SKIP_DIRS and not n.startswith(".")
                               and not (not rel and n == "library")
                               and not (n == "runs" and Path(dirpath).name == "harness")]
                picks += [Path(dirpath) / f for f in sorted(filenames) if f.endswith(".md")]
    return ([p for p in picks if p.is_file()], len(bad_dirs), skipped_homes, skipped_nested, skipped_records,
            homes, homes_ok, skipped_links)


def frontmatter(text):
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end < 0:
        return None
    fm = {}
    for line in text[3:end].splitlines():
        m = re.match(r"^([A-Za-z_-]+):\s*(.*)$", line)
        if m:
            fm[m.group(1)] = m.group(2).strip().strip("'\"")
    return fm


WHY = {
    "abs-path": "machine-absolute path: wrong on every other machine",
    "refused-cmd": "tells the agent to run something the gates refuse or the rules forbid",
    "env-read": "reads a secret store the gates block",
    "gate-refused": "shell substitution around git/gh: the release gate refuses it",
    "retired-model": "names a model ID on the retired/retiring list",
    "dead-link": "relative link to a file that does not exist",
    "frontmatter": "SKILL.md frontmatter cannot route the skill",
    "oversize": "SKILL.md over 500 lines: loads too much context",
    "dangling-skill": "skill symlink points nowhere",
    "no-skill-md": "skill folder without SKILL.md: cannot load",
}


def check_md():
    items, unproven = [], []

    occurrences = {}

    def hit(cls, rel, line_no, text):
        h = hashlib.sha1(text.strip().encode()).hexdigest()[:10]
        n = occurrences[(cls, rel, h)] = occurrences.get((cls, rel, h), 0) + 1
        key = f"md|{cls}|{rel}|{h}" + (f"|{n}" if n > 1 else "")
        items.append({"cls": cls, "where": f"{rel}:{line_no}" if line_no else rel, "id": key})

    retired = retired_models()
    if retired is None:
        unproven.append("md: retired-models list missing")
    rx_retired = re.compile(r"(?<![\w.-])(" + "|".join(sorted(map(re.escape, retired), key=len, reverse=True))
                            + r")(?![\w.-])") if retired else None
    files, bad_dirs, skipped_homes, skipped_nested, skipped_records, homes, homes_ok, skipped_links = md_files()
    if not homes_ok:
        unproven.append("md: HOMES.json unreadable")
    if bad_dirs:
        unproven.append(f"md: {bad_dirs} folders unreadable")
    if not files:
        unproven.append(f"md: no Markdown found under {LIBRARY}")
    candidates, cand_at = [], []
    unread = 0
    for p in files:
        try:
            text = p.read_text(errors="replace")
        except OSError:
            unread += 1
            continue
        rel = str(p.relative_to(LIBRARY))
        fence, fence_lang = None, ""
        lists = ForbidLists()
        fence_forbid = False
        for i, line in enumerate(text.splitlines(), 1):
            m = FENCE.match(line)
            if m:
                mark = m.group(1)
                if fence is None:
                    fence, fence_lang = mark, m.group(2).lower()
                    fence_forbid = lists.fence(line)
                elif mark[0] == fence[0] and len(mark) >= len(fence) and not m.group(2):
                    fence = None
                continue
            in_forbid = fence_forbid if fence is not None else lists.step(line)
            for cls, rx, _ in MD_RULES:
                if any(not prohibited(line, mm.start(), mm.end(), in_forbid)
                       and not (cls == "abs-path" and PAST_DEFECT.search(line[:mm.start()]))
                       for mm in rx.finditer(line)):
                    hit(cls, rel, i, line)
            if fence is not None:
                code = [(line, 0)] if fence_lang in SHELL_FENCES else []
            else:
                code = [(c.group(1), c.start(1)) for c in re.finditer(r"`([^`\n]+)`", line)]
            for c, at in code:
                if re.search(r"\b(?:git|gh)\b", c) and not prohibited(line, at, at + len(c), in_forbid):
                    candidates.append(c)
                    cand_at.append((rel, i, line))
            if rx_retired:
                if any(not prohibited(line, mm.start(), mm.end(), in_forbid) for mm in rx_retired.finditer(line)):
                    hit("retired-model", rel, i, line)
            if fence is None:
                for target in LINK.findall(CODE_SPAN.sub(lambda c: " " * len(c.group(0)), line)):
                    if not PLACEHOLDER.match(target) and not (p.parent / target).exists():
                        hit("dead-link", rel, i, line + "|" + target)
        if p.name == "SKILL.md":
            fm = frontmatter(text)
            if not fm or not fm.get("name") or not fm.get("description"):
                hit("frontmatter", rel, 1, "missing name/description")
            elif fm["name"] != p.parent.name and p.parent.parent == LIBRARY / "skills":
                hit("frontmatter", rel, 1, "name differs from folder")
            if text.count("\n") > 500:
                hit("oversize", rel, 1, "oversize")
    hits, detector = gate_hits(candidates) if candidates else (set(), "gate: nothing to check")
    if detector.startswith("fallback"):
        unproven.append(f"md: {detector}")
    seen_line = set()
    for idx in sorted(hits):
        rel, i, line = cand_at[idx]
        if (rel, i) not in seen_line:
            seen_line.add((rel, i))
            hit("gate-refused", rel, i, line)
    if unread:
        unproven.append(f"md: {unread} files unreadable")
    sk = LIBRARY / "skills"
    if sk.is_dir():
        for d in sorted(sk.iterdir()):
            if homes.get(d.name, "library") != "library":
                continue  # machine-local or owned by another repo: an expected portability gap here
            if d.is_symlink() and not d.exists():
                hit("dangling-skill", f"skills/{d.name}", 0, "dangling")
            elif (d.is_dir() and not d.is_symlink() and not d.name.startswith((".", "_"))
                  and d.name not in SKIP_DIRS | {"library", "deprecated"} and not (d / "SKILL.md").exists()
                  and not installer_only(d) and not skill_container(d)):
                hit("no-skill-md", f"skills/{d.name}", 0, "no SKILL.md")
    return {"files": len(files), "items": items, "detector": detector, "unproven": unproven,
            "skipped_homes": skipped_homes, "skipped_nested": skipped_nested, "skipped_records": skipped_records,
            "skipped_links": skipped_links}


# ---------- cache ----------

class Deadline(BaseException):
    """Raised by the refresh alarm. A BaseException, so no `except Exception` swallows it."""


def retry_hours(unproven):
    """RETRY_H when a gap could close on its own soon (a fetch or page that failed), else a day."""
    return RETRY_H if any(not any(w in u for w in LASTING) for u in unproven) else MAX_AGE_H


def refresh():
    data = {"schema": SCHEMA, "checked_at": time.time(),
            "host": socket.gethostname(), "library": str(LIBRARY)}
    for key, fn in (("home", check_home), ("fresh", check_fresh), ("md", check_md)):
        try:
            data[key] = fn()
        except Exception as e:
            data[key] = {"error": f"{type(e).__name__}: {e}"}
    _, _, unproven, _, _ = findings(data)
    data["retry_at"] = data["checked_at"] + retry_hours(unproven) * 3600
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CACHE.with_name(f"{CACHE.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(json.dumps(data, indent=1))
        tmp.replace(CACHE)
    finally:
        tmp.unlink(missing_ok=True)
    return data


def try_flock(fh):
    """'locked', 'busy' (someone else holds it) or 'unsupported' (no flock on this platform
    or filesystem). Only EWOULDBLOCK/EAGAIN mean busy."""
    if fcntl is None:
        return "unsupported"
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return "locked"
    except OSError as e:
        return "busy" if e.errno in (errno.EWOULDBLOCK, errno.EAGAIN) else "unsupported"


def run_with_deadline(fn):
    """fn() under the whole-run deadline. With SIGALRM a Deadline is raised here; without it
    (Windows) a timer drops the marker and ends the process, so a trickling download never holds on."""
    if hasattr(signal, "SIGALRM"):
        def expire(*_):
            raise Deadline()
        old = signal.signal(signal.SIGALRM, expire)
        signal.alarm(REFRESH_DEADLINE_S)
        try:
            return fn()
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old)
    import threading

    def expire_hard():
        LOCK_MARK.unlink(missing_ok=True)
        record_last("deadline")
        os._exit(1)
    timer = threading.Timer(REFRESH_DEADLINE_S, expire_hard)
    timer.daemon = True
    timer.start()
    try:
        return fn()
    finally:
        timer.cancel()


def _pid_alive(pid):
    """True/False on POSIX; None on Windows, where os.kill(pid, 0) would end the process."""
    if os.name == "nt":
        return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:  # EPERM: alive, someone else's
        return True
    return True


def marker_age():
    """Seconds since the marker refresh started, or None when no refresh holds the marker. A marker
    left by a crash (its process is gone; where that cannot be asked, older than STUCK_S and so past
    any deadline; or still unreadable after MARK_GRACE_S) is removed, so the next refresh can start.
    A live process past STUCK_S is kept and reported stuck."""
    try:
        st = LOCK_MARK.stat()
        m = json.loads(LOCK_MARK.read_text())
        pid, age = int(m["pid"]), max(0.0, time.time() - float(m["started"]))
    except FileNotFoundError:
        return None
    except (OSError, ValueError, KeyError, TypeError):
        try:
            st = LOCK_MARK.stat()
        except OSError:
            return None
        pid, age = None, max(0.0, time.time() - st.st_mtime)
        if age < MARK_GRACE_S:
            return age
    alive = _pid_alive(pid) if pid is not None else False
    if (alive and age <= 2 * STUCK_S) or (alive is None and age <= STUCK_S):
        return age  # running, or hung: reported stuck past STUCK_S; past 2x it the pid was reused
    drop_stale_marker(st)
    return None


def drop_stale_marker(st):
    """Remove the marker described by `st`. It is renamed away first and checked: if a new refresh
    replaced it in between, that marker is put back (link fails rather than overwrite)."""
    aside = LOCK_MARK.with_name(f"{LOCK_MARK.name}.stale.{os.getpid()}")
    try:
        os.rename(LOCK_MARK, aside)
    except OSError:
        return
    try:
        got = aside.stat()
        if (got.st_ino, got.st_mtime) != (st.st_ino, st.st_mtime):
            os.link(aside, LOCK_MARK)
    except OSError:
        pass
    aside.unlink(missing_ok=True)


def marker_refresh():
    """Without flock: an exclusive-create marker file stands in for the lock, and the refresh runs
    under the same deadline. A marker left by a crashed run is cleared (marker_age), never kept."""
    for _ in range(2):
        try:
            fd = os.open(LOCK_MARK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            if marker_age() is not None:
                return False
    else:
        return False
    try:
        os.write(fd, json.dumps({"pid": os.getpid(), "started": time.time()}).encode())
        os.close(fd)
        run_with_deadline(refresh)
        return True
    finally:
        try:  # only our own marker: a crashed-run cleanup may have let another refresh in
            if json.loads(LOCK_MARK.read_text()).get("pid") == os.getpid():
                LOCK_MARK.unlink()
        except (OSError, ValueError, AttributeError):
            pass


def locked_refresh():
    """Run refresh under an flock held for its whole life; a second refresh exits at once.
    The kernel drops the lock when the process ends, so a crash never leaves it stuck, and a
    whole-run deadline stops a trickling download from holding it for ever (nothing is written)."""
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOCK, "a+") as fh:
        got = try_flock(fh)
        if got == "busy":
            return False
        if got == "unsupported":
            return marker_refresh()
        fh.seek(0)
        fh.truncate()
        fh.write(json.dumps({"pid": os.getpid(), "started": time.time()}))
        fh.flush()
        run_with_deadline(refresh)
        return True


def refresh_running():
    """None when no refresh is running, else seconds since it started (0 if unknown)."""
    age = marker_age()
    if age is not None:
        return age
    if not LOCK.exists():
        return None
    try:
        with open(LOCK, "a+") as fh:
            got = try_flock(fh)
            if got != "busy":
                return None
    except OSError:
        return None
    try:
        return max(0.0, time.time() - float(json.loads(LOCK.read_text())["started"]))
    except (OSError, ValueError, KeyError, TypeError):
        return 0.0


def spawn_refresh():
    """True when a background refresh was started now."""
    if os.environ.get("SPM_BOARD_NO_SPAWN") == "1" or refresh_running() is not None:
        return False
    try:
        subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "refresh"],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
        return True
    except OSError:
        return False


# ---------- findings ----------

MD_SCOPE = {"gate-refused": "md-gate", "retired-model": "md-retired"}  # parts read by their own tool


def skipped_note(m):
    """Say what the scan left out on purpose, so 'N files' is never read as 'everything'."""
    parts = []
    if m.get("skipped_homes"):
        parts.append(f"{m['skipped_homes']} skills owned by other repos (HOMES.json)")
    if m.get("skipped_nested"):
        parts.append(f"{m['skipped_nested']} files in nested library/ folders")
    if m.get("skipped_records"):
        parts.append(f"{m['skipped_records']} harness run records")
    if m.get("skipped_links"):
        parts.append(f"{m['skipped_links']} symlinked skill folders")
    return " (skipped: " + ", ".join(parts) + ")" if parts else ""


def findings(d):
    """(lines, problems, unproven, read_scopes, partial) from a cache dict.
    problems: ordered list of groups {"group", "text", "keys", "scope"}; one group per home or
    tool finding, one per Markdown class (its keys are that class's individual cases).
    read: the scopes that gave a full reading; only those may forget a case that has gone.
    Never says clean or ok for something it could not read; a line with an unread part says
    "partial" every time, not only the first time its gap was shown."""
    lines, problems, unproven, read = [], [], [], set()
    h = d.get("home", {})
    if "error" in h:
        unproven.append("home: check crashed")
        lines.append("home: unread (check crashed)")
    else:
        hu = h.get("unproven", [])
        unproven += hu
        read.update(h.get("read", []))
        probs = [list(p) for p in h.get("problems", [])]
        for p in probs:
            key, text = p[0], p[1]
            keys = p[2] if len(p) > 2 else [key]
            problems.append({"group": key, "text": text, "keys": keys, "scope": scope_of(keys[0]),
                             "names": {k: k.split("|", 1)[-1] for k in keys} if len(keys) > 1 else None})
        where = "canonical clone here" if h.get("present") else "canonical clone is on the Mini SSD, not checked here"
        wt = f"worktrees={h.get('worktrees', '?')} detached={h.get('detached', '?')}"
        full = h.get("present") and not hu
        state = "; ".join(p[1] for p in probs) if probs else ("clean" if full else "")
        gap = " (partial: " + "; ".join(u.removeprefix("home: ") for u in hu) + ")" if hu else ""
        lines.append(f"home: {where} · {wt}" + (f" · {state}" if state else "") + gap)
    f = d.get("fresh", {})
    if "error" in f:
        unproven.append("fresh: check crashed")
        lines.append("fresh: unread (check crashed)")
    else:
        parts = []
        for n, t in f.get("tools", {}).items():
            st = t.get("status")
            if st in ("update", "current", "ahead", "build-differs"):
                read.add(f"fresh-{n}")
            if st == "update":
                parts.append(f"{n} {t['installed']}→{t['latest']}")
                k = f"fresh-{n}-{release_line(t['latest'])}"
                problems.append({"group": k, "text": f"{n} {t['latest']} is out (installed {t['installed']})",
                                 "keys": [k], "scope": f"fresh-{n}"})
            elif st in ("current", "ahead"):
                parts.append(f"{n} {t['installed']} {'ok' if st == 'current' else 'ahead of latest'}")
            elif st == "absent":
                parts.append(f"{n} not found")
                unproven.append(f"fresh: {n} not found on PATH or in ~/.local/bin, /opt/homebrew/bin, /usr/local/bin")
            elif st == "build-differs":
                parts.append(f"{n} {t['installed']} (same version, build differs from {t['latest']})")
            else:
                parts.append(f"{n} ? (unread)")
                unproven.append(f"fresh: {n} version")
        news = f.get("claude_changelog") or []
        if not f.get("changelog_ok", True):
            unproven.append("fresh: changelog")
            parts.append("changelog unread")
        unproven += f.get("unproven", [])
        clip = lambda x: x if len(x) <= 90 else x[:89] + "…"
        pick = f.get("claude_pick")
        if len(news) > 1:
            parts.append(f"newest CC {news[0]}" + (f" ({pick})" if pick and pick != news[0] else "")
                         + f": {clip(news[1])}")
        cx, cu = f.get("codex_news") or {}, f.get("cursor_news") or {}
        if cx.get("items"):
            parts.append(f"codex {cx['version']}: {clip(cx['items'][0])}")
        if cu.get("sections"):
            parts.append(f"cursor {cu['version']}: {clip(cu['sections'][0]['title'])}")
        r = f.get("retired") or {}
        if r.get("ok") and r.get("rows"):
            read.add("fresh-retired")
        if r.get("ok") and r.get("missing"):
            miss = r["missing"]
            problems.append({"group": "fresh-retired-list",
                             "text": f"retired-models.txt lacks {len(miss)} model IDs Anthropic lists as "
                                     f"retired/deprecated (e.g. {', '.join(miss[:3])})",
                             "keys": [f"fresh-retired|{i}" for i in miss], "scope": "fresh-retired"})
        lines.append("fresh: " + " · ".join(parts))
    m = d.get("md", {})
    if "error" in m:
        unproven.append("md: check crashed")
        lines.append("md: unread (check crashed)")
    else:
        mu = m.get("unproven", [])
        unproven += mu
        # Each part forgets only what it read itself: a gate fallback or a missing retired list
        # must not make the founder see old gate-refused or retired-model cases again later.
        if not any("no Markdown" in u or "unreadable" in u for u in mu):
            read.add("md")
            if not str(m.get("detector", "")).startswith("fallback"):
                read.add("md-gate")
            if not any("retired-models list" in u for u in mu):
                read.add("md-retired")
        by = {}
        for it in m.get("items", []):
            by.setdefault(it["cls"], []).append(it)
        total = sum(len(v) for v in by.values())
        top = sorted(by.items(), key=lambda kv: -len(kv[1]))
        gap = " (partial: " + "; ".join(u.removeprefix("md: ") for u in mu) + ")" if mu else ""
        lines.append(f"md: {m.get('files', 0)} files, {total} findings"
                     + (" (" + ", ".join(f"{k} {len(v)}" for k, v in top[:5]) + ")" if top else "") + gap
                     + skipped_note(m))
        for cls, its in top:
            problems.append({"group": f"md-{cls}", "cls": cls, "items": its,
                             "keys": [i["id"] for i in its], "scope": MD_SCOPE.get(cls, "md")})
    return lines, problems, unproven, read, bool(unproven)


def release_line(v):
    """2.1.308 -> 2.1, 2026.10.22-abc -> 2026.10: patch releases ship daily; a finding per
    release line keeps 'a new version is out' from being re-shown every day."""
    return ".".join(re.findall(r"\d+", v.split("-")[0])[:2])


BUCKET = re.compile(r"^(home-\w+)\|>=(\d+)$")


def note_key(u):
    """Unproven notes are keyed by kind, numbers removed, so '2 files unreadable' becoming
    '3 files unreadable' is the same gap, not a new one."""
    return "unproven|" + re.sub(r"\d+(?:\.\d+)?", "N", u)


def load_cache():
    d = json.loads(CACHE.read_text())
    if not isinstance(d, dict) or d.get("schema") != SCHEMA:
        raise ValueError("cache schema")
    for k, typ in (("home", dict), ("fresh", dict), ("md", dict)):
        if not isinstance(d.get(k), typ):
            raise ValueError(f"cache {k}")
    return d


def scope_of(key):
    if key.startswith("md|"):
        return MD_SCOPE.get(key.split("|")[1], "md")
    if key.startswith("fresh-retired|"):
        return "fresh-retired"
    if key.startswith("fresh-"):
        for n in ("cursor-agent", "claude", "codex"):
            if key.startswith(f"fresh-{n}-"):
                return f"fresh-{n}"
    if key.startswith(("home-prunable", "home-detached")):
        return "home-wt"
    if key.startswith("home-"):
        return "home-canon"
    if key.startswith("unproven|"):
        return "unproven"
    return "other"


class _NoLock:
    def close(self):
        pass


NO_LOCK = _NoLock()  # no flock on this platform: save without one


def seen_lock():
    """An flock around read-compute-print-save of the shown list, so two /spm runs started
    together never both show the same new case. Waits up to 1s; None when it could not lock.
    Without flock (Windows, some filesystems) the list is saved unlocked: a rare double showing
    beats showing everything every run."""
    if fcntl is None:
        return NO_LOCK
    try:
        SEEN_LOCK.parent.mkdir(parents=True, exist_ok=True)
        fh = open(SEEN_LOCK, "a")
    except OSError:
        return None
    for _ in range(20):
        got = try_flock(fh)
        if got == "locked":
            return fh
        if got == "unsupported":
            fh.close()
            return NO_LOCK
        time.sleep(0.05)
    fh.close()
    return None


def probe_json(limit=5):
    """(result, seen_to_save). The caller prints the result first and saves after, so a run
    killed in between repeats findings next time rather than losing them."""
    if SSD_MISSING:
        return ({"line": "board: Mini SSD not mounted, no reading", "new": [], "more_new": 0,
                 "new_unproven": ["board SSD not mounted"], "known": 0, "known_unproven": 0}, None)
    try:
        d = load_cache()
    except (OSError, ValueError):
        started = spawn_refresh()
        note = "board no cache yet"
        try:
            last = json.loads(LAST.read_text())
            if last.get("outcome") != "ok" and time.time() - float(last.get("at", 0)) < MAX_AGE_H * 3600:
                note = f"board refresh failing ({last.get('outcome')}), no cache"
        except (OSError, ValueError, TypeError, AttributeError):
            pass
        line = "board: check started in background" if started else "board: no cache yet, no check started now"
        return ({"line": line, "new": [], "more_new": 0,
                 "new_unproven": [note], "known": 0, "known_unproven": 0}, None)
    lines, problems, unproven, read, _ = findings(d)
    now = time.time()
    age_h = (now - float(d.get("checked_at", 0))) / 3600
    running = refresh_running()
    try:
        last = json.loads(LAST.read_text())
        if last.get("outcome") != "ok" and float(last.get("at", 0)) > float(d.get("checked_at", 0)):
            unproven.append(f"board refresh failing ({last.get('outcome')})")
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    if running is not None and running > STUCK_S:
        unproven.append(f"board refresh stuck {running / 60:.0f} min")
    elif age_h > MAX_AGE_H or now > float(d.get("retry_at", 0)):
        spawn_refresh()
        if age_h > MAX_AGE_H:
            unproven.append(f"board cache {age_h:.0f}h old, refreshing")
    # Only a missing file is a first run. A damaged list is kept aside (*.bad) when the new one is
    # saved, so it costs one re-show, not one every run; an unreadable one is named and left alone.
    seen_bad = seen_damaged = False
    try:
        raw = json.loads(SEEN.read_text())
        if not seen_shape_ok(raw):
            raise ValueError("shown-list shape")
        prior = set(raw)
    except FileNotFoundError:
        prior = set()
    except OSError:
        prior, seen_bad = set(), True
    except (ValueError, TypeError):
        prior, seen_damaged = set(), True
    current = {k for g in problems for k in g["keys"]}
    groups_now = {BUCKET.match(k).group(1) for k in current if BUCKET.match(k)}
    # Problems: forget a remembered case only when its own scope was read cleanly and it is gone.
    # A count bucket is kept while its group still has any count, so a count that falls and
    # rises again inside what was already shown is not new.
    seen = {k for k in prior if not k.startswith("unproven|")
            and (k in current or scope_of(k) not in read
                 or (BUCKET.match(k) and BUCKET.match(k).group(1) in groups_now))}

    def is_seen(k):
        m = BUCKET.match(k)
        if not m:
            return k in seen
        return any((n := BUCKET.match(s)) and n.group(1) == m.group(1) and int(n.group(2)) >= int(m.group(2))
                   for s in seen)
    gate_fallback = str(d.get("md", {}).get("detector", "")).startswith("fallback")
    shown, new_texts, more, known, elsewhere = set(), [], 0, 0, 0
    for g in problems:
        fresh_keys = [k for k in g["keys"] if not is_seen(k)]
        if fresh_keys and (("items" in g and not MD_NEW_HERE)
                           or (g["scope"] == "md-gate" and gate_fallback)):
            # Not announced here (md is announced on the Mini only; the fallback regex is not
            # the gate). Not recorded and not counted as known: nobody was shown these. Markdown
            # left for the Mini is counted apart, so the verdict here is never CLEAN.
            if "items" in g and not MD_NEW_HERE:
                elsewhere += len(fresh_keys)
            continue
        if len(fresh_keys) < len(g["keys"]):
            known += 1  # this group has cases the founder has already seen
        if not fresh_keys:
            continue
        if len(new_texts) >= limit:
            more += 1  # left unshown and unrecorded, so it is still new next time
            continue
        tail = ", …; full list: board.py summary" if len(fresh_keys) > 3 else ""
        if "items" in g:
            ex = [i["where"] for i in g["items"] if i["id"] in fresh_keys][:3]
            new_texts.append(f"md {g['cls']}: {len(fresh_keys)} new ({', '.join(ex)}{tail})"
                             f" — {WHY.get(g['cls'], '')}")
        elif g.get("names") and len(fresh_keys) < len(g["keys"]):
            ex = [g["names"][k] for k in fresh_keys][:3]
            new_texts.append(f"{g['group']}: {len(fresh_keys)} new ({', '.join(ex)}{tail}); {g['text']} in all")
        else:
            new_texts.append(g["text"])
        shown.update(fresh_keys)
    # Unproven notes: shown once while they persist; a note that clears and returns is new again.
    # Over the limit they stay unrecorded too, so preflight never drops one it was not shown.
    # States of the Board itself go first and stay on the board line every run.
    live = ("refreshing", "stuck", "failing")
    live_notes = [u for u in unproven if any(w in u for w in live)]
    if live_notes:
        lines.append("state: " + "; ".join(live_notes))
    ukeys = {note_key(u): u for u in live_notes + [u for u in unproven if u not in live_notes]}
    fresh_u = [k for k in ukeys if k not in prior]
    known_u = len(ukeys) - len(fresh_u)
    room = max(0, limit - (1 if seen_bad or seen_damaged else 0))  # preflight shows `limit` notes in all
    new_unproven = [ukeys[k] for k in fresh_u[:room]]
    more += max(0, len(fresh_u) - room)
    seen |= {k for k in ukeys if k in prior} | set(fresh_u[:room]) | shown
    if seen_bad:
        new_unproven.insert(0, f"board shown-list unreadable ({SEEN})")
    elif seen_damaged:
        new_unproven.insert(0, f"board shown-list damaged ({SEEN}): the next recorded run sets it aside "
                               f"as {SEEN.name}.bad.* and starts a new one")
    return ({"line": f"board ({age_h:.0f}h ago): " + " | ".join(lines), "new": new_texts,
             "more_new": more, "new_unproven": new_unproven, "known": known,
             "known_unproven": known_u, "elsewhere": elsewhere}, None if seen_bad else seen)


def seen_shape_ok(raw):
    return isinstance(raw, list) and all(isinstance(k, str) for k in raw)


def save_seen(seen):
    SEEN.parent.mkdir(parents=True, exist_ok=True)
    try:
        ok = seen_shape_ok(json.loads(SEEN.read_text()))
    except FileNotFoundError:
        ok = True
    except (OSError, ValueError):
        ok = False
    if not ok:  # kept for a look under its own name, never silently lost or overwritten
        os.replace(SEEN, SEEN.with_name(f"{SEEN.name}.bad.{int(time.time())}.{os.getpid()}"))
    tmp = SEEN.with_name(f"{SEEN.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(sorted(seen)))
    tmp.replace(SEEN)


def probe(limit, budget=None, record=False):
    """Print one JSON line, then (record=True, preflight's --record) record what it showed.
    Never raises; always one line. A hand run without --record leaves the shown-list alone.
    budget: seconds preflight will wait; with under 0.5 s of it left, nothing is recorded,
    so preflight killing the probe can only cause a repeat, never a silent loss."""
    lock = seen_lock() if record else NO_LOCK
    try:
        try:
            result, seen = probe_json(limit)
        except Exception as e:
            result, seen = {"line": "", "new": [], "more_new": 0, "new_unproven": [f"board {type(e).__name__}"],
                            "known": 0, "known_unproven": 0}, None
        if not record:
            seen = None
        writable = seen is None or lock is not None
        if seen is not None and lock is None:
            # Busy or unlockable: show as usual but record nothing, so nothing is lost.
            result["new_unproven"].append("board shown-list busy, not recorded")
        if seen is not None and writable:
            try:
                if not os.access(SEEN.parent, os.W_OK) or (SEEN.exists() and not os.access(SEEN, os.W_OK)):
                    raise OSError("unwritable")
            except OSError:
                result["new_unproven"].append("board seen-list unwritable")
                seen = None
        sys.stdout.write(json.dumps(result) + "\n")
        sys.stdout.flush()
        if seen is not None and lock is not None and (budget is None or time.monotonic() - T0 < budget - 0.5):
            try:
                save_seen(seen)
            except OSError:
                pass  # already printed; the next run shows these again, which is the safe side
    finally:
        if lock is not None:
            lock.close()


def summary():
    try:
        d = load_cache()
    except (OSError, ValueError):
        print("board: no usable cache yet (run board.py refresh)")
        return
    lines, problems, unproven, _, _ = findings(d)
    for l in lines:
        print("board " + l)
    for g in problems:
        if "items" in g:
            print(f"  - md {g['cls']}: {len(g['items'])} — {WHY.get(g['cls'], '')}")
            for it in g["items"]:
                print(f"      {it['where']}")
        else:
            print("  - " + g["text"])
            for k in (g["keys"] if g.get("names") else []):
                print(f"      {g['names'][k]}")
    for u in unproven:
        print("  unproven: " + u)


def report():
    try:
        print(json.dumps(load_cache(), indent=1))
    except (OSError, ValueError):
        print("board: no usable cache yet (run board.py refresh)")


def record_last(outcome):
    try:
        LAST.parent.mkdir(parents=True, exist_ok=True)
        LAST.write_text(json.dumps({"at": time.time(), "outcome": outcome}))
    except OSError:
        pass


if __name__ == "__main__":
    args = sys.argv[1:]
    cmd = (args or ["summary"])[0]
    if cmd == "refresh":
        try:
            ok = locked_refresh()
        except Deadline:
            record_last("deadline")
            print(f"board: refresh passed its {REFRESH_DEADLINE_S}s deadline, nothing written", flush=True)
            os._exit(1)  # a slow download thread would otherwise keep the process alive
        except Exception as e:
            record_last(type(e).__name__)
            raise
        if ok:
            record_last("ok")
        print(f"board: cache written to {CACHE}" if ok else "board: another refresh is running")
    elif cmd == "report":
        report()
    elif cmd == "probe":
        try:
            lim = max(1, int(args[args.index("--limit") + 1])) if "--limit" in args else 5
        except (ValueError, IndexError):
            lim = 5
        try:
            budget = float(args[args.index("--budget") + 1]) if "--budget" in args else None
        except (ValueError, IndexError):
            budget = None
        try:
            probe(lim, budget, record="--record" in args)
        except Exception as e:
            print(json.dumps({"line": "", "new": [], "more_new": 0,
                              "new_unproven": [f"board {type(e).__name__}"], "known": 0, "known_unproven": 0}))
        sys.exit(0)
    else:
        try:
            summary()
        except Exception as e:
            print(f"board: summary failed {type(e).__name__}")
        sys.exit(0)
