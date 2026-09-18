# Brief: Mission Control "Live Wall" v1

Status: **DRAFT — awaiting cross-vendor adversarial review (Round 0c).** No implementation
may begin until a different-vendor reviewer has returned a verdict and every confirmed
blocking finding is fixed.

Audience: the implementing agent and the independent reviewer. Phill reads the SHIP-DELTA
lines on the tickets, not this file.

---

## 1. What this is for

Phill cannot read terminals. Seeing work happen is how he trusts it. One monitor on each of
three machines runs a full-screen wall he can glance at from across the room.

**A wall that shows fake or self-reported "healthy" is worse than no wall.** That is the whole
design constraint, and it is why section 3 is frozen.

## 2. What the machine actually says today — VERIFIED, not assumed

Read on 2026-09-18 against `origin/main` at `5bda16b1`. Every line here was checked; the
recipe card's guesses are corrected where they were wrong.

| Claim | Verified state |
|---|---|
| Mission Control lives at `dashboard/app/(main)/command-centre` | **TRUE**, but it is a 76-line link index over 4 decks (hermes, knowledge, providers, wiki-graph). Header says "READ-ONLY. No data access, no writes." There is no fleet view, no wall, no live feed. |
| Heartbeats travel over Tailscale | **FALSE.** `docs/runbooks/fleet-operations.md`: "Transport is HTTPS to the Railway API, not peer-to-peer, so a machine on hotel wifi works exactly like one on the LAN." Tailscale is **stopped** on this MacBook right now, and both other machines are unreachable (`ssh` to `100.107.147.59` times out). |
| A fleet data source must be built | **FALSE — it exists.** `GET /api/mesh/fleet` (RA-7392, `app/server/mesh_fleet.py`) already returns machines, agents, ships and work claims. |
| Nothing enforces honest empty-vs-broken | **FALSE — already enforced.** `mesh_fleet.py` docstring: a failed read used to become `{"machines": []}`, "byte-identical to a fleet nobody has joined yet". Both failure shapes now "resolve to an empty list AND are reported, so 'empty' and 'broken' stop being the same answer." |

### The existing tables (`mesh/schema/0001_nexus_mesh.sql`)

- `mesh_machines` — `host` PK, `status`, `cpu_pct`, `mem_pct`, `load1`, `agent_runtimes`,
  **`last_seen`**, upserted by the heartbeat daemon every ~20s. This is the staleness source.
- `mesh_agents` — `machine`, `runtime`, `repo`, `branch`, `current_task`, `state`
  (idle | working | shipping | error), `updated_at`.
- `mesh_ships` — `machine`, `repo`, `branch`, `sha`, `subject`, `files_changed`, `shipped_at`.
- `mesh_work_claims` — claim state.
- `mesh_fleet` is a **VIEW** (schema line 65), not a missing table. The reader is correct.

### The fleet: `phills-macbook-pro` (mobile), `unite-mac-mini` (always on), `phill-desktop` (Windows)

### Two hard blockers, both founder-only

1. **The fleet is not enlisted.** The runbook's own ACTION REQUIRED item 1 is
   `bash mesh/bootstrap.sh` on each of the three machines; until then "No machine is fully
   enlisted and dispatchable." It states plainly that these items need "a credential, a machine
   you are sitting at, or a Google consent screen — none of which an agent can supply."
2. **`GET /api/mesh/fleet` returns HTTP 401** from here. `/health` returns 200, so Railway is
   alive; the fleet read needs a credential the wall's server side must hold.

**Consequence, and it is the correct behaviour, not a failure:** when v1 ships, the wall will
show **GREY "NO LIVE SOURCE YET"** for the fleet tiles, because there is genuinely no signal.
That is the honest answer. It must not be filled with sample rows to look finished.

## 3. THE ONE LAW (frozen — a reviewer must reject any diff that weakens this)

The wall READS ONLY from sources the build pipeline does not author:

- **Linear** — ticket existence and state
- **GitHub** — CI conclusion **by head SHA**, PR state, commits
- **Live production URL probes** — does the deployed thing answer correctly

The pipeline never writes a status the wall displays as proof. Nothing starts green. **Absent
is UNKNOWN — never zero, never pass.**

### Correction after review — the self-reported set is WIDER than one exception

