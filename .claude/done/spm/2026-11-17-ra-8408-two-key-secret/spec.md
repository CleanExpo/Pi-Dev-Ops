# SPM Spec — RA-8408: the server accepts a current and a next fleet key

<!-- header (append-only): created 2026-11-17 by Mini/claude, session mission-control-recovery-20261114 (resume) -->
<!-- amended 2026-11-17T02:41Z (uncommitted, pre-build) — amendment 1 (with the chair's round-2 wording fixes, and amendment 2 at 2026-11-17T02:46Z: acceptance criteria made per route from an enumeration of the real routers, 26 routes; test fixture made safe on unchanged code; measured baseline and a lasting test environment recorded): folds the judge round-2 closures (94/100), the independent correctness pass (14 findings) and the nine-seat engineering bench: positive-proof swap gate replaces the 60-minute quiet rule; step 0 (key provenance) and step 6 (retire the old variable) added; per-step reverse sequences replace "one-way"; refusal logging; both slots normalised the same way; six start-up states; route-enumeration test; guard match defined as exact equality plus a compare-site scan; acceptance criteria rewritten so none can pass without proving its claim. -->

### Contents
1 Task · 2 Context · 3 Problem and value · 4 Outcome · 5 Scope · 6 Existing capability ·
7 Bench receipt · 8 Judge · 9 Solution · 10 UX · 11 Technical · 12 Security · 13 Verification ·
14 Stress · 15 Acceptance criteria · 16 Goal · 17 Sequence and crew · 18 Handoff seed · 19 Recommendation

## 1. Task
| Field | Detail |
|---|---|
| Original request (verbatim) | Linear RA-8408: "Server accepts a current and a next X-Pi-CEO-Secret, so the D52 key rotation can finish with no outage". Founder, 17/11/2026: "These results are not good enough..Your role is to seek out and provide the required proceeses to repair, and fix the issues.." |
| Interpreted task | One owner in `app/server` decides whether an `X-Pi-CEO-Secret` header is accepted. It accepts the current value and one optional next value. Every existing check calls it. A runbook in the repo gives the safe rotation order, with the undo for each step. |
| Lane · tier | full · T3 (F2 I1 N0 X1 S2) |
| Target outcome | A merged, deployed server on which setting one extra variable lets machines holding the new key in, while machines on the old key keep working, so holders can be moved one at a time and the old key retired with no outage. |

## 2. Current context
| Field | Detail |
|---|---|
| Repo · branch · HEAD · tree | CleanExpo/Pi-Dev-Ops · `fix/ra-8408-two-key-secret` · 71bad315 (= origin/main) · clean apart from this spec folder. Worktree `/Volumes/Mini Mini 2T Storage/worktrees/Pi-Dev-Ops/ra-8408-two-key-secret`. |
| Done preflight | `donectl selftest` exit 0, 8 of 8 (17/11/2026). `donectl status`: spec-work contract `w_d0fb4803e5b3` LOCKED. |
| North Star source + revision | n/a (Pi-Dev-Ops internal operations) |
| Files, PRs, tickets inspected | RA-8408; handoff `~/session-handoffs/handoff-20261117-1215-d52-rotation-two-key.md`; `app/server/config.py`, `mesh_fleet_auth.py`, `app_factory.py`, `routes/{mesh,mesh_ship,mesh_lane_events,conversations,cost_report,routing,delegate,margot,webhooks,wiki_sources}.py`; `mesh/heartbeat.py`, `mesh/runner.py`; `.github/frozen-paths.txt`; `.github/file-length.baseline.txt`; `.github/function-length.baseline.txt`; `.github/workflows/{ci,workspace_intel_brief}.yml`; `scripts/workspace_intel_brief_ci.py`; `railway.pi-dev-ops.json`; dashboard `margot/bubble` and `webhook/morning-intel` routes. PR search for "8408" in all states: none. |
| Known current behaviour | See Grounded lines below. |
| Unknowns | U1 whether a non-ASCII header returns 500 today (inferred; the red-first test observes it). U2 what n8n holds and which of its workflows send the header (outside the repo). U3 who posts to `/api/webhook/routine-complete`. U4 whether a Railway variable change redeploys by itself, and whether two changes are batched into one deploy. U5 Railway log retention. U6 which of the repo's two Railway start configs is live. U7 whether Railway Rollback restores variables (reported from Railway's docs by one seat, not read by the lead). U8 closed: `tests/` runs in 584 s and `swarm/` in 2 s on the Mini. U9 whether the new key value appears in any transcript, handoff or shell history. |

Grounded 2026-11-17: `INTERNAL_WEBHOOK_SECRET = os.environ.get("TAO_INTERNAL_WEBHOOK_SECRET", "") or WEBHOOK_SECRET` — `app/server/config.py:250`; the GitHub secret has the same fallback at `:249`.
Grounded 2026-11-17: eight definitions compare the header to that one value — `routes/mesh.py:47`, `routes/conversations.py:64`, `routes/cost_report.py:25`, `routes/delegate.py:63`, `routes/margot.py:73`, `routes/webhooks.py:45`, `routes/wiki_sources.py:90`, `mesh_fleet_auth.py:23-34` (grep `compare_digest` and `INTERNAL_WEBHOOK_SECRET` over app/, swarm/, mesh/, scripts/).
Grounded 2026-11-17: a ninth reader, the start-up warning — `app/server/app_factory.py:212-213`.
Grounded 2026-11-17: other modules call those helpers by name — `routes/routing.py:24,129`, `routes/mesh_ship.py:34`, `routes/mesh_lane_events.py:117,168`.
Grounded 2026-11-17: every helper checks "not configured" before "missing"; three text families exist (mesh/conversations/wiki_sources · cost_report/delegate/margot · webhooks) — read of each helper body.
Grounded 2026-11-17: size limits — `.github/file-length.baseline.txt` lines 23 (webhooks.py 1264, now 1263), 63 (config.py 572, now 572), 103 (mesh.py 436, now 404), 158 (margot.py 341, now 341); `.github/function-length.baseline.txt:42` (`app_factory.py::on_startup` 145).
Grounded 2026-11-17: none of the files to change match `.github/frozen-paths.txt`.
Grounded 2026-11-17: heartbeat and runner read their key once at start — `mesh/heartbeat.py:38`, `mesh/runner.py:55`; heartbeat interval default 20 s — `mesh/heartbeat.py:39`.
Grounded 2026-11-17: a weekly outside scheduler (n8n, Sunday 09:00 UTC) and a manual-only GitHub workflow send the header — `.github/workflows/workspace_intel_brief.yml:6-10`, `scripts/workspace_intel_brief_ci.py:56-59`.
Grounded 2026-11-17: root log level is INFO — `app/server/config.py:96`; one worker — `railway.pi-dev-ops.json:8`.
Grounded 2026-11-17: Mission Control fleet read shows the Windows PC heartbeat 132,277 s stale, both Macs fresh — `mcp__mission-control__fleet_status`.
Lead (handoff, not re-read today): live Railway holds only `TAO_WEBHOOK_SECRET` (old value), `TAO_FLEET_READ_SECRET`, `TAO_SESSION_SECRET`; the new value is 57 characters.

