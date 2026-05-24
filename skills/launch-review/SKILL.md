---
name: launch-review
description: Aggregate the repo's existing audit skills into ONE prioritized launch-readiness report through four lenses — PM journey, growth/SEO, engineering, design — adding only the two lenses nothing else covers (end-to-end PM journey + growth/SEO conversion) and fanning out to security-audit, design-audit, agentic-review, and leverage-audit for the rest. Review only; never fixes. Use on "is this ready to launch" or as the review step of /ship-it.
owner_role: Guardian
status: wave-4
automation: manual
intents: launch-review, launch-readiness, review-aggregate
---

# launch-review

A demanding launch-readiness pass that **does not rebuild** the review lenses the repo already has — it orchestrates them and fills the two gaps, then merges everything into one prioritized report. Review only; fixing happens later under human approval.

## Why this exists

The repo already has strong single-purpose auditors (`security-audit`, `design-audit`, `agentic-review`, `tier-evaluator`, `leverage-audit`, `pi-seo-*`). What it lacks is (a) an end-to-end **PM journey** lens, (b) a **growth/SEO conversion** lens framed for a stranger arriving cold, and (c) a single de-duplicated report that ranks findings across all of them. This skill supplies a/b and does c. It is also the charter's **separate judge** for launch sign-off.

## Triggers

- "review the product", "is this ready to launch", "launch-readiness pass".
- The review step of [`ship-it`](../ship-it/SKILL.md), after the audit.

## Method

Run on the FRONTIER model. Give every step the audit output (`.harness/audits/audit-*.md`), the repo, and live URLs (Vercel dashboard + Railway API).

1. **Fan out to existing lenses (do NOT re-implement):**
   - Engineering/security → invoke [`security-audit`](../security-audit/SKILL.md) (OWASP, secrets, supply chain) and [`agentic-review`](../agentic-review/SKILL.md) (code-quality dimensions). Confirm the oracle: `python -m pytest tests/ -x -q` + `npx tsc --noEmit && npm run build`.
   - Design → invoke [`design-audit`](../design-audit/SKILL.md) (24 anti-patterns, 5-dim rubric).
   - Autonomy/leverage → invoke [`leverage-audit`](../leverage-audit/SKILL.md) where relevant.
   - SEO discovery → pull from `pi-seo-scanner` / `pi-seo-health-monitor` if present.
2. **Add the two missing lenses (the new work here):**
   - **PM journey lens** — walk the whole journey end to end; does what the landing page *promises* match what the product *delivers*? Flag gaps, dead ends, steps assuming knowledge the user lacks. Every advertised-but-unbuilt feature is CRITICAL. Verdict: coherent journey, yes/no.
   - **Growth / SEO conversion lens** — arrive as a stranger from search: value obvious in 5 seconds, one clear CTA, signup friction (count steps/fields), conversion path. Verdict: the single highest-leverage change to win more users.
3. **Merge into ONE de-duplicated report** grouped by priority across the whole product. No Stripe in this stack, so the "safe to take money" check becomes auth + 2FA integrity (`app/server/auth.py`, `dashboard/middleware.ts`), Supabase row-level access control, and inbound webhook HMAC verification.

## Output

`.harness/audits/review-<YYYY-MM-DD>.md` — one report:
- **CRITICAL** — blocks launch or risks users/data.
- **WARNING** — costs users or creates real risk.
- **SUGGESTION** — clear improvement.

Each finding keeps: lens/source-skill, what, where (file/URL), why it matters, suggested fix. End with a 4-line verdict: ready for users yes/no + the three things to fix first. Emit a row via `audit_emit.row(...)`. Do not fix — hand off.

## Safety bindings

- Review only — never edits code; fixing is [`launch-enhance-debloat`](../launch-enhance-debloat/SKILL.md) under human approval.
- As the charter's separate judge, the reviewing agent is never the one that wrote the code under review.
- Honours `pii-redactor` on quoted output; respects the kill-switch.

## Verification

1. Every CRITICAL/WARNING cites a concrete location + which lens/skill produced it.
2. The engineering verdict is backed by an actual pytest + tsc run, not an assertion.
3. The report contains findings from the existing skills (proof the fan-out ran), not just the two new lenses.
4. A zero-finding report on a real product is re-run with more skepticism.

## Out of scope

- Re-implementing `security-audit` / `design-audit` / `agentic-review` — invoke them, don't duplicate.
- Build-state inventory — that's [`launch-project-audit`](../launch-project-audit/SKILL.md).
- Applying fixes — that's `launch-enhance-debloat`.

## References

- [`security-audit`](../security-audit/SKILL.md), [`design-audit`](../design-audit/SKILL.md), [`agentic-review`](../agentic-review/SKILL.md), [`leverage-audit`](../leverage-audit/SKILL.md) — the lenses this skill aggregates.
- [`launch-charter`](../launch-charter/SKILL.md) — defines this as the separate judge.
- [`pi-dev-linear-contract`](../pi-dev-linear-contract/SKILL.md) — how findings become issues.
