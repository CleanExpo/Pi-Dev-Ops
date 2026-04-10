---
name: pi-seo-remediation
description: Remediation advisor for Pi-SEO findings that cannot be auto-fixed. Produces per-finding remediation cards with tier classification, step-by-step fix instructions, before/after code examples, verification commands, and effort estimates.
---

# Pi-SEO Remediation Skill

Produce remediation cards for findings that `autopr.py` cannot fix automatically. Focus on Tier 2-4 fixes that require human judgment or architectural changes.

## Remediation Tiers

| Tier | Who fixes | Type | Examples |
|------|-----------|------|---------|
| **Tier 1** | autopr.py (automated) | Dependency updates, lint fixes | `npm audit fix`, `pip-audit --fix`, `ruff --fix` |
| **Tier 2** | Developer (config change) | Configuration, policy, env rotation | CSP policy, CORS allowlist, rotate leaked secret, disable debug mode |
| **Tier 3** | Developer (code change) | Code refactor or addition | Replace `eval()`, parameterise SQL query, add input validation, sanitise HTML output |
| **Tier 4** | Team (architectural) | System-level change | Add auth middleware to entire API surface, implement rate limiting, centralise audit logging, add secrets manager |

Only produce cards for Tier 2-4. Tier 1 findings should reference autopr.py.

## Remediation Card Catalogue

Cards for each of the scanner's 10 secret patterns and 10 dangerous patterns:

### Secret Patterns

**Anthropic API key / OpenAI API key / GitHub PAT / Linear API key / AWS access key**
- **Tier**: 2
- **Risk**: Exposed credential allows full account compromise. Keys committed to git persist in history even after deletion.
- **Steps**:
  1. Immediately rotate the credential in the provider's dashboard
  2. Remove from source file, replace with env var reference (`os.environ["KEY_NAME"]` or `process.env.KEY_NAME`)
  3. Add `.env` to `.gitignore` if not already present
  4. Run `git log -S "leaked_value" --all` to find all commits containing the secret
  5. Use `git filter-repo --path-glob '*.env' --invert-paths` or BFG Repo Cleaner to purge history
  6. Force-push all affected branches (requires team coordination)
  7. Notify security team of potential exposure window
- **Verification**: `grep -r "old_key_prefix" . --include="*.py" --include="*.ts"` returns no matches
- **Effort**: M

**Hardcoded password / Hardcoded secret**
- **Tier**: 2–3
- **Steps**:
  1. Generate a strong random secret: `python -c "import secrets; print(secrets.token_urlsafe(32))"`
  2. Store in environment variable or secrets manager (Vercel env vars, Railway secrets, AWS Secrets Manager)
  3. Replace hardcoded value with `os.environ.get("SECRET_NAME")` / `process.env.SECRET_NAME`
  4. Add validation at startup: raise if env var is absent in production
- **Effort**: S

**Private key in source**
- **Tier**: 2
- **Steps**:
  1. Revoke the key pair immediately
  2. Generate a new key pair, store private key in secrets manager only
  3. Remove from repo, purge git history (same BFG process as API keys)
- **Effort**: M

**DB connection string**
- **Tier**: 2
- **Steps**:
  1. Rotate database password
  2. Move connection string to `DATABASE_URL` env var
  3. Verify ORM/driver reads from env: `os.environ["DATABASE_URL"]`
- **Effort**: S

### Dangerous Patterns

**shell=True subprocess**
- **Tier**: 3
- **Risk**: Command injection if any user-controlled data reaches the command string.
- **Before**: `subprocess.run(f"ls {user_dir}", shell=True)`
- **After**: `subprocess.run(["ls", user_dir])` — use list form, never string interpolation
- **Verification**: `grep -r "shell=True" app/ --include="*.py"` returns no matches
- **Effort**: S

**eval() usage**
- **Tier**: 3
- **Risk**: Arbitrary code execution if input is user-controlled.
- **Before**: `result = eval(user_expression)`
- **After**: Use `ast.literal_eval()` for safe data parsing, or `json.loads()` for JSON. If dynamic evaluation is genuinely needed, use a sandboxed interpreter.
- **Effort**: S–M depending on usage breadth

**dangerouslySetInnerHTML**
- **Tier**: 3
- **Risk**: XSS if content is not sanitised before rendering.
- **Before**: `<div dangerouslySetInnerHTML={{ __html: userContent }} />`
- **After**: Sanitise with DOMPurify before passing to React: `{ __html: DOMPurify.sanitize(userContent) }`
- **Steps**:
  1. `npm install dompurify @types/dompurify`
  2. Import: `import DOMPurify from "dompurify"`
  3. Wrap all user-controlled HTML through `DOMPurify.sanitize()`
- **Effort**: S

**innerHTML XSS risk**
- **Tier**: 3
- **Before**: `element.innerHTML = req.body.content`
- **After**: `element.textContent = req.body.content` for plain text, or DOMPurify for HTML
- **Effort**: S

**debug=True**
- **Tier**: 2
- **Steps**:
  1. Replace literal `debug=True` with `debug=os.environ.get("DEBUG", "false").lower() == "true"`
  2. Ensure `DEBUG` is not set to `true` in production env vars
- **Effort**: S

**Binding to 0.0.0.0**
- **Tier**: 2
- **Steps**:
  1. For production: bind to `127.0.0.1` unless the service is intentionally public-facing behind a reverse proxy
  2. For Docker: use env var — `host = os.environ.get("HOST", "127.0.0.1")`
  3. Confirm a reverse proxy (Nginx, Caddy, Vercel) handles public exposure
- **Effort**: S

**TODO near sensitive keyword**
- **Tier**: 3
- **Steps**:
  1. Review each TODO comment to determine if the security concern is still unaddressed
  2. Convert to a Linear ticket with proper severity classification
  3. Remove the TODO comment once the ticket is filed
- **Effort**: S

**security check suppressed (# nosec)**
- **Tier**: 2–3
- **Steps**:
  1. Read the surrounding code to understand why the suppression was added
  2. If suppression is justified, add a comment explaining why: `# nosec B101 — assertion only in test context`
  3. If not justified, remove `# nosec` and fix the underlying issue
- **Effort**: S

## Output Format

```json
{
  "project_id": "string",
  "generated_at": "ISO-8601",
  "remediation_plan": [
    {
      "fingerprint": "16-char hex",
      "title": "string",
      "severity": "critical|high|medium|low",
      "tier": 2,
      "tier_label": "Config change|Code change|Architectural",
      "risk_description": "string",
      "steps": ["step 1", "step 2"],
      "code_before": "string or null",
      "code_after": "string or null",
      "verification": "shell command to confirm fix",
      "effort": "S|M|L",
      "auto_fixable": false,
      "file_path": "string",
      "line_number": 0
    }
  ]
}
```
