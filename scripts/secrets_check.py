"""
secrets_check.py — Exposed-secrets CI smoke test for Pi-Dev-Ops.

Scans all git-tracked files (plus untracked .env* files) for committed secrets.
When violations are found:
  1. Prints each violation with file, line, and severity
  2. Auto-patches .gitignore to block the offending files from future commits
  3. Creates an URGENT Linear ticket (RA team)
  4. Fires a CRITICAL Telegram alert

Usage:
    python scripts/secrets_check.py [--repo-root PATH] [--dry-run]

Exit codes:
    0 — no secrets detected
    1 — one or more secrets detected (build MUST be blocked)
    2 — scan could not complete (infrastructure error)

Environment variables:
    LINEAR_API_KEY    — Linear personal API key (for auto-ticketing)
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID — for CRITICAL alert
    REPO_ROOT         — override repo root (default: parent of this script)
"""
import os
import re
import sys
import json
import subprocess
import datetime
import urllib.request
import urllib.error
import argparse
import base64

# ── CLI args ─────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="Pi-Dev-Ops secrets exposure check")
parser.add_argument(
    "--repo-root",
    default=os.environ.get("REPO_ROOT", os.path.join(os.path.dirname(__file__), "..")),
    help="Repository root to scan (default: parent of scripts/)",
)
parser.add_argument(
    "--dry-run",
    action="store_true",
    help="Report findings but do NOT modify .gitignore or raise tickets",
)
args = parser.parse_args()

REPO_ROOT = os.path.abspath(args.repo_root)
DRY_RUN = args.dry_run

# ── SCOPE LIMIT — READ BEFORE TRUSTING A [PASS] ───────────────────────────────
# This scanner sources its file list from
#   git ls-files --cached --others --exclude-standard
# FIXED 2026-08-02 — `--exclude-standard` was REMOVED, so gitignored files ARE now
# scanned. The history below is kept because the failure is instructive.
#
# It previously applied .gitignore, so **secrets in gitignored files were NEVER
# SCANNED**. Proven 2026-08-01 with the same fake AWS-shaped key in the same directory,
# gitignore as the only variable: docs/secret-control.ts -> DETECTED CRITICAL;
# docs/secret-control.tmp (matched by *.tmp) -> not listed, not scanned, MISSED.
#
# That matters here more than anywhere: .env.local, .env and credential files are exactly
# what .gitignore covers. A [PASS] means "no secrets in files git will show you", NOT
# "no secrets in this repo".
#
# Worse, the auto-patch below REMOVES FILES FROM THIS SCANNER'S OWN SCOPE: on finding a
# violation it appends the offending path to .gitignore, after which that file is never
# listed again and so never scanned again. Protective for committing; blinding for
# scanning. Use --dry-run when testing this script so it does not rewrite .gitignore.
#
# See ".gitignore is a silent scope reducer" in .harness/lesson-patterns.md. The fix
# pattern is fence/fail_open_check.py Class B: enumerate from an independent source, then
# ASK git about each item, so an ignored file fails loudly instead of vanishing.
# ──────────────────────────────────────────────────────────────────────────────

