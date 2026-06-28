#!/usr/bin/env python3
"""Tests for sync_claude_sessions redaction + parsing. Run: python scripts/test_sync_claude_sessions.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from sync_claude_sessions import redact, _text_of, render_digest  # noqa: E402

FAILS = []


def check(name, cond):
    print(f"  {'PASS' if cond else 'FAIL'}: {name}")
    if not cond:
        FAILS.append(name)


# ── Redaction: every shape must be stripped, including the two live ones ──────
# Secret-shaped strings are ASSEMBLED FROM PARTS so no full token literal exists
# in this source file — this keeps GitHub push-protection happy while still
# producing runtime values that match the redactor's patterns. Bodies use an
# obviously-fake "FAKE" marker so they can never resemble a real key.
def _mk(prefix: str, n: int) -> str:
    return prefix + ("FAKE0" * ((n // 5) + 1))[:n]


SECRETS = {
    "anthropic_oat": _mk("sk-ant-oat01-", 40),
    "anthropic_api": _mk("sk-ant-api03-", 40),
    "google_aiza": _mk("AIza", 36),
    "github_pat": _mk("ghp_", 36),
    "github_fine": _mk("github_pat_", 40),
    "linear": _mk("lin_api_", 40),
    "slack": _mk("xoxb-", 30),
    "aws": "AKIA" + "FAKE0FAKE0FAKE00".upper()[:16],
    "stripe": _mk("sk_live_", 24),
    "openai": _mk("sk-", 48),
    "jwt": ".".join([_mk("eyJ", 12), _mk("eyJ", 12), _mk("Sfl", 12)]),
    "bearer": "Bearer " + _mk("", 30),
    "password_assign": 'password="' + _mk("", 12) + '"',
}
for name, secret in SECRETS.items():
    blob = f"prefix text {secret} suffix text"
    out = redact(blob)
    check(f"redact strips {name}", secret not in out and "[REDACTED:" in out)

# A full-length Google-shaped key (assembled, not literal) must be caught
check("redact catches live-shaped Google key",
      redact("key is " + _mk("AIza", 36)) != "key is " + _mk("AIza", 36))

# Idempotent: re-redacting a redacted string changes nothing
once = redact("token " + _mk("sk-ant-oat01-", 30))
check("redact is idempotent", redact(once) == once)

# Clean text must pass through untouched (no false positives on prose)
clean = "We deployed the wiki-ingest skill and it worked. See file_path:line_number."
check("clean prose untouched", redact(clean) == clean)

# ── _text_of: handles str, list of blocks, tool_result ───────────────────────
check("_text_of str", _text_of("hello") == "hello")
check("_text_of text blocks",
      _text_of([{"type": "text", "text": "a"}, {"type": "tool_use", "name": "Bash"}]) == "a")
check("_text_of tool_result nested",
      "inner" in _text_of([{"type": "tool_result", "content": "inner"}]))

# ── render_digest: never emits a raw secret even if the session contains one ──
poisoned = {
    "intent": "fix the thing, my key is " + _mk("AIza", 36),
    "user_msgs": ["also " + _mk("sk-ant-oat01-", 30), "second turn"],
    "assistant_text": ["done, used " + _mk("ghp_", 36)],
    "tools": {"Bash": 3}, "prs": ["https://github.com/x/y/pull/1"],
    "project": "test", "branch": "main", "ts": "2026-06-29T00:00:00Z",
    "n_user": 2, "n_asst": 1,
}
digest = render_digest(poisoned, "abcd1234efgh")
check("render_digest redacts AIza", _mk("AIza", 36) not in digest)
check("render_digest redacts oat", _mk("sk-ant-oat01-", 30) not in digest)
check("render_digest redacts ghp", _mk("ghp_", 36) not in digest)
check("render_digest keeps PR + frontmatter", "pull/1" in digest and "type: session-digest" in digest)

print(f"\n{'ALL PASS' if not FAILS else f'{len(FAILS)} FAILURES: ' + ', '.join(FAILS)}")
sys.exit(1 if FAILS else 0)