The draft claimed "machine heartbeats are the single exception". **That was false**, and the
reviewer was right to block on it. The whole of the mesh is self-reported by agent processes:

| Table | Self-reported by | Own staleness rule required |
|---|---|---|
| `mesh_machines` | the heartbeat daemon | `last_seen` > 60s → GREY |
| `mesh_agents` | each agent process | `updated_at` > 90s → GREY, **even if the machine heartbeat is fresh** |
| `mesh_ships` | the autogit reporter | an event, not a state — shown with its age, never as health |
| `mesh_work_claims` | the claiming agent | `claimed_at` > 30 min with no ship → GREY "stale claim" |

**Every mesh-derived value carries a visible `self-reported` label.** The named failure the
reviewer found: an agent crashes while its machine's heartbeat daemon stays alive, so the
agent tile would have shown "working" forever. Its own staleness clock fixes that.

### Correction after review — CI is pipeline-adjacent, so Prove needs two sources

GitHub Actions is executed by the build pipeline, so a green CI conclusion is *partly*
self-authored: weaken the workflow and it reports success. The ONE LAW cannot be fully
satisfied by CI alone. Therefore **the Prove chip requires BOTH** the GitHub CI conclusion for
the head SHA **AND** the independent checker's headed-browser run. Either one absent → GREY.
CI green alone is never enough to turn Prove green. This is a stated, accepted limit, recorded
here rather than hidden.

## 4. The seven stations

Capture → Shape → Contract → Build → Prove → Ship → Learn.

One card per ticket. One proof chip per station. GREEN only when an outside source says so;
RED on failure; GREY on unknown.

| Station | Proven GREEN by | Source authored by |
|---|---|---|
| Capture | Linear issue exists | Linear |
| Shape | Linear description contains a falsifiable done-test **— absent ⇒ GREY, never green** | Linear |
| Contract | acceptance criteria recorded before the first commit was **received by GitHub** | Linear + GitHub push event |
| Build | a real commit + PR exists for the ticket | GitHub |
| Prove | CI `conclusion == success` for the head SHA **AND** independent checker's headed run — either absent ⇒ GREY | GitHub + checker |
| Ship | a **ticket-specific** marker is live at the production URL (see below) | production URL |
| Learn | SHIP-DELTA line present on the ticket | Linear |

### Correction after review — the Ship chip must not go green just because the site is up

The draft said "live URL probe answers correctly". The reviewer correctly blocked this: a
generic probe against a healthy site would turn **every** in-progress ticket's Ship chip green,
including reverted and never-merged ones. That is the exact false-green the wall exists to
prevent.

**Fixed rule, revised again after round 2.** Ship goes GREEN only when a **ticket-declared
probe assertion passes right now** — a URL plus an expected response the ticket itself names.
That live assertion is the *primary and sufficient* evidence, because it tests behaviour rather
than history.

No ticket-declared assertion ⇒ **GREY "no ship test declared"**, never green. Site-up alone is
never Ship.

**Ancestry is a supporting signal only, and must never stand alone. PROVED by control:**
git ancestry is monotonic, so a reverted change still reports as shipped forever. In a scratch
repo — feature commit, then a real `git revert`, preconditions asserted (HEAD advanced, and
`feat.txt` confirmed gone from the tree) — `git merge-base --is-ancestor` still answered **YES**.
A design that trusted ancestry would show GREEN for a change that had been removed from
production. Hence the live assertion decides Ship; ancestry may only *downgrade* a green, never
create one.

### Correction after review — git commit dates are NOT usable for Contract

**Proved, not argued.** In a scratch repo, setting `GIT_AUTHOR_DATE` and `GIT_COMMITTER_DATE`
produced a commit git reports as `2020-01-01 00:00:00 +0000`. So "criteria recorded before
first commit" computed from commit metadata is trivially backdatable by the very agent it is
meant to constrain.

**Fixed rule.** Use the time GitHub *received* the push (the push/commit event timestamp from
the GitHub API, which the pusher cannot set), compared against the Linear comment/field
timestamp. If either timestamp is missing, the chip is **GREY** — the comparison is never run
against a null, because `criteria < null` must never be allowed to evaluate truthy.

### No comparison may run against an absent value

