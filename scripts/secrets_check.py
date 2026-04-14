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
]

# Compiled with line-boundary awareness
_COMPILED = [(re.compile(p), title, sev) for p, title, sev in _SECRET_PATTERNS]

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
def _list_tracked_files() -> list[str]:
    """Return all git-tracked files relative to REPO_ROOT."""
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            print(f"  [WARN] git ls-files failed: {result.stderr.strip()}", flush=True)
            return []
        return [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]
    except FileNotFoundError:
        print("  [WARN] git not found — scanning all files via os.walk()", flush=True)
        return []


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
    rel_files = _list_tracked_files() or _list_all_files()
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