## 3. Problem and value
| Field | Detail |
|---|---|
| User / customer | The founder, who runs three machines and reads Mission Control. |
| Pain and current workaround | The fleet key was printed in a transcript. The rotation on 15/11 broke every heartbeat for 36 hours, because the server accepts exactly one value and the holders (three machines, Vercel, GitHub, n8n, long-running processes) cannot all change at the same instant. Workaround today: two Macs are back on the exposed key. |
| Revenue path | None directly. It removes an exposed credential from an internal operations server and stops Mission Control going dark during a rotation; the fleet is what builds and ships client work. |
| Incremental cost | $0. No new service, model call or storage. A few rate-limited log lines. |
| Why now | The exposed key is still live and still in use. |

## 4. Desired outcome
- Operator outcome: after merge and deploy, the founder approves one variable on Railway; the Windows PC heartbeat turns fresh in Mission Control without anyone touching the PC; each remaining holder is then moved one at a time with nothing going dark; the old key is then retired.
- System outcome: one function owns the decision; a new secret comparison in a new file, or a new route that takes the header without being tested, fails a test.
- Must not happen: a secret value, hash, prefix or length in any log or error; the read-only fleet key accepted on a write route; an empty or absent header accepted; a malformed next value breaking holders of the current value; any change to the GitHub signature check.
- Plain statement for the founder: merging this does NOT end the exposure. The exposure ends only after runbook steps 4 (swap), 5 (GitHub signing secret) and 6 (retire the old variable) are all done. Steps 5 and 6 have their own ticket (§19).

## 5. Scope
In scope
- New `app/server/internal_secret.py` (owner). The eight definitions and the start-up warning call it.
- New env variable `TAO_INTERNAL_WEBHOOK_SECRET_NEXT`.
- Tests; `.env.example`; `DEPLOYMENT.md` variable rows; new runbook `docs/runbooks/fleet-key-rotation.md`.

Out of scope (explicit)
- Any production variable change, and any command that reads a stored key (founder only, after merge).
- The GitHub signature path and its secret; intake, Gmail, calendar, Telegram, Slack and Linear secrets; session auth. `app/server/config.py` is not edited.
- Dashboard code. A general N-key list, automatic expiry of the next slot, rotation tooling, a dashboard panel, a counters endpoint, a stale-heartbeat alert.

Named limits (each recorded in the runbook)
- **L1** `dashboard/app/api/webhook/morning-intel/route.ts` is a second, single-key check on Vercel. Its Vercel variable and its outside caller must move together; follow-up ticket (b).
- **L2** Log lines name the route family, not the holder. `routing` logs as `cost_report`; `mesh_ship` and lane-events POST log as `mesh`; `webhooks` covers four callers. A server line therefore cannot confirm one holder; the swap gate uses a caller-side success per holder.
- **L3** The guard cannot catch a new comparison written inside a file that is already allowed to compare secrets (for example `routes/webhooks.py`), nor one that borrows the value from the owner's private functions. The route-enumeration test (AC-4) covers the direction that matters: a route that takes the header and is not tested fails.

Assumptions: [A1] server accepts current plus next (founder default given). [A3] no production change without the founder's yes; no value shown.
Constraints: Tier 1; fake fixture values only; files and functions at their size limit must not grow; smallest reviewable change.

## 6. Existing capability
Search terms used: `compare_digest`, `INTERNAL_WEBHOOK_SECRET`, `WEBHOOK_SECRET`, `x-pi-ceo-secret`, `X_PI_CEO_SECRET`, `FLEET_READ_SECRET`, `PI_CEO_API_KEY`, `PI_CEO_WEBHOOK_SECRET`, `n8n`, `8408` (PRs, remote branches).
| Capability | Location / source | Reuse? | Notes |
|---|---|---:|---|
| Multi-value acceptance for the fleet GET routes | `app/server/mesh_fleet_auth.py:23-34` | yes | The pattern being generalised; its compare moves into the owner. |
| Separate internal variable | `config.py:250` | yes | Lets the swap leave `TAO_WEBHOOK_SECRET` alone until step 6. |
| Per-route helper names and error texts | the eight definitions | yes | Kept as thin wrappers. |
| Fleet-read test fixture pattern | `tests/test_mesh_fleet_read_secret.py:27-43` | yes | Pattern for the new tests. |
| "Env binds per deployment" lesson | `.github/workflows/kill-switch-proof.yml:86-87` | yes | Quoted in the runbook. |
| Two-key PR | none found | no | PR search all states; `git ls-remote --heads origin '*8408*'` empty. |

Alternative considered and rejected: no code change, flip `TAO_INTERNAL_WEBHOOK_SECRET` to the new value in one window. Every holder not moved in that window breaks silently, which is the 36-hour failure again; the reviews found five holders the ticket had missed, so the list cannot be trusted to be complete.

