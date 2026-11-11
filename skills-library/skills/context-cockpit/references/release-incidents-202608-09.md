# Historical release incidents, August–September 2026

Preserved source record. Model, billing, credential, lane and availability statements below describe dated incidents; they are not current procedures or entitlement evidence. Follow CLAUDE.md, pr-release-gate/SKILL.md and operating-procedures.md for current action.

**ONE VENDOR BEING DOWN IS NOT "REVIEW EVIDENCE UNAVAILABLE" (founder directive, 19/08/2026,
after this recurred repeatedly).** The reviewer is any agent that is not the implementing
agent — the gate script only checks `reviewer_agent != implementation_agent`, so it has always
accepted any non-builder lane. Before reporting any review as blocked you MUST run the chain
and let it exhaust every lane:

```bash
python3 ~/.claude/skills/pr-release-gate/scripts/independent_review.py \
  --brief <brief> --base <sha> --head <sha> --repo <worktree> --out <report.json>
```

**The lane order is the code, not this paragraph:** `python3
~/.claude/skills/pr-release-gate/scripts/lane_registry.py --list` prints it. As at 24/09/2026 it
is `cursor` → `codex` → `gemini` → `openrouter`. **Founder ruling, 24/09/2026: "use cursor until
codex comes back on-line as the multi-LLM auditor."** Cursor and Codex are the two shell lanes,
the only ones that can execute a mutant. Codex counts as back online only when the token in
`~/.codex/auth.json` has an unexpired `exp` AND a one-line `codex exec` probe answers: on
24/09/2026 the token was valid to 01/10 while the usage limit refused every run until 26/09. `gemini` (`GEMINI_API_KEY` in
**`~/CARSI/.env.local`**; the `Unite-Group/.env.local` copy is DEAD; free tier) and
`openrouter` (`OPENROUTER_API_KEY` in `~/.hermes/.env`, **METERED and uncapped**) can only
reason, never execute. Only when the runner exits 2, having named a reason per lane, is review
evidence genuinely unavailable.

**`ollama` was REMOVED as a lane on 29/08/2026 (founder directive):** it could not execute
mutants, and it was not even free.

**COST LAW: free and paid-subscription lanes before metered ones (founder directive,
29/08/2026).** OpenRouter's key is UNCAPPED ($1,495 lifetime as at 29/08/2026), so it is always
last. One fallback is the chain working; a second is a decision not to look. On the FIRST
`[lane] <x> unavailable`, STOP and diagnose that lane, then pass `--lane <next>` explicitly for
subsequent rounds. Never re-run the default chain into the metered lane
round after round — a session did exactly that eight times on 29/08/2026.

**Codex and every ChatGPT product run on the PAID SUBSCRIPTION and never use API
credits.** `ERROR: Your workspace is out of credits. Add credits to continue.` is
therefore NOT a billing fact: it means the OAuth token in `~/.codex/auth.json` has
expired and the CLI cannot assert the subscription entitlement. Decode `exp` from that
file before concluding anything — `codex login status` prints "Logged in using ChatGPT"
even when the token is dead, so it is not a liveness check. The fix is `codex login`
(interactive, founder-only). Never buy credits, never switch to an API key, never accept
a metered fallback in response to that message.

**An exit code is not a verdict.** `codex exec` EXITS 0 when it hits its usage limit and writes
no report; a session that trusts the status records a review that never happened. Judge every
lane on the report file. Credentials: search `~/.hermes/.env` FIRST (~26 secrets, the estate's
densest store) before concluding any key is absent.

**A PR opens only after GitHub itself has run the exact head green (founder, 25/09/2026).**
A local PASS proves nothing about whether GitHub can run the checks: from 13/09 GitHub started
no job on skills-library (billing), every PR showed a red X, and seven were merged untested.
Push first, let the `push` run finish green on GitHub, then `gh pr create`; the gate refuses
it otherwise. skills-library's checks run on the Mac Mini runner (label `mini`).

**Mesh runner work branches are exempt from the pre-push receipt (founder ruling, 28/09/2026,
RA-7789).** A mesh runner pushes its own `refs/heads/mesh/*` branch unattended to ship a
run. That push cannot merge anything. The installed pre-push hook waves it through only as a
new branch or a fast-forward, and only when the push touches no other branch; it prints
`mesh runner branch, gate skipped`. Opening, readying or merging a PR from a mesh branch is
NOT exempt, and neither is an agent hand-pushing any other branch.