# ── Secret patterns (mirrors app/server/scanner.py _SECRET_PATTERNS) ─────────
_SECRET_PATTERNS: list[tuple[str, str, str]] = [
    (r"sk-ant-api[0-9A-Za-z\-_]{30,}", "Anthropic API key", "CRITICAL"),
    (r"ghp_[0-9A-Za-z]{36}", "GitHub personal access token", "CRITICAL"),
    (r"lin_api_[0-9A-Za-z]{40}", "Linear API key", "CRITICAL"),
    (r"AKIA[0-9A-Z]{16}", "AWS access key ID", "CRITICAL"),
    (r"sk-[a-zA-Z0-9]{48}", "OpenAI API key", "CRITICAL"),
    (r"-----BEGIN (RSA|EC|DSA|OPENSSH) PRIVATE KEY-----", "Private key in source", "CRITICAL"),
    (r"(?i)(password|passwd|pwd)\s*=\s*['\"][^'\"\n]{8,}['\"]", "Hardcoded password", "HIGH"),
    (r"(?i)(secret|api_key|apikey|token)\s*=\s*['\"][^'\"\n]{8,}['\"]", "Hardcoded secret", "HIGH"),
    (r"(?i)bearer\s+[0-9a-zA-Z\-._~+/]{20,}", "Bearer token in source", "HIGH"),
    (r"(?i)(?:db|database)_?(?:url|uri|connection)\s*=\s*['\"]postgresql://[^'\"]+['\"]",
     "DB connection string", "HIGH"),
    # ── Added 2026-08-02. The previous ten shapes omitted the three with the most reach in
    # this estate, so an all-clear could only ever have meant "clean for ten shapes":
    #   - a Supabase service-role JWT bypasses RLS on every fenced production database; it is
    #     the one key that makes row-level security irrelevant
    #   - a live Stripe key is billing
    #   - a Telegram bot token is the notification bus, which is also the approval channel
    (r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{20,}",
     "JWT (Supabase service-role/anon key or similar)", "CRITICAL"),
    (r"\b(sk|rk)_live_[0-9A-Za-z]{16,}", "Stripe LIVE secret key", "CRITICAL"),
    (r"\b(sk|rk)_test_[0-9A-Za-z]{16,}", "Stripe test secret key", "HIGH"),
    (r"\b\d{8,10}:AA[0-9A-Za-z_-]{32,}", "Telegram bot token", "CRITICAL"),
]

# NOTE ON THE JWT PATTERN. It matches Supabase ANON keys too, which are public by design and
# legitimately appear in NEXT_PUBLIC_* vars. That is deliberate: a regex cannot tell an anon
# key from a service-role key without decoding the payload, and the two failure directions are
# not symmetric. A false positive on an anon key costs one triage; a miss on a service-role key
# costs RLS across the estate. Triage the hits; do not narrow the pattern.

# Compiled with line-boundary awareness
_COMPILED = [(re.compile(p), title, sev) for p, title, sev in _SECRET_PATTERNS]


def _is_public_anon_jwt(value: str) -> bool:
    """Return true only for a JWT whose payload explicitly identifies Supabase anon access.

    Supabase anon keys are intentionally browser-public and are already documented as such in
    SECURITY.md. Decoding the unsigned payload is classification, not authentication: every
    other JWT shape, malformed token, or role still fails closed as a secret finding.
    """
    try:
        payload = value.split(".", 2)[1]
        payload += "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload).decode("utf-8"))
        return claims.get("iss") == "supabase" and claims.get("role") == "anon"
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return False

# ── Placeholder exclusion (skip false positives from docs/examples) ───────────
_PLACEHOLDER_RE = re.compile(
    r"<redacted>|<your-|<paste|<configured>|your-password|example\.com"
    r"|\$\{[A-Z_]+|process\.env\.|os\.environ"
    r"|AKIAIOSFODNN7EXAMPLE|REPLACE_ME|INSERT_YOUR|YOUR_.*_HERE|PASTE_YOUR"
    r"|fake[_-]?(?:key|token|secret|password|api)"
    r"|dummy[_-]?(?:key|token|secret|password)"
    r"|sample[_-]?(?:key|token|secret|password)"
    r"|test[_-]?(?:key|token|secret|password|api)"
    r"|demo[_-]?(?:key|token|secret|password)"
    r"|placeholder|not.?a.?real|not.?valid|changeme|change.?this"
    r"|REDACTED|MASKED|CENSORED|\[hidden\]|\[removed\]"
    r"|\$[A-Z_][A-Z0-9_]+"
    r"|%[A-Z_][A-Z0-9__%]+"
    r"|\{\{[^}]+\}\}",
    re.IGNORECASE,
)