## 7. Specialist bench receipt
`T3 (F2 I1 N0 X1 S2) · seats product-manager, architect, security-reviewer, qa-verification-lead, devils-advocate-judge, ops-cost-realist · rounds 2 (judge only in round 2) · split 0.0 · overlap (canonical) high on call-time reads, non-ASCII compare, guard scope, swap-proof visibility · board_version 1.0 · leveling_version 1.0`. Requested model tiers are intent; the serving model is not observable from seat output. Reading: unanimous criticism, so every must_fix is folded. Adversarial pass: one independent correctness review of the first written spec, verdict FAIL with 14 spec-text findings, all folded in amendment 1.
| Seat | Verdict | Confidence | must_fix (slugs) |
|---|---|---:|---|
| product-manager | needs-work | 0.80 | cut-gold-plating, success-not-end-of-exposure, missing-runbook |
| architect | needs-work | 0.82 | fleet-503-semantics, call-time-module-attribute-reads, validate-next-per-call, keep-wrappers-pin-texts, ast-guard-scope, non-ascii-header-500, dashboard-verifier-holder |
| security-reviewer | needs-work | 0.80 | non-ascii-compare, next-value-policy, fleet-auth-semantics, ast-guard-scope, owner-reads-config-at-call-time, routing-ninth-path, visibility-must-prove-swap |
| qa-verification-lead | needs-work | 0.80 | ninth-reader-app-factory, keep-check-secret-names, validate-next-at-call-time, length-rule-next-only, whitespace-header-vs-whitespace-next, non-ascii-header-500, red-first-per-family, github-hmac-positive-control |
| devils-advocate-judge R1 | needs-work (79/100) | 0.74 | visibility-wrong-slot, morning-intel-single-key, holder-inventory, next-slot-expiry, read-at-call-time, non-ascii-compare, github-hmac-fallback |
| devils-advocate-judge R2 | needs-work (94/100) | 0.78 | quiet-window-vs-cadence, n8n-holder, guard-exact-constant |
| ops-cost-realist | needs-work | 0.80 | config-py-file-length-gate, swap-step-ordering, no-registry-docs-update, log-only-proof-weak |

Synthesis decisions where seats disagreed
- 32-character rule for the next value: product said drop it; security, architect and judge said keep it. Kept, for the next value only, with a loud start-up WARNING and a runbook check of that line before any holder moves.
- Guard: product said plain text search; architect, security and QA said syntax-tree scan. Syntax-tree scan with exact-equality matching.
- Counters endpoint: architect and judge suggested; QA and product said no. Not built.
- `cut-gold-plating` is retired in part by evidence: each rule it wanted cut is a must_fix of two or more other seats.
- `next-slot-expiry`: automatic expiry rejected (it would lock out moved holders; judge R2 agreed); closed by start-up WARNINGs on every boot while the slot is set and an owned board card for the swap.
- Dummy compare value: one seat asked whether a fixed constant is safe. Decision: a random value generated once per process, so it cannot be presented.

## 8. Judge challenge
| Category | R1 (brief) | R2 (first spec) | R2 notes |
|---|---:|---:|---|
| First-source evidence | 21/25 | 23/25 | n8n holder missing (−2) |
| Clear user / business problem | 17/20 | 20/20 | |
| Reuse of existing capability | 12/15 | 15/15 | |
| Security / privacy safety | 10/15 | 15/15 | |
| UX clarity | 7/10 | 7/10 | quiet window shorter than holder cadence (−3) |
| Testability | 8/10 | 9/10 | guard string-match undefined (−1) |
| Cost / control simplicity | 4/5 | 5/5 | |
| **Total** | **79** | **94** | |

Deductions below 100 and their closure in amendment 1
| Deduction | Owner | Closure | Evidence |
|---|---|---|---|
| n8n holder missing (−2) | lead | holder table names n8n and its workflows, with cadence; unknown holders are blocking rows | §9 holder table, AC-13 |
| quiet window vs cadence (−3) | lead | swap gate is positive proof per holder; silence is not accepted | §9 step 4, AC-13 |
| guard match undefined (−1) | builder | exact equality, never substring; negative control with a pinned error text | AC-3 |

Decision: **APPROVE EXPERIMENT** — a named, bounded, reversible, local build in this worktree: no push, PR, merge or deploy under this decision. Reason it is not APPROVE BUILD: the last returned judge contract reads 94, and the bench's two-round cap is used, so no third score is requested. The three named deductions are closed in this amendment, but the lead's own reading of that is not a judge contract. What moves it to a release: the built code passing the independent Tier 1 review under `pr-release-gate`, plus the founder's yes to push (asked once, when the build is verified).
Hard floors: security fail ≥0.8 — clear (verdict needs-work, items folded) · rollback for irreversible work — clear (per-step reverse sequences, §9) · authority — clear (RA-8408, founder "fix") · evidence — clear.
Hard-day card (a holder is locked out after the swap): impact — that holder's calls are refused; evidence — a `rejected reason=mismatch where=<label>` line and a stale heartbeat or a failed scheduled job; options — move the holder to the new key (preferred), or restore the overlap with ONE combined change: old value in the current slot AND new value in the next slot together, never one alone; dissent — none; owner — lead lane diagnoses, founder approves any variable change; authority boundary — no agent changes a production variable; next check — heartbeat age and the absence of new `rejected` lines.

## 9. Proposed solution
Owner module `app/server/internal_secret.py`. Imports only `hmac`, `hashlib`, `os`, `logging`, `time`, and `from . import config`; never a routes module.

