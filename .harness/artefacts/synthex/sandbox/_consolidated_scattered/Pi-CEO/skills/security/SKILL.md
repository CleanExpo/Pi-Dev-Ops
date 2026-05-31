---
name: security
description: Security patterns and anti-patterns for the Pi-Dev-Ops codebase — path traversal, HMAC webhooks, secrets hygiene, timing-safe comparisons, autonomous permission grants.
---

# Security Best Practices

Apply whenever touching auth, session handling, file paths derived from user input, webhook signature verification, or autonomous harness configuration.

## Input Validation & Path Traversal

**DO** sanitise every session ID before using it in a file path.

```python
import re
safe_sid = re.sub(r'[^a-zA-Z0-9]', '', sid)
```

`sid='../../etc/passwd'` is a valid HTTP string. Without sanitisation it becomes a path traversal attack.
Already implemented in `app/server/persistence.py:_safe_sid()` — never bypass it, never accept a raw `session_id` in a file-open call.

**DON'T** construct file paths from request parameters without this check, even in internal routes.

## HMAC Webhook Verification

**DO** use `hmac.compare_digest()` for all webhook signature checks — it is timing-safe.

```python
import hmac, hashlib

def verify_github(payload: bytes, secret: str, header: str) -> bool:
    expected = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header)

def verify_linear(payload: bytes, secret: str, header: str) -> bool:
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header)
```

GitHub header: `x-hub-signature-256: sha256=<hex>`
Linear header: `Linear-Signature: <hex>`
The formats differ — handle both explicitly. See `app/server/webhooks.py`.

**DON'T** use `==` for HMAC comparison — it leaks timing information.

## Secrets Hygiene

**DO** keep secrets in environment variables only. Load via:

```python
from dotenv import load_dotenv
load_dotenv(override=True)  # override=True required — claude CLI sets ANTHROPIC_API_KEY="" in shell
```

**DON'T** commit `.claude/settings.local.json`. It contains local tool allowlists specific to one machine and leaks configuration if shared. It is already in `.gitignore` — verify it stays there.

**DON'T** put real credentials in docs, runbooks, or scripts/. A Pi-SEO dry-run on 2026-04-10 found 6 exposed keys across `docs/runbooks/` and `scripts/` in portfolio repos (dr-nrpg, synthex, ccw-crm). Even if they are "example values", any committed key must be rotated immediately.

**DO** add a `detect-secrets` pre-commit hook to every portfolio repo before enabling Pi-SEO scanning:

```yaml
# .pre-commit-config.yaml
- repo: https://github.com/Yelp/detect-secrets
  rev: v1.4.0
  hooks:
    - id: detect-secrets
```

## Autonomous Harness Permissions

Long-running harnesses stall at 3 AM waiting for a click that never comes if permissions are not pre-granted. **All three layers must be set**:

1. `.claude/settings.json` — project-level allowlist:
   ```json
   {
     "permissions": {
       "defaultMode": "bypassPermissions",
       "allow": ["Bash", "Read", "Write", "Edit", "Glob", "Grep"]
     }
   }
   ```

2. Every SDK call site — `ClaudeAgentOptions(permission_mode='bypassPermissions')`

3. Every `claude -p` subprocess invocation — include `--dangerously-skip-permissions` via a shared `CLAUDE_EXTRA_FLAGS` config constant.

Missing **any** layer creates a silent stall. Missing layer 1 means desktop sessions prompt. Missing layer 2 means SDK sessions prompt. Missing layer 3 means subprocess sessions prompt.

## Rate Limiting

`_req_log` in `app/server/auth.py` accumulates IP keys forever. Prune stale IPs (last request >120 s ago) inline inside `check_rate_limit()` every 5 minutes — no background task needed in asyncio.

**DON'T** let this dict grow unbounded in production — a long-running Railway container will leak memory.

## TLS / Proxy

**DON'T** add `TrustedHostMiddleware` restricting to `127.0.0.1` — Railway terminates TLS and proxies requests, so this blocks all cloud traffic. Use `ALLOWED_ORIGINS` for CORS control instead.
