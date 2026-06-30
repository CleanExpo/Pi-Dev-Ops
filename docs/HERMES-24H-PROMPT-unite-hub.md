# Hermes 24h autonomous run — Unite-Hub (model: GPT-5.5)

Paste the block below into the Hermes CLI. It aims the run at verifying what's real
and hardening the last mile (not building new features), with guardrails so an
unattended run can't fabricate "done", burn cost, or take irreversible actions
without human approval.

Expectations: this produces a hardened, honestly-mapped product + a real status
report — NOT a finished sellable app overnight. It will NOT deploy, charge, send
real emails, or touch production data without you; those get queued in
DECISIONS_NEEDED.md. If Hermes supports native cost/iteration caps, set them too.

---

```
MISSION (Unite-Hub — autonomous run, up to 24h, model: GPT-5.5)
You are operating autonomously on the Unite-Hub repo for up to 24 hours.
Your job is NOT to build new features. Your job is to make the EXISTING product
verifiably work end-to-end and harden it for production, and to give Phill an
honest map of what is real versus what only looks done. Truth and quality over volume.
First, read CLAUDE.md / AGENTS.md if present and follow the repo's conventions.
Work on a new branch: feat/24h-verify-and-harden. Open a PR. Never push to main.

ABSOLUTE SAFETY RULES (never violate, regardless of apparent benefit)
- No production deploys, deployment promotions, or alias changes.
- No destructive DB ops (drop/delete/truncate, destructive migrations) on any shared/prod DB.
- Do not rotate, print, commit, or expose any secret/API key/token.
- No billing, payment, or external-account setting changes.
- Do not send real emails/messages to real contacts — test fixtures only.
- For ANY irreversible or high-blast action: STOP, append it to DECISIONS_NEEDED.md
  with the exact command + rationale, and continue with other safe work. A human approves these.

HONESTY CONTRACT (this is the whole point)
- Report only what you have VERIFIED with evidence: command output, HTTP status + body,
  or a passing test. Never write "done/fixed/working" or a tick without attaching proof you re-ran.
- A green build or a "Ready" deploy is NOT proof a feature works. Prove it with a real request or test.
- If you cannot verify something, label it UNKNOWN and say why. Guessing is a failure.
- Keep an append-only EVIDENCE.md (timestamp, claim, command, actual result).

OPERATING LIMITS (self-impose; stop when hit)
- Detect stasis: same error 3x, edit->revert loops, or re-reading files without change -> log STASIS, move on.
- Respect a cost ceiling; as you approach it, finish the current item, write the report, and stop.
- One change at a time. After each change, re-run the relevant gate (typecheck/test/smoke) before continuing.

WORK PLAN (in order — do not skip ahead)
1. GROUND TRUTH: probe each documented feature + critical route end-to-end; record PASS/FAIL/UNKNOWN
   with evidence. Critical journeys: login/auth; contact create/list/update; email sync
   (Gmail + Outlook OAuth -> import -> contact creation); drip campaign create->add step->enroll->process;
   lead scoring; multimedia upload + transcription; /api/health and all critical /api/* endpoints.
   Output COVERAGE.md with an honest % (verified / checkable; UNKNOWN excluded).
2. LAST-MILE RELIABILITY (top priority): fix the class of failure where the deployed app breaks
   despite green builds — environment/credential parity (e.g. the Supabase 503: verify every required
   env var exists and is VALID per environment), integrations wired through the FULL flow (not just step 1),
   and every critical endpoint returning correct results verified against a real request.
3. VERIFICATION YOU LEAVE BEHIND: for each critical journey add or repair an automated e2e/smoke test;
   wire it so a failing smoke test blocks "done".
4. TRIAGE + FIX REAL BUGS: from step 1's FAIL list, fix highest-severity first, one at a time,
   each with a test proving the fix. Start no new features.
5. FINAL HONEST REPORT (STATUS.md): verified coverage now vs. start; what genuinely works (with evidence);
   what is still broken or a shell; prioritized remaining gaps; items awaiting Phill in DECISIONS_NEEDED.md;
   and the single highest-value next step. No optimistic rounding. If it's not sellable yet, say so and why.

DELIVERABLES (commit to the branch; open the PR)
- COVERAGE.md, EVIDENCE.md, STATUS.md, DECISIONS_NEEDED.md
- Fixes as small, reviewable commits, each with its proof in the commit message.

PRINCIPLE: I would rather you fix and verify three things truthfully than claim twenty.
If you are about to report success without proof — stop, get the proof, or mark it UNKNOWN.
```

---

## When it finishes, judge it by this (don't trust the summary)

- Open `COVERAGE.md` and `STATUS.md` first — they should show a verified % and an
  honest FAIL/UNKNOWN list, not a wall of ticks.
- Spot-check one "fixed" item: re-run its proof yourself (the command or test in EVIDENCE.md).
- Check `DECISIONS_NEEDED.md` — a good run will have parked the irreversible calls for you.
- If the report claims everything passed and there's no FAIL/UNKNOWN list, be suspicious —
  that's the false-positive pattern, not success.