# File extensions / names never scanned (docs, env templates by design)
_SKIP_EXTS = {".md", ".rst", ".lock", ".png", ".jpg", ".jpeg", ".gif", ".svg",
              ".ico", ".woff", ".woff2", ".ttf", ".eot", ".pdf", ".zip",
              ".tar", ".gz", ".pyc"}
_SKIP_NAMES = {
    ".env", ".env.local", ".env.production", ".env.development", ".env.example",
    ".env.test", "READY_TO_DEPLOY.md", "DEPLOYMENT_GUIDE.md",
}
# Path prefixes never scanned — test fixtures contain intentional fake secrets;
# scanner.py stores regex patterns as string literals (not real credentials);
# .harness/ JSON files are generated analysis output that may reference previously
# removed credentials in description fields (not live secrets).
_SKIP_PATH_PREFIXES = (
    "tests/",
    "test/",
    "app/server/scanner.py",   # contains secret patterns as regex documentation
    "app/server/config.py",    # exclusion list comments trigger pattern matches; real secrets are os.environ.get()
    ".harness/",               # generated analysis output — not committed secrets
)

# ── Exclusion preconditions ──────────────────────────────────────────────────
#
# EVERY EXCLUSION IS A CLAIM ABOUT THE WORLD, AND CLAIMS EXPIRE.
#
# `.harness/` was skipped above on the stated ground that it holds "generated analysis output —
# not committed secrets". That was true the day it was written. On 2026-06-16 a Codex Stop hook
# began running `autogit ship` — commit AND push — at the end of every session, and `.harness/`
# started being committed and pushed to a PUBLIC repository. 98 MB accumulated behind an
# exclusion whose premise had silently become false, including an entire vendored copy of
# another product's working tree. Nothing rechecked, because nothing was ever asked to.
#
# A skipped path is indistinguishable from a clean path in the output. That is the same shape as
# a vacuous control: the check reports health about its own aim, not about the world. So each
# exclusion now DECLARES why it is safe, and the declaration is asserted at run time.
#
# `not-committed` is the only one that is fully machine-checkable, and it is the one that broke.
NOT_COMMITTED = "not-committed"          # verifiable: nothing under it may be git-tracked
REVIEWED_FIXTURE = "reviewed-fixture"    # committed deliberately; NOT machine-verifiable
BINARY = "binary"                        # non-text by format
UNVERIFIED_TEXT = "unverified-text"      # scannable text with no stated basis for skipping

_PATH_PRECONDITIONS: dict[str, str] = {
    "tests/": REVIEWED_FIXTURE,
    "test/": REVIEWED_FIXTURE,
    "app/server/scanner.py": REVIEWED_FIXTURE,
    "app/server/config.py": REVIEWED_FIXTURE,
    ".harness/": NOT_COMMITTED,
    # Installed third-party packages, skipped by the _HEAVY filter in _list_tracked_files().
    # Verified rather than trusted: if vendored dependencies are ever committed, this fires
    # and fails the run instead of silently leaving 8k+ committed files unscanned.
    ":(glob)**/site-packages/**": NOT_COMMITTED,
}

# Binary formats cannot carry a greppable secret; .md/.rst/.lock plainly can, and are skipped
# for convenience rather than for a reason. Naming that honestly is the point — they are
# reported every run so the cost of the convenience stays visible instead of invisible.
_EXT_PRECONDITIONS: dict[str, str] = {
    **{e: BINARY for e in (".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".woff",
                           ".woff2", ".ttf", ".eot", ".pdf", ".zip", ".tar", ".gz", ".pyc")},
    **{e: UNVERIFIED_TEXT for e in (".md", ".rst", ".lock")},
}


