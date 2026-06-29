#!/usr/bin/env python3
"""
sync_claude_sessions.py — B.U.I.L.D. Inflow pipeline #1 (own inputs).

Mines the local Claude Code session lake (~/.claude/projects/**/*.jsonl) for
*content* — intent, decisions, user corrections, tools used, and shipped PRs —
and writes one redacted, OKF-formatted digest per session into the 2nd Brain
vault's process/ staging area, where improve-system + wiki-ingest pick it up.

This is the CONTENT pass. It is complementary to the FABLE distiller
(~/Fabel Prompt Engineer/scripts/fable-distill.mjs), which mines the SAME lake
for working-rhythm METRICS. We do not duplicate that — we extract knowledge.

Security: every text field is run through redact() before it touches disk.
The known-live secret shapes (Anthropic OAuth sk-ant-oat, Google AIza, …) are
covered explicitly — they are NOT in scripts/secrets_check.py's bank.

Usage:
    python scripts/sync_claude_sessions.py --dry-run --limit 5   # safe sample
    python scripts/sync_claude_sessions.py                       # incremental full run
    python scripts/sync_claude_sessions.py --since-last          # only changed files

Exit codes: 0 ok · 2 infra error.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
LAKE = HOME / ".claude" / "projects"
VAULT = HOME / "2nd Brain" / "2nd Brain"
DEFAULT_OUT = VAULT / "process" / "sessions"
MARKER = VAULT / "process" / ".sync-claude-sessions.json"

# ── Secret redaction bank ────────────────────────────────────────────────────
# Mirrors scripts/secrets_check.py _SECRET_PATTERNS and EXTENDS it with the
# shapes that bank misses but our transcripts actually contain.
_SECRET_PATTERNS: list[tuple[str, str]] = [
    (r"sk-ant-oat[0-9A-Za-z\-_]{20,}", "ANTHROPIC_OAUTH"),      # not in secrets_check
    (r"sk-ant-api[0-9A-Za-z\-_]{20,}", "ANTHROPIC_API"),
    (r"AIza[0-9A-Za-z\-_]{20,}", "GOOGLE_API"),                 # not in secrets_check
    (r"ghp_[0-9A-Za-z]{30,}", "GITHUB_PAT"),
    (r"gho_[0-9A-Za-z]{30,}", "GITHUB_OAUTH"),
    (r"github_pat_[0-9A-Za-z_]{30,}", "GITHUB_FINE_PAT"),
    (r"lin_api_[0-9A-Za-z]{30,}", "LINEAR_API"),
    (r"xox[baprs]-[0-9A-Za-z\-]{10,}", "SLACK_TOKEN"),
    (r"AKIA[0-9A-Z]{16}", "AWS_KEY"),
    (r"(?:sk|rk|pk)_live_[0-9A-Za-z]{20,}", "STRIPE_LIVE"),
    (r"sk-[a-zA-Z0-9]{48}", "OPENAI_API"),
    (r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}", "JWT"),
    (r"-----BEGIN (?:RSA|EC|DSA|OPENSSH) PRIVATE KEY-----", "PRIVATE_KEY"),
    (r"(?i)(?:password|passwd|pwd)\s*[=:]\s*['\"]?[^\s'\"]{8,}", "PASSWORD_ASSIGN"),
    (r"(?i)(?:secret|api_key|apikey|access_token|auth_token)\s*[=:]\s*['\"]?[A-Za-z0-9\-._~+/]{12,}", "SECRET_ASSIGN"),
    (r"(?i)bearer\s+[0-9a-zA-Z\-._~+/]{20,}", "BEARER"),
]
_COMPILED = [(re.compile(p), tag) for p, tag in _SECRET_PATTERNS]


def redact(text: str) -> str:
    """Replace every secret shape with a typed placeholder. Idempotent."""
    if not text:
        return text
    for rx, tag in _COMPILED:
        text = rx.sub(f"[REDACTED:{tag}]", text)
    return text


# ── JSONL parsing (shape verified 2026-06-29) ────────────────────────────────
def _text_of(content) -> str:
    """Flatten an Anthropic message.content (str | list of blocks) to text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "text" and b.get("text"):
                parts.append(b["text"])
            elif b.get("type") == "tool_result":
                inner = b.get("content")
                parts.append(_text_of(inner) if inner else "")
        return "\n".join(p for p in parts if p)
    return ""