Every chip rule is written as: *if any input is absent → GREY*. That precedes all other logic.
The reviewer's finding 7 was that a naive `criteria_recorded < first_commit` goes vacuously
true when `first_commit` is null or defaults to now. This ordering forbids it.

**"Absent" is defined explicitly, after round 2.** The draft said "absent" and left it to the
implementer, which would have let an API's empty answer slip through as present. Absent means
**any** of: the key is missing; `null`; `undefined`; an empty string; a whitespace-only string;
an empty array; an empty object; or a numeric `0` where the field is an identifier or timestamp
rather than a count. An upstream returning `[]` for commits, or `""` for a SHA, is **absent** —
not "present and therefore comparable". Each chip declares its required inputs by name, and a
single shared guard checks all of them against that definition before any comparison runs.

## 5. Screens

Three machines × two monitors = six tiles in the fleet view. Monitor 2 of each machine runs
the wall.

Kiosk URL: `/command-centre/wall?machine=<host>&screen=<n>`. `machine` must match a
`mesh_machines.host` value; an unknown host renders a GREY "unknown machine" card rather than
an empty page.

Accordion: one station expanded at a time, auto-advancing through its cards, then to the next
station. "Follow the action" jumps to whichever station just had a real event. **Click pauses;
idle resumes.** Large type, dark theme, readable across a room. No horizontal scroll.

### Correction after review — the accordion must never hide a RED

The reviewer blocked the accordion as designed: a RED card inside a collapsed station is
invisible to someone glancing from across the room, which is a wall reporting false health.
Accepted. Three rules override the carousel:

1. **A persistent failure banner sits outside the accordion**, always visible, carrying live
   counts: `RED n · GREY n`. It is never collapsed and never auto-hidden. If both counts are
   zero it still renders, showing zero — so "no banner" can never be mistaken for "no problems".
2. **Auto-advance cannot skip a station holding a RED or a GREY.** Revised after round 2: the
   draft restricted rotation to RED-holding stations only, which would have hidden an entirely
   GREY station — one that had lost all its data sources — for as long as any RED existed. That
   is the same false-health bug in a new place. **Rotation covers every station holding a
   non-GREEN chip**, RED ordered first. A station is skipped only when all its chips are GREEN.
3. **A station with a RED or GREY renders its header in that colour even when collapsed.**
   Colour survives collapse; only detail is hidden.

## 6. Live-update method — chosen after reading the repo

`rg` found **no** `EventSource`, no `text/event-stream`, and no Supabase Realtime channel
anywhere under `dashboard/`. So neither transport is established and the choice is open.

**Decision REVERSED after review: client-side polling of a cached snapshot, not SSE.**

The draft chose SSE. The reviewer blocked it, and on measurement the substance holds even
though "structurally unfeasible" overstates it. `dashboard/vercel.json` sets no `maxDuration`,
so the platform default applies and a long-lived SSE connection is cut and re-established
repeatedly. For a 24/7 kiosk that is on the order of a few hundred reconnects per screen per
day across six screens, each one capable of triggering a fresh upstream poll — a rate-limit and
cost problem for no benefit, since the wall does not need sub-second latency. A founder
glancing across a room does not need a push socket.

**Chosen design:**

- One **cached snapshot endpoint** on the dashboard returning the whole wall state as JSON,
  server-side cached for a few seconds so six screens polling do not multiply upstream calls.
- **The payload carries `generated_at`, and the browser enforces it.** Added after round 2: a
  cached endpoint whose updater has crashed keeps answering `HTTP 200` with the last good
  payload, so the wall would display stale data as live — a 200 is not freshness. If
  `generated_at` is older than three poll intervals, or the field is missing entirely, the wall
  renders a full-width GREY **"SNAPSHOT STALE — age Ns"** and every chip drops to GREY. The
  client trusts the timestamp, never the status code.
- The wall **polls that endpoint** on a short interval and re-renders in place. This satisfies
  "must update without refresh" — the page never reloads — without any long-lived connection.
- The upstream readers (GitHub, Linear, URL probes) run behind that cache, on polite intervals
  within published rate limits. **Six screens must cost the same upstream as one.**
- `api/webhook/github` already exists and is preferred over polling for PR/CI events.

