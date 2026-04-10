---
name: security
description: Security rules for Pi Dev Ops — path traversal prevention, HMAC webhook verification, secrets hygiene, timing-safe comparisons.
---

# Security Best Practices

Apply whenever touching auth, session handling, file paths derived from user input, or webhook signature verification.

## Rules

- **Sanitise session IDs before any file path use.** `re.sub(r'[^a-zA-Z0-9]', '', sid)` prevents path traversal (e.g. `sid='../../etc/passwd'`). Already implemented in `persistence.py:_safe_sid()` — never bypass it.

- **Webhook HMAC verification must use `hmac.compare_digest()`.** Timing-safe comparison prevents timing attacks. Both GitHub (`x-hub-signature-256: sha256=<hex>`) and Linear (`Linear-Signature: <hex>`) use HMAC-SHA256 but with different header formats — handle both explicitly.

- **Never commit `.claude/settings.local.json`.** It contains local tool allowlists specific to one machine and leaks your tool configuration if shared. Add it to `.gitignore`.

- **Never hardcode credentials.** Use `os.environ.get()` with a `load_dotenv(..., override=True)` at the top of `config.py`. The `claude` CLI clobbers `ANTHROPIC_API_KEY=""` in the shell environment — `override=True` is required to win.