def parse_session(path: Path) -> dict | None:
    """Extract a content digest from one session JSONL. None if no real turns."""
    intent = ""
    user_msgs: list[str] = []
    assistant_text: list[str] = []
    tools: dict[str, int] = {}
    prs: list[str] = []
    project = ""
    branch = ""
    ts = ""
    n_user = n_asst = 0

    try:
        lines = path.read_text(errors="replace").splitlines()
    except Exception:
        return None

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        t = d.get("type")
        if not ts:
            ts = d.get("timestamp", "")
        if d.get("cwd") and not project:
            project = os.path.basename(d["cwd"].rstrip("/"))
        if d.get("gitBranch") and not branch:
            branch = d["gitBranch"]
        if t == "user":
            txt = _text_of(d.get("message", {}).get("content"))
            txt = txt.strip()
            if txt and not txt.startswith("<"):  # skip tool_result/system-wrapped noise
                n_user += 1
                if not intent:
                    intent = txt
                if len(txt) < 600:
                    user_msgs.append(txt)
        elif t == "assistant":
            n_asst += 1
            msg = d.get("message", {})
            for b in msg.get("content", []) if isinstance(msg.get("content"), list) else []:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "tool_use":
                    tools[b.get("name", "?")] = tools.get(b.get("name", "?"), 0) + 1
                elif b.get("type") == "text" and b.get("text"):
                    assistant_text.append(b["text"])
        elif t == "pr-link":
            url = d.get("prUrl")
            if url:
                prs.append(url)

    if n_user == 0 and n_asst == 0:
        return None
    return {
        "intent": intent,
        "user_msgs": user_msgs,
        "assistant_text": assistant_text,
        "tools": tools,
        "prs": prs,
        "project": project or "unknown",
        "branch": branch,
        "ts": ts,
        "n_user": n_user,
        "n_asst": n_asst,
    }


# ── OKF digest rendering ─────────────────────────────────────────────────────
def _trunc(s: str, n: int) -> str:
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1] + "…"


def render_digest(sess: dict, session_id: str) -> str:
    r = redact
    intent = _trunc(r(sess["intent"]), 240) or "(no user prompt)"
    date = (sess["ts"] or "")[:10] or "undated"
    tools_sorted = sorted(sess["tools"].items(), key=lambda kv: -kv[1])
    tools_line = ", ".join(f"{k}×{v}" for k, v in tools_sorted[:12]) or "(none)"
    # last 2 assistant text blocks = conclusions/outcome
    conclusions = [_trunc(r(t), 400) for t in sess["assistant_text"][-2:] if t.strip()]
    corrections = [_trunc(r(m), 200) for m in sess["user_msgs"][1:6]]  # post-intent user turns
    prs = [r(p) for p in sess["prs"]]

    desc = _trunc(intent, 140)
    fm = [
        "---",
        "type: session-digest",
        f"name: session-{session_id[:8]}",
        f'description: "{desc}"',
        f"project: {sess['project']}",
        f"branch: {sess['branch']}",
        f"session_id: {session_id}",
        f"date: {date}",
        f"turns: {sess['n_user']}u/{sess['n_asst']}a",
        "---",
        "",
    ]
    body = [
        f"# Session digest — {sess['project']} ({date})",
        "",
        "## Intent",
        intent,
        "",
        "## Tools used",
        tools_line,
        "",
    ]
    if corrections:
        body += ["## Follow-up user turns (corrections / decisions)", ""]
        body += [f"- {c}" for c in corrections] + [""]
    if conclusions:
        body += ["## Conclusions (last assistant output)", ""]
        body += [c + "\n" for c in conclusions]
    if prs:
        body += ["## Shipped", ""] + [f"- {p}" for p in prs] + [""]
    return "\n".join(fm + body)


# ── Walk + incremental marker ────────────────────────────────────────────────
def find_jsonl(root: Path) -> list[Path]:
    return sorted(root.rglob("*.jsonl"), key=lambda p: -p.stat().st_mtime)


def load_marker() -> dict:
    try:
        return json.loads(MARKER.read_text())
    except Exception:
        return {}


def main() -> int:
    ap = argparse.ArgumentParser(description="Mine Claude session lake → vault digests")
    ap.add_argument("--dry-run", action="store_true", help="write to scratch, don't update marker")
    ap.add_argument("--since-last", action="store_true", help="only files newer than marker")
    ap.add_argument("--limit", type=int, default=0, help="cap number of sessions (0 = all)")
    ap.add_argument("--out-dir", default=None, help="override output dir")
    args = ap.parse_args()

    if not LAKE.exists():
        print(f"ERROR: lake not found: {LAKE}", file=sys.stderr)
        return 2

    out_dir = Path(args.out_dir) if args.out_dir else (
        Path("/private/tmp/claude-501/scratch-session-digests") if args.dry_run else DEFAULT_OUT
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    marker = load_marker()
    new_marker = dict(marker)
    files = find_jsonl(LAKE)

    written = skipped = empty = 0
    for path in files:
        if args.limit and written >= args.limit:
            break
        key = str(path)
        mtime = path.stat().st_mtime
        if args.since_last and marker.get(key) == mtime:
            skipped += 1
            continue
        sess = parse_session(path)
        if not sess:
            empty += 1
            continue
        session_id = path.stem
        digest = render_digest(sess, session_id)
        date = (sess["ts"] or "undated")[:10]
        fname = f"{date}-{sess['project']}-{session_id[:8]}.md"
        (out_dir / fname).write_text(digest)
        new_marker[key] = mtime
        written += 1

    if not args.dry_run:
        MARKER.parent.mkdir(parents=True, exist_ok=True)
        MARKER.write_text(json.dumps(new_marker, indent=0))

    print(f"sessions: {written} written, {skipped} skipped, {empty} empty → {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
