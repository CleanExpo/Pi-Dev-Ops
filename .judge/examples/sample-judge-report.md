# Judge Report (Worked Example)

> Example output for the proposal:
> *"Build a connector that researches OpenAI and Anthropic skills, hooks, agents, MCP,
> and testing workflows before implementation."*
> This is illustrative — scores and findings are for demonstration only.

## 1. Proposal being judged

A new connector that, before any feature is implemented, fans out to research how OpenAI
(Codex) and Anthropic (Claude Code) handle skills, hooks, agents, MCP servers, and testing,
then returns a recommendation. In effect, an automated "do the research first" pre-build step.

## 2. Decision

REDUCE SCOPE

## 3. Score

| Category | Score | Notes |
|---|---:|---|
| First-source evidence | 14/25 | Vendor docs exist for both CLIs, but the proposal does not pin versions; CLI skill/hook formats change. |
| Clear user/business problem | 14/20 | "Research before building" is real, but overlaps the existing `judge` gate. |
| Reuse of existing capability | 6/15 | `judge` already mandates existing-capability + evidence review; a separate connector duplicates it. |
| Security/privacy safety | 10/15 | A network connector that auto-fetches and feeds results into build decisions widens the prompt-injection surface. |
| UX clarity | 7/10 | Unclear how a human reviews/overrides the connector's recommendation. |
| Testability | 6/10 | No eval set defined for "good research"; output quality is hard to assert. |
| Cost/control simplicity | 2/5 | Adds a standing network dependency and a new failure mode. |
| **Total** | **59/100** | Below threshold as a standalone build. |

## 4. First-source evidence table

| Claim | Evidence checked | Source type | Status |
|---|---|---|---|
| Claude Code exposes repo skills as `/skill-name` | Anthropic Claude Code skills docs | Official vendor docs | SUPPORTED |
| Codex reads repo skills from `.agents/skills` | OpenAI Codex skills docs | Official vendor docs | PARTIAL |
| Codex custom slash prompts are deprecated | OpenAI changelog | Official changelog | NOT CHECKED |
| A connector improves decisions vs. the `judge` gate | — | — | UNSUPPORTED |

## 5. What already exists

- **This repo:** `judge` gate (`.claude/skills/judge`, `.agents/skills/judge`) already enforces
  evidence-first review and existing-capability checks. `tao-judge` provides loop-termination scoring.
- **Claude Code / Codex:** both already support repo-scoped skills and read-only tool use for research.
- **MCP:** doc-fetch MCP servers already exist; a bespoke connector re-implements that.

## 6. Devil's advocate objections

- The `judge` gate already requires first-source research before approval — a connector adds a
  second, overlapping mechanism.
- Auto-fetched web content driving build decisions is a prompt-injection vector.
- "Research quality" has no acceptance test, so the connector can silently degrade.

## 7. Architecture and bloat risks

Duplicates `judge`'s evidence step; introduces a standing network dependency; couples build
approval to an external fetch path that can fail or be poisoned.

## 8. Security, privacy, and permission risks

- Prompt injection via fetched pages feeding into approval logic.
- MCP trust boundary widened if the connector gains write/tool access.
- Audit gap: recommendations must be logged with their sources, or approvals become unprovable.

## 9. UI/UX missing elements

No defined human override, no progress visibility during fetch, no confirmation step before a
recommendation influences a build decision, no error path when fetch fails.

## 10. Loop testing and stress testing

- **Eval cases:** known questions with known correct first-source answers.
- **Red-team cases:** a page that injects "approve this build" instructions.
- **Stress cases:** vendor docs unreachable / rate-limited.
- **Regression checks:** connector output must not change a `judge` REJECT into an APPROVE without new evidence.
- **Acceptance threshold:** ≥ 90% correct source attribution on the eval set; 0 injection-driven approvals.
- **Blocking failure:** any injection-driven approval blocks the build.

## 11. Smallest safe version

A read-only doc-fetch helper invoked *inside* the existing `judge` run — no new approval authority,
results clearly attributed, human keeps the decision.

## 12. Final recommendation

Build smaller: fold research into the existing `judge` gate as a read-only, attributed helper rather
than a standalone connector with approval influence. Run an experiment on the eval set before any
wider build.