def _tracked_under(prefix: str) -> list[str]:
    """Files git currently tracks under `prefix`. Empty list == the not-committed claim holds."""
    try:
        r = subprocess.run(["git", "ls-files", "--", prefix], cwd=REPO_ROOT,
                           capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            return []
        return [ln for ln in r.stdout.splitlines() if ln.strip()]
    except Exception:
        return []


def verify_exclusion_preconditions() -> tuple[list[str], list[str]]:
    """Assert every exclusion's stated reason still holds.

    Returns (violations, warnings). A violation means an exclusion is actively hiding files it
    claimed could not exist — treat it as a failed run, not a note, because the scan that
    follows is unsound for exactly those paths.
    """
    violations: list[str] = []
    warnings: list[str] = []

    for prefix, kind in _PATH_PRECONDITIONS.items():
        if kind == NOT_COMMITTED:
            tracked = _tracked_under(prefix)
            if tracked:
                violations.append(
                    f"{prefix!r} is skipped because it is {kind!r}, but git tracks "
                    f"{len(tracked)} file(s) under it (e.g. {tracked[0]}). The exclusion's "
                    f"premise is false, so those files are committed AND unscanned."
                )
        elif kind == REVIEWED_FIXTURE:
            n = len(_tracked_under(prefix))
            if n:
                warnings.append(f"{prefix!r}: {n} tracked file(s) hidden by a {kind!r} exclusion "
                                f"(committed on purpose; not machine-verifiable)")

    for ext, kind in _EXT_PRECONDITIONS.items():
        if kind != UNVERIFIED_TEXT:
            continue
        n = len([p for p in _tracked_under(".") if p.lower().endswith(ext)])
        if n:
            warnings.append(f"{ext!r}: {n} tracked text file(s) hidden by an {kind!r} exclusion "
                            f"— these CAN carry secrets; skipped for convenience only")

    return violations, warnings


# ── .gitignore patterns that should always cover sensitive files ──────────────
_REQUIRED_GITIGNORE_ENTRIES = [
    ".env",
    ".env.*",
    "!.env.example",
    "*.pem",
    "*.key",
    ".harness/.password-hash",
    ".harness/.session-secret",
]


# ── Finding dataclass (simple dict) ──────────────────────────────────────────
def _make_finding(path: str, line: int, title: str, severity: str, snippet: str) -> dict:
    return {
        "path": path,
        "line": line,
        "title": title,
        "severity": severity,
        "snippet": snippet[:120],
    }


# ── File enumeration ──────────────────────────────────────────────────────────
def _list_tracked_files() -> list[str] | None:
    """Return files to scan, relative to REPO_ROOT. None means git could not be consulted.

    The None/[] distinction is load-bearing. An empty list is a real answer — every
    enumerated file was excluded — whereas None means enumeration never happened. Returning
    [] for both let `scan_all` treat "nothing left to scan" as "git is unavailable" and fall
    back to walking the whole tree, which re-admitted the vendored files the filter had just
    removed.
    """
    try:
        # NOTE the ABSENT --exclude-standard. Including it meant gitignored files were
        # never scanned, and .env.local / *.pem / credential dumps are exactly what
        # .gitignore covers — the paths most worth scanning were the ones skipped.
        # Heavy generated trees are dropped below instead, by path, so the exclusion is
        # explicit and reviewable rather than inherited silently from .gitignore.
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            print(f"  [WARN] git ls-files failed: {result.stderr.strip()}", flush=True)
            return None
        # Dropping --exclude-standard pulls in node_modules/.next/etc. Filter by path.
        #
        # `site-packages/` is matched on STRUCTURE, not on the virtualenv's directory name.
        # Naming each venv directory ('.venv/', 'venv/') looked equivalent and was not: this
        # repo also carries a `.venv-verify/`, and `'.venv/' in '.venv-verify/lib/...'` is
        # False — the next character is '-', not '/'. That one miss put 8,099 vendored files
        # into every local scan and reported 102 third-party matches as exposed secrets, so
        # the gate exited 1 on a clean tree and rewrote .gitignore. A gate that always cries
        # wolf is a gate nobody reads. Any interpreter layout puts installed packages under
        # `site-packages/`, so this holds for a venv of any name — and the precondition below
        # verifies the exclusion instead of trusting it.
        _HEAVY = ("node_modules/", ".next/", ".git/", "dist/", "build/", ".venv/",
                  "venv/", "site-packages/", "__pycache__/", ".pytest_cache/",
                  ".turbo/", "coverage/", ".omx/")
        out = []
        for ln in result.stdout.splitlines():
            f = ln.strip()
            if not f:
                continue
            n = f.replace("\\", "/")
            if any(h in n for h in _HEAVY):
                continue
            out.append(f)
        return out
    except FileNotFoundError:
        print("  [WARN] git not found — scanning all files via os.walk()", flush=True)
        return None


def _list_all_files() -> list[str]:
    """Fallback: walk the repo tree, skip .git/ and common binary dirs."""
    paths = []
    skip_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}
    for dirpath, dirnames, filenames in os.walk(REPO_ROOT):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            paths.append(os.path.relpath(full, REPO_ROOT))
    return paths


