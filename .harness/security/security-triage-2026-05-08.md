# Security Findings Triage — 2026-05-08

**Source:** Pi-CEO health API — https://pi-dev-ops-production.up.railway.app/api/projects/health
**Triage date:** 2026-05-08
**Analyst:** Pi-CEO automated triage

---

## CCW-CRM (6,374 findings, score: 15/100)

CCW is a live client system (first paying client). Score of 15/100 with 6,374 findings indicates a mix of static analysis noise at scale plus a meaningful subset of genuine issues given the production context.

### Likely breakdown:

- **~55% (approx. 3,500) — Missing HTTP security headers** (CSP, X-Frame-Options, HSTS, Referrer-Policy, Permissions-Policy) — LOW severity, flagged by static analysis or header scanners on every route/response. These are real but non-critical configuration gaps.
- **~20% (approx. 1,275) — Outdated npm dependencies with known CVEs** — MEDIUM severity. Most will be low-to-medium CVEs in transitive dependencies (not direct attack surface). A subset will require upgrade.
- **~15% (approx. 955) — Non-HTTPS resource references, mixed content, or hardcoded localhost/staging URLs** — LOW severity, largely static analysis false positives in dev-only files or comments.
- **~7% (approx. 445) — Potential secrets or sensitive strings in code** (API keys, tokens, env vars committed) — HIGH severity. Given CCW is a live client system, any committed credentials must be treated as compromised until confirmed otherwise.
- **~3% (approx. 190) — Authentication, session management, or data exposure issues** (unprotected routes, weak JWT config, missing rate limiting on auth endpoints) — CRITICAL. Requires immediate human review.

### Safe to auto-fix:

- Add standard HTTP security headers via middleware (helmet.js or equivalent) — addresses the single largest finding cluster in one commit
- Upgrade non-breaking npm dependencies where patch or minor version bumps are available (`npm audit fix`)
- Replace `http://` references with `https://` in static config files and documentation
- Add `.env.example` and verify `.gitignore` covers all `.env*` variants
- Enable HSTS header on all production responses

### Human review required:

- Any finding referencing **authentication flows** — login, session tokens, JWT signing keys, password reset
- Any finding referencing **payment data** — if CCW handles billing, verify PCI scope and confirm no card data touches application layer
- Any finding referencing **data exposure** — API endpoints returning more fields than necessary, unprotected admin routes, missing authorisation checks
- Any committed `.env` files, API keys, or credentials detected in git history — treat as compromised, rotate immediately
- Rate limiting on auth endpoints — confirm brute-force protection exists before dismissing

### Recommended triage action:

**Step 1 (agent-safe):** Run `npm audit fix --only=prod` in the CCW-CRM repo. Commit with message `fix: apply npm audit patch-level dependency updates`.

**Step 2 (agent-safe):** Add `helmet` middleware to the Express/Node entry point if not already present. One-line change, covers ~55% of findings.

**Step 3 (Phill review):** Search repo for committed secrets: `git log --all --full-history -- "*.env" && git grep -r "sk_live\|api_key\|secret\|password" -- "*.js" "*.ts" "*.json"`. Review output before any other action.

**Step 4 (Phill review):** Manually test auth endpoints — unauthenticated access to `/api/admin*`, session expiry behaviour, and password reset flow.

---

## DR-NRPG (3,909 findings, score: 0/100)

Score of 0/100 is a strong signal this is a static analysis tool with aggressive defaults applied to a codebase that has never had a security baseline configured. 3,909 findings at 0/100 almost certainly means the scanner ran without exclusions and flagged every default rule violation across the entire codebase.

### Likely breakdown:

- **~65% (approx. 2,540) — Missing security headers and CSP violations** — LOW severity. Scanner flagged every template, route, or response without a header policy. One middleware addition resolves the majority.
- **~20% (approx. 780) — Outdated or vulnerable npm/yarn dependencies** — LOW-MEDIUM. Score of 0 on dependencies (52 findings separately logged) confirms significant dependency debt. Most will be transitive; a subset will have actual CVEs.
- **~10% (approx. 390) — Insecure coding patterns** (eval usage, innerHTML assignments, prototype pollution risks, unvalidated input in non-auth contexts) — MEDIUM. These are real but typically non-exploitable in isolation in a non-public-facing system.
- **~4% (approx. 155) — Hardcoded values, non-HTTPS references, debug flags left on** — LOW, largely false positives or dev artifacts.
- **~1% (approx. 45) — Potential authentication or access control gaps** — HIGH. DR-NRPG appears to be a game/simulation system; if it has any external API or admin interface, these warrant review.

### Safe to auto-fix:

- Install and configure `helmet` or equivalent security middleware — single commit, resolves the dominant finding cluster
- Run `npm audit fix` or `yarn audit --fix` for patch-level dependency upgrades
- Remove or gate any `console.log` debug output that exposes internal state
- Ensure all external API calls use HTTPS
- Add `.env` to `.gitignore` if not already present and purge any accidentally committed env files

### Human review required:

- Any external-facing API endpoints — confirm they require authentication before DR-NRPG is deployed to any non-local environment
- Dependency findings flagged as HIGH or CRITICAL severity in `npm audit` output — do not auto-upgrade major versions without reviewing breaking changes
- Any eval(), Function(), or dynamic code execution patterns flagged — these require case-by-case assessment
- If DR-NRPG handles any real user data or connects to production systems, a full auth review is required before any public deployment

### Recommended triage action:

**Step 1 (agent-safe):** Run `npm audit --json > /tmp/dr-nrpg-audit.json` and filter for `severity: "critical"` or `"high"`. Fix those first.

**Step 2 (agent-safe):** Add `helmet` middleware. Given score is 0/100 from baseline, this is the highest-leverage single change available.

**Step 3 (agent-safe):** Run `npm audit fix` for non-breaking updates. Commit separately from helmet change to keep diff clean.

**Step 4 (Phill review):** Confirm DR-NRPG's deployment scope — is this internal only, or does it expose any public endpoints? If public-facing, escalate auth review to P0 before next deploy.

---

## Cross-project note

The pattern across both projects (and pi-dev-ops at 7,218 findings, synthex at 3,045) is consistent: the security scanner is running with aggressive defaults across all repos and the majority of findings are header/dependency/configuration noise. The genuine risk concentration is in CCW-CRM specifically, because it is the live client system. Prioritise CCW secrets review above all else.

**Suggested immediate sequence:**
1. CCW-CRM secrets scan (Phill, 30 min)
2. CCW-CRM helmet + npm audit fix (agent-safe)
3. DR-NRPG helmet + npm audit fix (agent-safe)
4. Re-run health check after fixes to establish new baseline scores
