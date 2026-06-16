# Hermes overnight run — build + prove the remaining core journeys

Overnight unattended is the highest-risk mode (runaway cost, looping). This prompt is built around
hard caps, per-task PRs, NO auto-merge, NO deploy, and explicit anti-loop/stasis rules (learned from
the goal-loop incident). Set the cost cap to a number you're comfortable with (default $40) and enable
Hermes's native cost cap too if available. Expect real progress + an honest morning report — not every
net-new feature finished.

---

```
OVERNIGHT MISSION (Unite-Hub): Work the remaining core-journey punch-list overnight, ONE task at a time,
building + proving each, opening a PR PER TASK for morning review. Autonomous; don't wait for input; if a
task blocks, log it and move to the next. NEVER auto-merge. NEVER deploy.

HARD STOP CONDITIONS (obey strictly — overnight safety):
- Cost cap: stop the WHOLE run at $40 total spend (or the platform cap, whichever is lower) and write the report.
- Max 25 iterations per task; if exceeded, mark the task partial/UNKNOWN and move on.
- STASIS: if you repeat the same action or emit the same status 3x without new progress, ABORT that task and
  move on. Never re-loop. Never re-evaluate a cancelled/deleted goal — if its record is gone, it is done.
- Time-box to the overnight window: finish the current task, write the report, stop.

GLOBAL RULES:
- KEY SOURCING: SUPABASE_SERVICE_ROLE_KEY from `supabase projects api-keys --project-ref
  lksfwktwtmyznckodsau --output json` (in-memory only; NOT vercel env run). Never print/commit secrets.
- SAFETY ENVELOPE: scoped reversible prod TEST data only (tagged throwaway users/workspaces/contacts/
  campaigns/uploads), full verified cleanup. No destructive schema ops, no real emails, no billing, no deploys.
- HONESTY CONTRACT: PASS only with re-run evidence (HTTP status+body / test output). No "done/tick" without
  proof. Unverifiable or human-gated -> UNKNOWN. Update COVERAGE.md honestly after each task.
- REGRESSION: before finishing each task, re-run existing PASS guards (contact-crud, integrations, lead-scoring);
  never regress a PASS.

TASK QUEUE (priority order — each: own branch feat/<task>; build minimal-correct -> PROVE end-to-end as a real
authed user with tagged data -> leave e2e guard -> update COVERAGE.md -> open PR -> next):
1. CONFIRM LEAD SCORING (PR #101): re-run its guard; assert persisted ai_score == the rule's expected value.
   If it does not actually pass, fix it. Do not trust the merge.
2. FIX UPLOAD 500: diagnose + fix the authenticated upload 500 (ANTHROPIC_API_KEY path); prove a tiny tagged
   file uploads successfully and persists.
3. TRANSCRIPTION ENDPOINT: implement the smallest viable transcription endpoint; prove wiring (mock provider in
   tests if live cost/credentials block); mark the live-provider step UNKNOWN if blocked.
4. DRIP CAMPAIGN LIFECYCLE: build create -> add step -> enroll -> process; prove with a tagged test campaign +
   contact; processing must NOT email any real address (test domain / dry-run). If the full lifecycle can't be
   safely finished, build+prove as far as possible and mark the remainder UNKNOWN.
5. OUTLOOK OAUTH ROUTE: add authorize/callback + missing-env guards mirroring Gmail; consent is human-gated ->
   write exact steps to DECISIONS_NEEDED.md.
6. GMAIL: verify everything except consent; write the exact human OAuth-consent steps to DECISIONS_NEEDED.md.

MORNING REPORT (merge NOTHING):
- COVERAGE.md updated: every journey PASS/FAIL/UNKNOWN + overall %.
- STATUS.md: what now PASSES, what's partial/blocked, exact human steps needed, and the list of PR numbers opened
  and staged for my review.
- EVIDENCE.md, DECISIONS_NEEDED.md.

PRINCIPLE: build the minimum correct thing, prove it for a real authed user with tagged throwaway data, clean up,
or mark UNKNOWN. Open PRs; never merge or deploy. Work the queue under the hard caps; the run ends at the
cost/time cap or when the queue is exhausted.
```

---

## In the morning, judge by this (don't trust the summary)
- Open COVERAGE.md: PASS count should be climbing toward 5/6. Each PASS must cite real evidence.
- Each task = its own PR, NOT merged. Review/merge them yourself after spot-checking.
- Re-run one newly-PASS e2e guard yourself.
- DECISIONS_NEEDED.md holds the human-only items (Gmail/Outlook consent) with exact steps.
- If the report shows all-green with no FAIL/UNKNOWN and no PRs to review, be suspicious — that's the
  false-positive pattern, not success.