If sub-second latency is ever genuinely needed, the persistent Railway container is the correct
host for a push channel — not a serverless function. Recorded so the option is not lost.

## 7. Stale / grey rules

| Condition | Renders |
|---|---|
| `mesh_machines.last_seen` older than 60s (3× the ~20s beat) | GREY "no signal", age shown |
| Source read returns the `problem` flag from `parse_rows` | GREY "SOURCE BROKEN — <reason>", never empty |
| No live source wired for a panel | GREY "NO LIVE SOURCE YET — <what would feed this>" + a Linear ticket filed |
| CI conclusion absent for the head SHA | GREY, never green |
| URL probe non-2xx or wrong body | RED |

`empty` and `broken` must never render the same. That distinction already exists server-side;
the wall must not collapse it.

## 8. PROOF — the control pair, written before implementation

The maker never grades. An independent checker (different model, fresh context, no builder
history) runs these, in a **headed** browser Phill can watch, screenshots to `.handoff-logs/`.

**Known-good control.** Move a real ticket in Linear → the card appears/moves on the wall
within one poll window, with no page refresh.

**Known-bad controls — every one must go RED or GREY, and none may stay green:**

1. Stop one machine's reporter → that machine's tiles go GREY "no signal" within 60s.
2. Point a URL probe at a dead address → that ticket's Ship chip goes RED.
3. Remove a source credential in a test environment → panel shows "NO LIVE SOURCE",
   **not zero and not green**.
4. Feed a head SHA with no CI run → Prove chip GREY, never green.

**Grep proof.** No mock, sample or fixture data reachable from any production wall route.
Run with `rg --no-ignore` and exclude nothing: this machine's `grep` is aliased to
`ugrep --ignore-files`, which silently hides `app/workspaces/`, so a clean `grep` result here
is not evidence.

**CI proof.** Read the conclusion from GitHub for the head SHA. My own local test run is not
the evidence.

## 9. Units, and what is blocked

| Unit | Buildable now? |
|---|---|
| 1 — Fleet view (6 tiles) | **Partly.** The reader and the tiles ship; they will correctly show GREY until bootstrap runs. Installing reporters on the other two machines is **BLOCKED** — Tailscale is stopped and both hosts are unreachable. |
| 2 — Wall (kiosk accordion) | **Yes.** Renders GREY honestly with no data. |
| 3 — Live feed (SSE) | **Yes** for transport and the GitHub reader. The Linear reader and the fleet read need credentials. |
| 4 — Honest placeholders | **Yes.** This is the unit that makes an empty wall truthful rather than broken. |
| 5 — Put it on the screens | **BLOCKED** — needs the other two machines reachable. |
| 6 — "See it now" click-through | **Gated.** A T3 session must still load the fence, enforcer and hooks. Prove it with a test; if it does not, report it as a bypass and **do not wire the click-through.** |

Deferred to tickets, not built now: raw desktop capture per monitor; Margot voice entry; the
command line that writes to Linear.

## 10. What needs Phill (one list, not a conversation)

1. Start Tailscale on this MacBook (nothing can reach the other two machines until then).
2. `bash mesh/bootstrap.sh` on each of the three machines, plus the two `schtasks` commands it
   prints on `phill-desktop`.
3. Set `MESH_DISPATCH_ENABLED=1` on Railway.
4. Provide the credential that makes `GET /api/mesh/fleet` return 200 rather than 401.

Until 1 and 2 are done the wall is **honestly grey**. That is a working wall reporting the
truth, not a broken one.

---

## 11. Round 0 review log

**Reviewer:** `gemini-3.1-pro-preview` — a different vendor to the author (Claude). Codex was
first choice and was unavailable: token valid but **quota exhausted until 19 Sep**, so the free
Gemini lane was used per the cost law. No paid API lane was touched.

**Verdict on draft 1: FAIL**, 7 blocking findings. Full text saved to
`.handoff-logs/live-wall-v1-gemini-review.txt`.

Every finding was source-verified before acceptance, because reviewers fabricate.

