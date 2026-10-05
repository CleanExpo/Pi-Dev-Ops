<!-- scan-exempt: pattern-definitions -->
# Scan checklist — check IDs ↔ OWASP mapping

Implemented by `scripts/scan.py`; taxonomies: OWASP Top 10 for LLM Apps 2025 and OWASP
Top 10 for Agentic Applications for 2026 (recon-verified titles).

| Check | OWASP | What fails it | Why |
|---|---|---|---|
| SEC-SECRET | LLM02, ASI03 | Any credential-shaped string in any artifact (incl. estate gap-list: `sk-ant-oat*`, `AIza*`) | Secrets never enter a skill, reference, log, or commit. Hits are flagged file:line, match never printed |
| SEC-DESTRUCT | ASI02 | `rm -rf`, force-push, SQL DROP/unbounded DELETE, resource removal — without human-gate language within ±200 chars | Generated skills ship no destructive default action |
| SEC-EXEC | ASI05 | `curl\|bash`, `eval()`, `exec()`, shelling out on fetched content | Never execute attacker-controllable input |
| SEC-INJECT | ASI01, LLM01 | Agent-directed imperatives ("ignore all previous instructions", "AI AGENT:") inside references/assets/fixtures | Retrieved/bundled content is data, not instruction |
| SEC-SCOPE | ASI03 | Body implies Bash/Write/Edit the frontmatter doesn't declare | Least privilege, declared honestly |
| QA-FRONTMATTER | ASI04 | name≠dir, missing description | Catalogue integrity (2-place rule) |
| QA-TESTS | ASI09 | `def test` with no real assert statement; "for now"/"only"/TODO scope-narrowing in tests | Anti-skeleton: a test that can't fail is a prop |

Static limits (honest): scan.py is lexical. It cannot prove runtime behaviour — that is
what phase 7 (eval, fresh) and human promotion are for. A PASS here is necessary, never
sufficient.