Values
- `_slots() -> (current, next, read_only)`, called on every decision; nothing is cached at import. `current = config.INTERNAL_WEBHOOK_SECRET.strip()` read as a module attribute; `next = effective_next(current, os.environ.get("TAO_INTERNAL_WEBHOOK_SECRET_NEXT", ""), read_only)`; `read_only = os.environ.get("TAO_FLEET_READ_SECRET", "").strip()`. All three are stripped the same way. (Stripping current changes one outcome, on purpose: a stored current value with stray surrounding whitespace matched nothing before and now matches its trimmed form. `config.py` is at its size limit and is not edited; reading the environment at call time matches how the fleet-read key is read today.)
- `effective_next(current, raw_next, read_only) -> str` — pure. The candidate is `raw_next.strip()`; every check runs on the candidate; the candidate is what is honoured. Honoured only when ALL hold: `current` is non-empty; the candidate is non-empty; every character is in 0x21–0x7E; length is at least 32; it differs from `current`; it differs from `read_only`. Otherwise `""`.
- `next_state(current, raw_next, read_only) -> str` — pure: `"unset"`, `"active"`, `"equals_current"`, or `"ignored"`.

Decision
- `classify(presented, where) -> str` — exactly one of `"unconfigured"`, `"missing"`, `"mismatch"`, `"current"`, `"next"`. Order: `unconfigured` when current is empty (a next value alone never opens anything); then `missing` when `presented` is `None` or `""`; otherwise compare. The presented value is never stripped (a header of spaces is a mismatch, as today).
- `classify_fleet_read(presented) -> str` — for the two GET routes only: `"unconfigured"` only when current, honoured next and read-only are all empty (today's rule); else `"missing"`, `"mismatch"`, `"current"`, `"next"` or `"read_only"`.
- `accepted(result) -> bool` — true only for `current`, `next`, `read_only`. Wrappers branch on this, never on a list of refusal states.
- Compare: SHA-256 digest of `value.encode("utf-8", "surrogatepass")` for the presented value and for each slot; `hmac.compare_digest` on the digests. EVERY slot compare runs on every call (no `any()`, no early return). An empty slot is compared against a random 32-byte value generated once per process (`_DUMMY`), and that result is discarded, so an empty slot can never match. No `str` input makes the call raise.

Wrappers
- Each of the seven route helpers keeps its name, signature, status codes and exact error texts: call `classify(secret, "<label>")`; raise its own 503 on `unconfigured`; return when `accepted(...)`; otherwise raise its own "missing" or "invalid" 401. `mesh_fleet_auth.check` keeps its name and texts and calls `classify_fleet_read`; it holds no compare of its own. Now-unused `hmac` imports in the edited files are removed.
- `app_factory.on_startup` lines 212-213 become one call to `log_startup_state(log)`; the function does not grow.

Visibility (labels are fixed strings passed by the wrapper: `mesh`, `conversations`, `cost_report`, `delegate`, `margot`, `webhooks`, `wiki_sources`, `fleet_read`; never a URL, path, header, address, value, hash, prefix or length)
- Refusals, always on: WARNING `internal_secret: rejected reason=<missing|mismatch> where=<label>`, at most once per (reason, label) per 600 s.
- Acceptances, only while a next value is honoured: INFO `internal_secret: accepted slot=<current|next> where=<label>`, at most once per (slot, label) per 600 s. A read-only acceptance is not logged.
- The limiter is a module-level dict read through a patchable clock `_now = time.monotonic`, with `_reset_log_state()` for tests. It is per process; the window restarts on every deploy; a race can only duplicate a line. No lock, no shared store.
- `log_startup_state(log)` prints exactly one primary line:
  1. WARNING, the existing text unchanged, when current is empty.
  2. INFO `internal_secret: next slot not set`.
  3. WARNING `internal_secret: next slot ACTIVE: rotation in progress, finish the swap (docs/runbooks/fleet-key-rotation.md)`.
  4. WARNING `internal_secret: next slot equals current: swap applied, now remove TAO_INTERNAL_WEBHOOK_SECRET_NEXT`.
  5. WARNING `internal_secret: TAO_INTERNAL_WEBHOOK_SECRET_NEXT is set but IGNORED (fails policy)`.
  plus, independently, when true:
  6. WARNING `internal_secret: current key comes from the TAO_WEBHOOK_SECRET fallback` (current non-empty while `os.environ` has no `TAO_INTERNAL_WEBHOOK_SECRET`).
  7. WARNING `internal_secret: read-only fleet key equals a write key` (read-only equals current or the raw next candidate).
  No line carries a value, hash, prefix, length or policy detail.

Flows
- Permission: write routes accept current or honoured next. The two fleet GET routes additionally accept the read-only key. The read-only key is refused everywhere else, and a next value equal to it is not honoured.
- Failure: malformed next → ignored, WARNING at start-up, current holders unaffected. Non-ASCII or malformed-character header → 401.
- Behaviour changes, stated: (1) a non-ASCII header returned 500 (unhandled `TypeError`, U1) and now returns 401; (2) refusals now write a rate-limited WARNING. No other caller-visible change when no next value is set.

Rollout (written into the runbook as numbered steps, each with "what you should see" and "how to stop"; every production step is the founder's, one yes each; every variable change takes effect only after the server redeploys, so each step says: deploy it, note the deployment, read the start-up line from that deployment)

Holder table (runbook, with a tick column; a holder that cannot be confirmed blocks step 4)
| Holder | Where the value lives | How often it calls | How to confirm it is on the new key |
|---|---|---|---|
| Windows PC | machine env (already new, per handoff) | every 20 s | heartbeat fresh in Mission Control |
| Mac Mini, MacBook | `PI_CEO_API_KEY` and `TAO_WEBHOOK_SECRET` in `~/.hermes/.env` and profile env files; MCP server env; `MC_LANE_SECRET` / keychain `mc-lane-secret` | every 20 s (heartbeat); on use (others) | restart the process, then heartbeat fresh; Mission Control status tool returns data |
| Desk voice loop | `PI_CEO_API_KEY` / `TAO_WEBHOOK_SECRET` | only while running | one call succeeds |
| GitHub Actions secret `PI_CEO_WEBHOOK_SECRET` (sends the header; NOT the signing secret) | repo secrets | manual only | run `workspace_intel_brief.yml` by hand; run is green |
| Vercel `TAO_WEBHOOK_SECRET` (margot/bubble) | Vercel env; needs a redeploy | on use | the bubble answers |
| Vercel `TAO_INTERNAL_WEBHOOK_SECRET` / `TAO_FLEET_READ_SECRET` (fleet tile; record which is set) | Vercel env | on page load | fleet tile loads |
| Vercel `WEBHOOK_SECRET` + the morning-intel outside caller (L1, move together) | Vercel env; n8n | daily (11:45 AEST, per code comment) | trigger the workflow by hand; it succeeds |
| n8n: workspace RSS monitor, weekly brief (Sunday 09:00 UTC), any other workflow sending the header (U2) | n8n credential store | daily / weekly | execute each workflow by hand; it succeeds |
| Whoever posts `/api/webhook/routine-complete` (U3) | UNKNOWN | irregular | UNKNOWN: identify before step 4. If still unidentified 7 days after step 2, the founder decides whether to swap anyway; a lockout would then show as `rejected reason=mismatch where=webhooks`, and the combined undo restores it |

Steps
0. Before anything: count-only check that the new key value does not appear in any transcript, handoff or shell history on each machine that took part on 15/11 (a command that prints a match count and never the value; proven first with a planted fake string giving a count of 1). If the count is not zero, mint a fresh key and use that instead. Every later copy of the value goes from its store to the holder through a pipe or keychain read; it is never typed as a command argument, pasted into a chat, or read into an agent's context. The read-only fleet key stays a different value from any write key.
1. Deploy the merged code. See: `next slot not set`, and (expected today) the fallback warning. Record which start config printed it (U6). How to stop: revert the PR; safe.
2. Set `TAO_INTERNAL_WEBHOOK_SECRET_NEXT` on Railway. Do NOT touch `TAO_WEBHOOK_SECRET`. Deploy; note the deployment; see `next slot ACTIVE` in that deployment's log (if it reads IGNORED, stop: the value fails policy). Proof: the Windows PC heartbeat turns fresh, untouched, after that deployment went live; one `accepted slot=current` line is seen (proves the log reaches Railway, U5). How to stop: remove the variable and redeploy, or revert; safe while no holder has moved.
3. Move holders one at a time, in the table's order; restart each process; tick the row only on its confirmation. From the first move onward: ROLL FORWARD ONLY. Never revert the PR and never press Railway Rollback (U7), because old code accepts only the old key and every moved holder goes dark. If the server must go back to old code, first move every moved holder back to the old key, last moved first.
4. Swap gate, all three at once: this deployment's start-up line reads `next slot ACTIVE`; every row of the holder table is ticked by a caller-side success (a route family with no log line at all is UNKNOWN, not quiet); no `accepted slot=current` and no `rejected reason=mismatch` line since the last holder moved. Then, as separate deploys in this order: (a) set `TAO_INTERNAL_WEBHOOK_SECRET` to the new value; deploy; see `next slot equals current: swap applied`; see one `accepted`-free, `rejected`-free heartbeat cycle and fresh heartbeats; (b) only then remove `TAO_INTERNAL_WEBHOOK_SECRET_NEXT`; deploy; see `next slot not set` with no fallback warning. Removing NEXT first locks out every moved holder. How to undo: ONE combined change — old value in the current slot AND new value in the next slot together (if Railway applies them as two deploys, set next first); see `next slot ACTIVE`. Never set the current slot back alone. If the two changes land as two deploys, the first one prints `next slot equals current`; ignore that line until the current slot has been set back.
5. In the same window: rotate the GitHub signing secret — set `TAO_GITHUB_WEBHOOK_SECRET` on Railway and the GitHub webhook setting together. This cannot be half-done: the two sides must change together. How to stop: put the previous signing secret back on both sides together.
6. Retire the old variable: once 4 and 5 are confirmed, delete `TAO_WEBHOOK_SECRET` on Railway or overwrite it with a fresh random value no holder has; do the same for the dashboard's old variables once their callers have moved. Until this step, deleting either newer variable would silently bring the exposed key back. How to stop: set the variable again; nothing reads it once both newer variables are set.
After the swap: for one full daily cycle and through the next Sunday run, check every heartbeat is fresh, the morning brief arrived, and no `rejected reason=mismatch` line appeared.

## 10. UX requirements
No user interface. The operator surfaces are: Mission Control heartbeat age (existing), the seven start-up lines, and the rate-limited `accepted` / `rejected` lines. Copy is fixed in §9. The runbook is plain English, numbered, with "what you should see" and "how to stop" after each step, and the holder table with a tick column.

## 11. Technical requirements
Files
- Add: `app/server/internal_secret.py` (under 300 lines; every function under 40 lines); `tests/test_internal_secret.py` (unit); `tests/test_internal_secret_routes.py` (HTTP only; must not import the owner module at file level); `tests/test_internal_secret_guard.py`; `docs/runbooks/fleet-key-rotation.md`.
- Edit: `app/server/routes/{mesh,conversations,cost_report,delegate,margot,webhooks,wiki_sources}.py` (helper bodies and imports only), `app/server/mesh_fleet_auth.py`, `app/server/app_factory.py` (lines 212-213), `.env.example`, `DEPLOYMENT.md` (variable rows: add `TAO_INTERNAL_WEBHOOK_SECRET`, `TAO_INTERNAL_WEBHOOK_SECRET_NEXT`, `TAO_FLEET_READ_SECRET`; correct the `TAO_WEBHOOK_SECRET` row).
- Not edited: `app/server/config.py`; `app/server/webhook.py`; any dashboard file; any existing baselined test file; `tests/conftest.py`.

Size gates: no baselined file or function grows (`.github/scripts/file_length_lint.py`, `function_length_lint.py` exit 0). `margot.py` stays at 341 by removing its now-unused `hmac` import. Schema / migration: none. Env: one new optional variable; unset is today's behaviour. Backward compatibility: helper names, signatures, codes and texts unchanged. Performance: up to four SHA-256 digests and three constant-time compares per authenticated request; negligible; limiter map bounded at 8 labels × 4 keys. Hooks / skills / agents: none.

## 12. Security and privacy
- Auth: decision owned by one module; fail-closed on empty, absent, malformed, unconfigured.
- Permission boundary: read-only key limited to the two GET routes; a next value equal to it is not honoured; a start-up WARNING when it equals a write key.
- Secrets: never in source, tests (fake values such as `fake-current-key` and `fake-next-key-` padded to 32 or more characters; chosen not to resemble real token formats), logs, error texts or the PR. The path a real value takes to a holder is a pipe or keychain read (runbook step 0).
- Timing: digest compare gives equal-length inputs; every slot compare always runs.
- Untrusted input: header bytes of any content; no exception path.
- External services: none. PII: none. Prompt-injection surface: none.
- Approval gates: every production variable change, and any command that reads a stored key, is the founder's. Audit: start-up, accepted and rejected log lines.
- Residual exposure stated: between rollout steps 2 and 4 the exposed value stays valid (same as today, not worse); after step 4 it still signs GitHub events until step 5; it remains a dormant fallback until step 6.
- Noted, not changed (follow-up tickets): the dashboard holds a write key (margot/bubble) and falls back to one for the fleet tile; `routing.py` takes a tenant id from the query string for any key holder.

## 13. Verification plan
Environment: the worktree on the Mini; a Python 3.12 virtual environment built from `app/requirements.lock`, plus CI's pinned `ruff==0.15.10`, at `/Volumes/Mini Mini 2T Storage/cache/venvs/pi-dev-ops-ra-8408-py312` (outside the worktree and outside any session folder, so the locked recipes survive a handoff; removed at close-out). Isolation: FastAPI `TestClient` with routers mounted on a bare app, `monkeypatch`, and an autouse fixture in each new test file that removes `TAO_INTERNAL_WEBHOOK_SECRET_NEXT` and `TAO_FLEET_READ_SECRET` from the environment and resets the log limiter; no network. In the route test file that fixture resets the limiter only when the owner module can be found, and does nothing otherwise, so the file sets up cleanly on unchanged code. Prod-impossibility guard: no test reads a real environment secret; no Railway, Vercel, GitHub-secret or keychain command is part of this build. Teardown: none needed.

All PLANNED until run:
- static: `ruff check` on the new and edited files · `python3 .github/scripts/file_length_lint.py` · `python3 .github/scripts/function_length_lint.py` · `python3 scripts/check_frozen_paths.py` and the fail-open and secrets scans, each invoked as `ci.yml` invokes it.
- unit: `pytest -p no:cacheprovider -q tests/test_internal_secret.py tests/test_internal_secret_guard.py`
- integration: `pytest -p no:cacheprovider -q tests/test_internal_secret_routes.py` plus the existing auth-touching files (`test_cost_report_route.py`, `test_routing_route.py`, `test_conversations_api.py`, `test_mesh_fleet_read_secret.py`, `test_mesh_fleet_endpoint.py`, `test_mesh_lane_events.py`, `test_mesh_ship_endpoint.py`, `test_mesh_claim_lane.py`, `test_routes_webhooks.py`, `test_wiki_sources_api.py`, `test_margot_truth_check_voice.py`, `test_remaining_transport_boundaries.py`, `test_ra7216_attribution_keys.py`). These existing files are a regression check only; `test_remaining_transport_boundaries.py` replaces the delegate check with a stand-in and proves nothing about delegate auth.
- full: `pytest tests/ -q` and `pytest swarm/ -q` (what CI runs), each under a hard time limit of about twice its measured baseline; hitting the limit is a failure to diagnose. Measured on unchanged code 17/11/2026: `tests/` exit 0, 13,243 passed, 26 skipped, 3 xfailed, 584 s, so its limit is 1200 s. `swarm/` exit 0, 344 passed, 2 skipped, 2 s, so its limit is 120 s. `ruff check app/` exit 0 on unchanged code.
- red-first: the route test file is written first and run on unchanged code; saved output shows one assertion failure per family for the next-key row (a refusal where success is expected), zero errors, zero collection failures, and the current-key and wrong-key rows passing.
- browser/UI: n/a. smoke: n/a locally. manual: none.
- Human-gated (production): rollout steps 0 to 6.

## 14. Loop and stress testing
- Normal: current accepted; next accepted when honoured.
- Edge: next equal to current (label `current`, state `equals_current`); next equal to read-only (not honoured; that value refused on a write route); next set with current empty (503); next of exactly 32 characters honoured, 31 ignored; current with a trailing newline and next the same value stripped (accepted; state `equals_current`).
- Malformed: non-ASCII header and a lone-surrogate string (`"\ud800"`) → mismatch, no exception; next containing a space, a non-ASCII character, or a control character → ignored, current still works.
- Large: 64 KB presented value → mismatch, no exception (unit level).
- Empty: header absent, `""`, `"   "` against next unset, `""`, `"   "` → refused in every combination.
- Duplicate / idempotency: with a controlled clock, a second accepted or rejected event on the same key at 599 s logs nothing; at 600 s logs one line; two labels give two lines.
- Permission failure: read-only key on `mesh._check_secret` and on one non-mesh write route (401); accepted on both GET routes.
- Network / API failure, retry: n/a (no outbound call).
- Regression: every existing test in the integration list passes unchanged.
- Human checkpoint: founder approval before each rollout step.
- Bypass attempt (auth surface): present the read-only key, a blank header with a blank next value, or the process dummy value (test sets `_DUMMY` to a known value) to a write route → refused.
- Bypass attempt (guard surface): plant references by attribute, by `from .config import`, by `getattr` string, and by `os.environ` string in a temp tree → the guard finds all four; plant a `compare_digest` call in a new temp file → found; a pinned error text containing a variable name → NOT found.
- Bypass attempt (route surface): add a route that takes the header to the enumerated set without a family row → the enumeration test fails.
- Bypass attempt (log surface): accept under next and assert the capture is exactly the fixed template and contains neither key value.
- Mutants the tests must kill (each applied by monkeypatch or temp copy and seen red; supporting evidence saved as `mutants.txt`): `unconfigured` decided on `current or next`; early return after the first match (a spy that calls through to the real `hmac.compare_digest` counts the compares on a request presenting the current key); the dummy compare result kept; `len > 32` instead of `>= 32`; the read-only inequality skipped; "log once per process forever"; limiter keyed on slot only.

## 15. Acceptance criteria (become the Done contract)
Route table (26 routes, enumerated 17/11/2026 from the real routers on 71bad315: every route with a header parameter aliased `X-Pi-CEO-Secret`, plus every `routes/webhooks.py` handler that calls `_require_internal_webhook_secret`).
Write routes (24), accept current or honoured next:
- conversations: POST `/api/conversations/ingest` · GET `/api/conversations/search` · GET `/api/conversations/recent`
- cost_report: GET `/api/cost-report`
- routing: GET `/api/routing` (the header branch; an empty header still goes to session auth)
- delegate: POST `/api/margot/delegate`
- margot: POST `/api/margot/turn` · POST `/api/margot/voice`
- mesh: POST `/api/mesh/heartbeat` · GET `/api/mesh/claims` · POST `/api/mesh/claim/update` · POST `/api/mesh/claims/reap` · POST `/api/mesh/dispatch` · POST `/api/mesh/claim/self`
- mesh_lane_events: POST `/api/mesh/lane-events`
- mesh_ship: POST `/api/mesh/ship`
- webhooks: POST `/api/webhook/morning-intel` · POST `/api/webhook/routine-complete` · POST `/api/webhook/workspace-intel-refresh` · GET `/api/workspace-intel`
- wiki_sources: POST `/api/wiki/sources/upload` · GET `/api/wiki/sources` · GET `/api/wiki/requirements` · PUT `/api/wiki/requirements`
Read routes (2), additionally accept the read-only key: GET `/api/mesh/fleet` · GET `/api/mesh/lane-events`

- [ ] AC-1 Two-key acceptance, proven red-first. For each of the 26 routes one well-formed request is sent three times: wrong key → 401; current key → that route's named expected status (below 500, and never 401 or 422); honoured next key → the same status; where the handler calls a stubbed collaborator, the stub was called. Delegate goes through its real helper. The three sends are three separately named tests per route (`wrong`, `current`, `next`), so the red run can count them. Every test name starts `test_acNN_` with its criterion's two-digit number, so each Done recipe selects exactly its own tests. The recipes and their two checker scripts are in `recipes/` beside this spec. Proof: `tests/test_internal_secret_routes.py` passes on the build; and the recipe re-runs the same file against a clean export of 71bad315 and requires exactly 26 failed (the `next` tests, each an assertion failure), 0 errors, and the 52 `wrong` and `current` tests passed. That output is saved as `red-first.txt` beside this spec.
- [ ] AC-2 Texts and codes pinned: each of the three text families' exact 503 and 401 texts asserted; the order "not configured" before "missing" asserted for one helper of each family.
- [ ] AC-3 One owner: `tests/test_internal_secret_guard.py` scans the syntax tree of every `.py` file under `app/server`. Outside `config.py` and `internal_secret.py` it finds no Name, Attribute or import alias exactly equal to `INTERNAL_WEBHOOK_SECRET` or `WEBHOOK_SECRET`, and no string constant exactly equal to `INTERNAL_WEBHOOK_SECRET`, `WEBHOOK_SECRET`, `TAO_INTERNAL_WEBHOOK_SECRET`, `TAO_INTERNAL_WEBHOOK_SECRET_NEXT`, `TAO_WEBHOOK_SECRET` or `TAO_FLEET_READ_SECRET`. Match is equality, never substring. It finds `compare_digest` call sites only in an explicit allow-list of files (today's non-fleet-key comparers plus `internal_secret.py`). Controls in the same file: four planted reference forms and one planted compare site are found; a pinned error text and names such as `GITHUB_WEBHOOK_SECRET` are not; the scan of the real tree is non-empty for the two allowed files.
- [ ] AC-4 Every route that takes the header is tested: a test enumerates, from the real routers, every route with a header parameter aliased `X-Pi-CEO-Secret` plus every handler in `routes/webhooks.py` that calls `_require_internal_webhook_secret`, and asserts that set equals the 26 routes of the AC-1 route table (method and path); a planted extra route makes it fail.
- [ ] AC-5 Empty and malformed never match: header absent / `""` / whitespace × next unset / `""` / whitespace → refused on every write family; next-only with current empty → 503; non-ASCII header → 401 on every family; lone surrogate and 64 KB values → `mismatch` with no exception; the process dummy value → refused.
- [ ] AC-6 Next-value policy: honoured at exactly 32 characters; ignored at 31, with a space, with a non-ASCII or control character, when equal to current, when equal to read-only; in every ignored case the current key is still accepted and nothing raises; a next value with surrounding whitespace is honoured as its stripped form; current with a trailing newline plus the same value as next is accepted and reports `equals_current`.
- [ ] AC-7 Read-only stays read-only: read-only key → 401 on `mesh._check_secret` and one non-mesh write route, success on both GET routes; the fleet check returns 503 only when current, honoured next and read-only are all empty; the read-only key alone still opens the GET routes; `mesh_fleet_auth` contains no compare.
- [ ] AC-8 Visibility without leakage: accepted under next → the capture holds exactly one record whose message equals `internal_secret: accepted slot=next where=<label>` character for character, and contains neither key value; no accepted line when no next is honoured; a refusal logs `internal_secret: rejected reason=<missing|mismatch> where=<label>` with next set or unset; with a controlled clock, 599 s gives no second line and 600 s gives one; two labels give two lines; every slot compare runs on a request presenting the current key (call-through spy).
- [ ] AC-9 Start-up states: one test per line 1 to 7 of §9, each asserting the exact text and that no key value appears; `app_factory.py` no longer references the config attribute (covered by AC-3) and `on_startup` did not grow (size gate).
- [ ] AC-10 Reads at call time: changing `config.INTERNAL_WEBHOOK_SECRET` (monkeypatch) or either environment variable after import changes the next decision.
- [ ] AC-11 GitHub signature path untouched: with next honoured, a signature computed with the next value is refused AND a signature computed with the configured GitHub secret is accepted, in the same test; `git diff origin/main --stat` lists neither `app/server/webhook.py` nor `app/server/config.py`.
- [ ] AC-12 Nothing else breaks: the existing auth-touching files of §13 pass; full `pytest tests/` and `pytest swarm/` pass within the time limit; ruff, file-length, function-length and frozen-path checks exit 0.
- [ ] AC-13 Runbook and docs: `docs/runbooks/fleet-key-rotation.md` contains steps 0 to 6, the holder table with cadence and tick columns and the n8n and UNKNOWN rows, the three-part swap gate, the swap order (current first, then remove next), the combined undo, "roll forward only" and "never press Railway Rollback", the per-step "deploy it, note the deployment, read the start-up line", the two GitHub secret names listed separately, "read-only key must be a different value", limits L1 to L3, the unknowns U2 to U7 as things to observe, a "how to stop" line for steps 5 and 6, the seven-day rule for the unidentified poster, the note to ignore the `equals current` line during an undo, and the sentence that exposure ends only after steps 4, 5 and 6; `.env.example` and `DEPLOYMENT.md` name the three variables. Proof: one grep per required phrase. The phrase "60 minutes" must not appear as a gate.
- [ ] AC-14 (human-gated, production, not part of the build contract) Rollout steps 0 to 6, each on the founder's yes; proof per step as written in the runbook.

Supporting only (not criteria): `mutants.txt`; the measured baseline time.

## 16. Goal command
```text
/goal Implement the accepted SPM spec at .claude/done/spm/2026-11-17-ra-8408-two-key-secret/spec.md in the worktree /Volumes/Mini Mini 2T Storage/worktrees/Pi-Dev-Ops/ra-8408-two-key-secret. Completion condition: every X-Pi-CEO-Secret check in app/server calls app/server/internal_secret.py, a honoured next value is accepted on every route family, and the Done contract verifies AC-1..AC-13 on the exact final commit. Crew: lead builds test-first; review via the first eligible non-Claude lane from lane_registry.py; gates on the Mini. Constraints: local build only under APPROVE EXPERIMENT (no push, PR, merge or deploy until the independent review passes and the founder says yes); no unrelated files; fake secret values only; no file or function at its size limit grows; no Railway, Vercel, GitHub-secret or keychain command; red-first output kept. Stop and hand off if blocked by credentials, a founder-only decision, or a third failed review round. Queue push, PR and every rollout step for Phill in one batch.
```

## 17. Implementation sequence and crew
| Phase | Objective | Crew · model | Validation command | State |
|---|---|---|---|---|
| 1 | Local test environment; measure full-suite time on unchanged code | lead (main thread) | baseline exit code and seconds recorded | WIP |
| 2 | Red-first: route tests written, seen failing for the right reason on unchanged code | lead | AC-1 red output saved | idle |
| 3 | Owner module and its unit tests; wrappers; start-up call | lead | AC-1, AC-2, AC-5 to AC-11 recipes | idle |
| 4 | Guard and route-enumeration tests with controls; mutants seen red | lead | AC-3, AC-4, §14 mutants | idle |
| 5 | Runbook, `.env.example`, `DEPLOYMENT.md` | lead | AC-13 | idle |
| 6 | Full suite and size gates | lead | AC-12 | idle |
| 7 | Post-build review (crew-reviewer, crew-security, eng-performance, parallel, read-only) | sub agents | each high finding re-proved by lead | idle |
| 8 | Release gate: independent Tier 1 review until PASS within the three-round cap; then founder yes; push with receipt; GitHub green; PR | lead + non-Claude review lane | `pr-release-gate` | idle |
| Pi Durable | not needed | UNAVAILABLE → n/a | | |

Skill loadout: spm (plan · inline · front door) · engineering-requirements (plan · bench · required gate) · done-harness (all · inline · Done contract) · superpowers:test-driven-development (build · inline · red-first is a criterion) · pr-release-gate (release · inline · required before push).

## 18. Session-handoff seed
Planned: two-key acceptance behind one owner, per this spec. Key files: this spec; `engineering.md` beside it; `app/server/internal_secret.py` (new). Expected verification: Done contract AC-1..AC-13. Deferred risks: limits L1 to L3; unknowns U2 to U7 and U9; rollout steps are the founder's; the exposed value stays a fallback until step 6. Pickup: run `donectl status` in the worktree, read §17 for the first phase not marked complete, continue.

## 19. Recommendation
Approve experiment: build locally now. Release (push and PR) after the independent review passes and the founder says yes.

Founder batch
1. When the build is verified and independently reviewed: push and open the pull request (recommend yes).
2. After merge: rollout steps 0 to 6, one yes each, asked in order as each becomes ready (recommend yes to each).

Follow-up tickets to file with this spec, each checked for an existing ticket first:
(a) Steps 5 and 6: rotate the GitHub signing secret, retire `TAO_WEBHOOK_SECRET`, and remove the two `or WEBHOOK_SECRET` fallbacks in `config.py`. Owner: founder for production changes, lead lane for the code.
(b) Dashboard: two-key or removal of the morning-intel single-key hop (L1); remove the write-key fallback in `dashboard/lib/control/mesh-upstream.ts`; decide whether the dashboard should hold a write key at all.
(c) Alert when any machine's heartbeat is stale (the outage ran 36 hours because nothing alerted). Fleet-board 1% card with an owner.
(d) `routes/routing.py` takes a tenant id from the query string for any key holder: tenancy review.
(e) Migration ledger comparison could not run in this session (no database address): run it before the next change that adds a migration.

`Waterline: Class 1 · Stage spec (rung 3/12 specified) · A — evidence: six seat contracts, judge R2 94/100, one independent correctness pass (FAIL, folded), nine engineering-bench reports, all returned 17/11/2026; engineering gate PLANNED`