| # | Finding | Verification | Outcome |
|---|---|---|---|
| 1 | Ship chip turns green whenever the site is up, for every ticket | Re-read §4: it said only "live URL probe answers correctly", with no binding to the ticket. Reviewer right. | **CONFIRMED — fixed.** Ship now needs the merge SHA present in the deployed revision plus a ticket-declared assertion. |
| 2 | Accordion hides a RED inside a collapsed station | Correct by inspection of §5. A rotating single-panel view cannot guarantee a failure is on screen. | **CONFIRMED — fixed.** Persistent failure banner, RED-restricted rotation, colour survives collapse. |
| 3 | SSE on serverless is broken | Partly overstated — the platform does support SSE. But `dashboard/vercel.json` sets no `maxDuration`, so connections are cut and reconnect, each reconnect able to trigger an upstream poll. Substance holds. | **PARTIAL — accepted.** SSE dropped for cached-snapshot polling. |
| 4 | CI is authored by the pipeline, so it cannot prove itself | True in principle; it challenges the source list the brief was given. Mitigated rather than dismissed. | **ACCEPTED as an inherent limit.** Prove needs CI **and** the independent checker; CI alone never turns it green. |
| 5 | Git commit dates are spoofable, so the Contract check is worthless | **Proved by control.** In a scratch repo, setting the two date env vars produced a commit reported as `2020-01-01 00:00:00 +0000`. | **CONFIRMED — fixed.** Use GitHub's received-push time, which the pusher cannot set. |
| 6 | The self-reported set is wider than the one stated exception | Correct, and the most damaging finding. §3 claimed heartbeats were the single exception while §4 relied on `mesh_agents` for current task. All four mesh tables are agent-written. | **CONFIRMED — fixed.** All four labelled self-reported, each with its own staleness clock. |
| 7 | Absent values could evaluate vacuously true | Correct. `criteria < null` is exactly the bug class this wall exists to expose. | **CONFIRMED — fixed.** "Any input absent ⇒ GREY" now precedes all chip logic. |

Non-blocking findings recorded against the units that will meet them: kiosk authentication on
keyboardless screens (unit 5), hostname-in-query-param fragility (unit 2), and the difficulty
of simulating a head SHA with no CI run at all (unit 3, control 4).

**Findings the reviewer could not judge** — it had no repo access and said so rather than
bluffing: the existence and contents of the files in §2, the Tailscale and SSH state, and the
`grep` alias behaviour. All three were verified first-hand against `origin/main` and are cited
inline in §2.

### Round 2 — verdict FAIL, 4 new blocking findings

Three of the four were flaws introduced **by the round-1 fixes themselves**, which is the
argument for re-reviewing rather than declaring victory after one pass.

| # | Finding | Verification | Outcome |
|---|---|---|---|
| 1 | Ancestry is monotonic, so a reverted ticket stays GREEN forever | **Proved by control** — see below | **CONFIRMED — fixed.** Live assertion decides Ship; ancestry may only downgrade. |
| 2 | Restricting rotation to RED stations hides a fully-GREY dead station | Correct by inspection of my own round-1 fix | **CONFIRMED — fixed.** Rotation covers every non-GREEN station. |
| 3 | A crashed cache updater serves stale data as live behind `HTTP 200` | Correct; a 200 is not freshness | **CONFIRMED — fixed.** `generated_at` + client-enforced staleness. |
| 4 | `[]` and `""` are present-but-absent and slip the guard | Correct | **CONFIRMED — fixed.** "Absent" now enumerated explicitly. |

**The revert control, and a warning about controls.** First attempt passed `-q` to
`git revert`, which does not accept it. No revert happened, yet the script printed
"FALSE GREEN PROVEN" anyway — a control that reported a result it had never measured, which is
precisely the defect class this wall exists to expose. Rewritten with `set -e` and two asserted
preconditions (HEAD must advance; `feat.txt` must be gone). Only then: a real revert commit,
the file confirmed removed, and `git merge-base --is-ancestor` still answering **YES**.

Recorded because it is the sharpest lesson available here: **a control that cannot fail proves
nothing, and my first one could not fail.**

### Round 3 — verdict PASS

All four round-2 findings confirmed FIXED with the new text quoted back. Reviewer's closing
line: **"REMAINING FALSE-GREEN PATHS: none."**

Three rounds, 11 blocking findings, every one source-verified before acceptance. Round 0's
review gate is satisfied and implementation may begin. The same gate applies again to the
finished code before any PR is marked ready.