# ── Secret scanning ───────────────────────────────────────────────────────────
def _scan_file(rel_path: str) -> list[dict]:
    """Scan a single file for secret patterns. Returns list of findings."""
    rel_norm = rel_path.replace("\\", "/")
    basename = os.path.basename(rel_norm)
    ext = os.path.splitext(basename)[1].lower()

    if ext in _SKIP_EXTS:
        return []
    if basename in _SKIP_NAMES:
        return []
    # Skip known-safe path prefixes (test fixtures, the scanner module itself)
    if any(rel_norm.startswith(prefix) for prefix in _SKIP_PATH_PREFIXES):
        return []

    full_path = os.path.join(REPO_ROOT, rel_path)
    try:
        with open(full_path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except (OSError, PermissionError):
        return []

    lines = text.split("\n")
    findings = []
    for pattern, title, severity in _COMPILED:
        for match in pattern.finditer(text):
            matched_text = match.group(0)
            if title.startswith("JWT (") and _is_public_anon_jwt(matched_text):
                continue
            # Skip placeholders / example values
            if _PLACEHOLDER_RE.search(matched_text):
                continue
            line_num = text[: match.start()].count("\n") + 1
            line_text = lines[line_num - 1] if line_num <= len(lines) else ""
            if _PLACEHOLDER_RE.search(line_text):
                continue
            findings.append(_make_finding(rel_path, line_num, title, severity, line_text.strip()))
    return findings


def scan_all() -> list[dict]:
    """Enumerate and scan all relevant files. Returns deduplicated findings."""
    tracked = _list_tracked_files()
    rel_files = _list_all_files() if tracked is None else tracked
    all_findings: list[dict] = []
    for rel in rel_files:
        all_findings.extend(_scan_file(rel))
    return all_findings


# ── .gitignore auto-patch ─────────────────────────────────────────────────────
def _gitignore_path() -> str:
    return os.path.join(REPO_ROOT, ".gitignore")


def _load_gitignore() -> list[str]:
    gp = _gitignore_path()
    if not os.path.isfile(gp):
        return []
    with open(gp, "r", encoding="utf-8") as fh:
        return fh.read().splitlines()


def patch_gitignore(findings: list[dict]) -> list[str]:
    """Ensure required entries AND any finding paths are in .gitignore.
    Returns list of lines added. Writes to .gitignore (unless DRY_RUN)."""
    existing = _load_gitignore()
    existing_set = set(existing)
    additions: list[str] = []

    # Always ensure the baseline required entries exist
    for entry in _REQUIRED_GITIGNORE_ENTRIES:
        if entry not in existing_set:
            additions.append(entry)

    # Add exact file paths from findings (so the specific leaky file is blocked)
    for f in findings:
        path_entry = f["path"].replace("\\", "/")
        if path_entry not in existing_set and path_entry not in additions:
            additions.append(path_entry)

    if not additions:
        return []

    if DRY_RUN:
        print(f"  [DRY-RUN] Would add {len(additions)} entries to .gitignore:")
        for a in additions:
            print(f"    + {a}")
        return additions

    gp = _gitignore_path()
    with open(gp, "a", encoding="utf-8") as fh:
        fh.write("\n# ── secrets_check.py auto-patch " + datetime.date.today().isoformat() + " ──\n")
        for entry in additions:
            fh.write(entry + "\n")
    print(f"  [GITIGNORE] Added {len(additions)} entries to .gitignore", flush=True)
    return additions


# ── Linear ticket ─────────────────────────────────────────────────────────────
_LINEAR_URL = "https://api.linear.app/graphql"
_LINEAR_TEAM_ID = "a8a52f07-63cf-4ece-9ad2-3e3bd3c15673"
_LINEAR_PROJECT_ID = "f45212be-3259-4bfb-89b1-54c122c939a7"


def raise_linear_ticket(findings: list[dict]) -> str | None:
    """Create an URGENT Linear ticket. Returns identifier or None."""
    api_key = os.environ.get("LINEAR_API_KEY", "")
    if not api_key:
        print("  [LINEAR] LINEAR_API_KEY not set — skipping ticket creation", flush=True)
        return None
    if DRY_RUN:
        print(f"  [DRY-RUN] Would create URGENT Linear ticket for {len(findings)} secret(s)", flush=True)
        return None

    rows = "\n".join(
        f"- `{f['path']}:{f['line']}` — **{f['title']}** ({f['severity']})"
        for f in findings[:20]
    )
    mutation = """
    mutation CreateIssue($input: IssueCreateInput!) {
        issueCreate(input: $input) { success issue { identifier } }
    }
    """
    variables = {
        "input": {
            "teamId": _LINEAR_TEAM_ID,
            "projectId": _LINEAR_PROJECT_ID,
            "title": f"[SECRETS] {len(findings)} exposed secret(s) detected in repo — immediate action required",
            "description": (
                "## CRITICAL: Exposed Secrets Detected\n\n"
                f"`secrets_check.py` found **{len(findings)} secret violation(s)** "
                f"in the Pi-Dev-Ops repository.\n\n"
                "### Violations\n"
                f"{rows}\n\n"
                "### Immediate Actions Required\n"
                "1. Rotate **all** exposed credentials immediately\n"
                "2. Verify `.gitignore` patches applied by `secrets_check.py`\n"
                "3. Run `git log --all -- <file>` to check exposure history\n"
                "4. If secrets were ever pushed to remote: treat them as compromised\n\n"
                "Run `python scripts/secrets_check.py` to reproduce."
            ),
            "priority": 1,  # Urgent
        }
    }
    payload = json.dumps({"query": mutation, "variables": variables}).encode()
    req = urllib.request.Request(
        _LINEAR_URL, data=payload, method="POST",
        headers={"Content-Type": "application/json", "Authorization": api_key},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
        ident = (result.get("data", {}).get("issueCreate", {}).get("issue") or {}).get("identifier", "?")
        print(f"  [LINEAR] Created URGENT ticket: {ident}", flush=True)
        return ident
    except Exception as exc:
        print(f"  [LINEAR] Ticket creation failed: {exc}", flush=True)
        return None


# ── Telegram alert ────────────────────────────────────────────────────────────
def send_telegram_alert(findings: list[dict], ticket_id: str | None) -> None:
    """Fire a CRITICAL Telegram message. Swallows errors."""
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not bot_token or not chat_id:
        print("  [TELEGRAM] TELEGRAM_BOT_TOKEN/CHAT_ID not set — skipping alert", flush=True)
        return
    if DRY_RUN:
        print(f"  [DRY-RUN] Would send CRITICAL Telegram alert ({len(findings)} secret(s))", flush=True)
        return

    top = findings[:5]
    lines = "\n".join(f"• `{f['path']}:{f['line']}` {f['title']}" for f in top)
    ticket_ref = f"\n🎫 Linear: {ticket_id}" if ticket_id else ""
    text = (
        f"🚨 *CRITICAL: Exposed Secrets Detected*\n\n"
        f"Pi-Dev-Ops repo contains *{len(findings)} secret violation(s)*.\n\n"
        f"{lines}"
        f"{' …and more' if len(findings) > 5 else ''}"
        f"\n\nRotate all credentials immediately.{ticket_ref}"
    )
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
    }).encode()
    req = urllib.request.Request(url, data=payload, method="POST",
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10):
            pass
        print("  [TELEGRAM] CRITICAL alert sent", flush=True)
    except Exception as exc:
        print(f"  [TELEGRAM] Alert failed: {exc}", flush=True)


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> int:
    print(f"\nPi-Dev-Ops Secrets Check — {REPO_ROOT}")
    print("=" * 60)
    if DRY_RUN:
        print("  MODE: dry-run (no writes, no tickets, no alerts)\n")

    # 0. Assert the exclusions before trusting anything they hide.
    #    Runs FIRST: a clean scan result is meaningless if an exclusion is concealing tracked
    #    files it claimed could not exist. This is the check that would have caught .harness/
    #    on 2026-06-16 instead of 47 days and 98 MB later.
    print("Verifying exclusion preconditions…", flush=True)
    violations, warnings = verify_exclusion_preconditions()
    for w in warnings:
        print(f"  [WARN] {w}")
    if violations:
        print("\n[FAIL] Exclusion precondition violated — this scan is NOT sound:\n")
        for v in violations:
            print(f"  [VIOLATION] {v}")
        print("\n  Fix the exclusion or the world it describes. Do NOT widen the exclusion to\n"
              "  match current behaviour — that is how the original defect was written.\n")
        return 2
    print("  all exclusion preconditions hold\n", flush=True)

    # 1. Scan
    print("Scanning git-tracked files for exposed secrets…", flush=True)
    findings = scan_all()

    if not findings:
        print("\n[PASS] No exposed secrets detected.\n")
        return 0

    # 2. Report
    print(f"\n[FAIL] {len(findings)} secret violation(s) found:\n")
    for f in findings:
        sev_tag = f"[{f['severity']}]"
        print(f"  {sev_tag:<12} {f['path']}:{f['line']} — {f['title']}")
        print(f"             {f['snippet'][:100]}")
    print()

    # 3. Auto-patch .gitignore
    print("Patching .gitignore…", flush=True)
    added = patch_gitignore(findings)
    if added:
        print(f"  Added: {', '.join(added[:6])}{'…' if len(added) > 6 else ''}")
    else:
        print("  .gitignore already covers all finding paths.")

    # 4. Raise Linear ticket
    print("Raising URGENT Linear ticket…", flush=True)
    ticket_id = raise_linear_ticket(findings)

    # 5. Telegram alert
    print("Firing CRITICAL Telegram alert…", flush=True)
    send_telegram_alert(findings, ticket_id)

    # 6. Write harness log
    _log_to_harness(findings, ticket_id)

    print(f"\n{'=' * 60}")
    print(f"RESULT: {len(findings)} secret(s) exposed — credentials must be rotated.")
    if not DRY_RUN:
        print("  .gitignore patched to prevent re-commit.")
        print("  URGENT Linear ticket raised.")
    print()
    return 1


def _log_to_harness(findings: list[dict], ticket_id: str | None) -> None:
    """Append a structured record to .harness/secrets-scan/YYYY-MM-DD.jsonl."""
    try:
        log_dir = os.path.join(REPO_ROOT, ".harness", "secrets-scan")
        os.makedirs(log_dir, exist_ok=True)
        today = datetime.date.today().isoformat()
        log_path = os.path.join(log_dir, f"{today}.jsonl")
        row = json.dumps({
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "findings": len(findings),
            "critical": sum(1 for f in findings if f["severity"] == "CRITICAL"),
            "high": sum(1 for f in findings if f["severity"] == "HIGH"),
            "ticket": ticket_id,
            "dry_run": DRY_RUN,
            "paths": list({f["path"] for f in findings}),
        })
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(row + "\n")
    except Exception:
        pass  # Observability must never block the check result


if __name__ == "__main__":
    sys.exit(main())
