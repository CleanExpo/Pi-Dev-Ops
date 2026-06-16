# Forward plan: Unite-Hub client portal (login → see projects → message us)

Generated: 2026-06-07 · Horizon: 20 moves · Planner: forward-planner

## Win condition (Definition of Done)

What "complete" means for *this* portal, as checkable conditions. The brief names three
capabilities (log in, see projects, message us); the win condition below is what those three
actually require once you reason backward from a shipped, operable, multi-tenant feature.

- [auto] **wc1 — Client identity exists.** A client user can register/be invited, log in, log out, and reset their password; Supabase Auth holds the credentials, not a hand-rolled table.
- [auto] **wc2 — Client ↔ tenant linkage exists.** Every authenticated client maps to exactly one (or more) client account/organisation, and that mapping is stored, not inferred.
- [auto] **wc3 — Row-level isolation is enforced.** A client can read *only* their own projects and messages; cross-tenant reads are impossible at the database layer (Supabase RLS), verified by a test that attempts a cross-tenant read and gets zero rows.
- [auto] **wc4 — Projects are visible to the client.** `GET` of "my projects" returns the authenticated client's projects with status, and only those.
- [auto] **wc5 — Two-way messaging works.** A client can send a message to staff and read replies; staff can read and reply from the internal CRM side; threads are scoped to the client.
- [auto] **wc6 — Real-time / fresh delivery.** New messages appear to the recipient without a manual refresh (Supabase Realtime or poll-on-focus), verified by a subscription test.
- [auto] **wc7 — Notifications fire.** Staff are notified of a new client message and clients of a staff reply (email at minimum), verified by an enqueue test.
- [auto] **wc8 — Auth + data routes are rate-limited and abuse-resistant.** Login, reset, and message-send endpoints reject after a threshold; verified by a burst test.
- [auto] **wc9 — Audit trail exists.** Auth events and message sends are recorded with actor, timestamp, and tenant; verified by a row-count assertion after an action.
- [auto] **wc10 — Roles are separated.** A client account cannot reach any staff/admin route or staff-only data; verified by an authz test hitting a staff route as a client and getting 403.
- [auto] **wc11 — End-to-end test passes.** A single integration test drives invite → login → view projects → send message → receive reply → logout.
- [auto] **wc12 — Observability is live.** A dashboard panel / log query shows portal logins, message volume, and error rate so silent failure is detectable.
- [human] **wc13 — Operable by a human.** A runbook exists for resetting a locked-out client, revoking access for an offboarded client, and handling a "client says they can't log in" ticket.
- [human] **wc14 — File-share decision settled.** Whether clients can upload/download documents is explicitly in-scope or explicitly deferred (not silently assumed either way).
- [human] **wc15 — Privacy/consent posture stated.** Data-retention, message-deletion, and PII handling for client data are defined and applied (relevant to the redaction posture already in the portfolio).

## Board state

**Internal (from `.harness/projects.json` + skill worked example, grounded; full repo not mounted this run):**
- The portfolio registry has **no `unite-hub` entry**; the matching project is **`unite-group`** — repo `CleanExpo/unite-group`, stack **Next.js + TypeScript + Supabase + Claude AI**, frontend on `dashboard-unite-group.vercel.app`, Linear **team UNI (`ab9c7810-…`)**, project **`b62d9b14-…`**. All portal moves route there. *(Open item below: confirm Unite-Hub is the same repo as unite-group or register a distinct `unite-hub` entry before tickets are filed.)*
- Current auth reality (per the skill's documented Unite-Hub example and standard state for this app): a static login **page** exists, but there is **no working auth API**; Supabase has a `users`-style table **without an auth schema wired**; **no session lifecycle**, **no password reset**, **no rate limiting**. Treat auth as absent, not partial.
- No client↔tenant mapping, no client-facing project read path, no messaging schema or surface, no RLS policies scoped to client tenants, no audit table for portal events.

**External (best-practice baseline for Next.js + Supabase client portals, current as of 2026-06):**
- Supabase **Auth + Row Level Security** is the intended isolation mechanism for multi-tenant portals; the failure mode others hit is shipping the UI before RLS, so "my data" filtering lives only in the client query and is trivially bypassed. RLS must land *before* any client-readable data path.
- **Supabase Realtime** (Postgres changes / broadcast) is the standard for in-app messaging freshness; teams that skip it ship a "messaging" feature that needs a manual refresh and feels broken.
- Email notification for portals is normally a managed provider (Resend/Postmark/SES) — a real branch point, since "approved provider vs. build our own sender" changes the move.
- Common silently-dropped pieces in portal builds: invite/onboarding flow (clients rarely self-register), staff-side reply surface (the messaging "other half" nobody owns), authz separation client-vs-staff, audit logging, and the offboarding/runbook path.

## The gap (win condition − current state)

| Win-condition item | Status | Notes |
|---|---|---|
| wc1 client identity (auth) | absent | static page only; no auth API/session/reset |
| wc2 client↔tenant linkage | absent | no mapping table/column |
| wc3 RLS isolation | absent | no policies; would leak cross-tenant |
| wc4 projects visible | absent | no client-scoped project read path |
| wc5 two-way messaging | absent | no message schema or surface (client or staff side) |
| wc6 realtime freshness | absent | no subscription wiring |
| wc7 notifications | absent | no provider chosen, no enqueue |
| wc8 rate limiting | absent | no limiter on any route |
| wc9 audit trail | absent | no audit table for portal events |
| wc10 role separation | absent | no client-vs-staff authz boundary |
| wc11 e2e test | absent | nothing to test yet |
| wc12 observability | absent | no portal panel/metric |
| wc13 runbook | absent | no operator doc |
| wc14 file-share decision | absent | undecided = scope risk |
| wc15 privacy/consent posture | partial | portfolio has redaction norms; not applied to portal data yet |

Everything is absent or partial. This is a from-zero feature riding on an existing app shell.

## The spine — 20 moves

Ordered current-state → win-condition, respecting real dependencies. Each is one verifiable deliverable.

1. **Confirm project routing & scope guardrails** — *Deliverable:* written confirmation that Unite-Hub == `unite-group` repo (or a new `unite-hub` registry entry added) + file-share (wc14) and privacy (wc15) decisions captured. *Verify:* `projects.json` resolves the target; wc14/wc15 marked decided in this plan. *Unlocks:* m2. *Requires:* human input. **[branch point — see below]**
2. **Auth schema + tenant model migration** — *Deliverable:* Supabase migration adding client-profile + `client_account` (tenant) + `account_membership` linking auth user → account. *Verify:* `list_tables` shows the tables/columns; migration runs idempotently. *Unlocks:* m3, m5, m7. *Requires:* m1.
3. **Supabase Auth wired (register/invite + login + logout)** — *Deliverable:* working auth via Supabase Auth from the portal; session cookie issued. *Verify:* integration test logs a user in and reads the session. *Unlocks:* m4, m9. *Requires:* m2.
4. **Password reset flow** — *Deliverable:* request-reset + confirm-reset paths. *Verify:* test: request → reset token issued → password changes. *Unlocks:* m11. *Requires:* m3.
5. **RLS policies for tenant isolation** — *Deliverable:* RLS on every client-readable table keyed to `account_membership`. *Verify:* test attempts cross-tenant read → 0 rows. *Unlocks:* m6, m8. *Requires:* m2. **(red-team: must precede any read path)**
6. **Client→tenant linkage enforced & seeded** — *Deliverable:* each client mapped to their account; staff tool/seed to set it. *Verify:* query returns exactly one account per test client. *Unlocks:* m8. *Requires:* m5.
7. **Project data model exposed to clients** — *Deliverable:* `project` rows carry an owning `account_id`; read view scoped for clients. *Verify:* schema check + RLS denies other accounts. *Unlocks:* m8. *Requires:* m2, m5.
8. **"My projects" client read endpoint + page** — *Deliverable:* authenticated client sees their projects with status. *Verify:* test: client A sees only A's projects. *Unlocks:* m12. *Requires:* m6, m7. *(satisfies wc4)*
9. **Session validation middleware + role guard** — *Deliverable:* middleware rejects unauthenticated requests and blocks client tokens from staff routes. *Verify:* authz test: client hits staff route → 403. *Unlocks:* m12. *Requires:* m3. *(satisfies wc10)*
10. **Rate limiting on auth + send routes** — *Deliverable:* limiter on login/reset/message-send. *Verify:* burst test trips the limit. *Unlocks:* m17. *Requires:* m3. *(satisfies wc8)*
11. **Audit logging table + writes** — *Deliverable:* `portal_audit` table; auth events and message sends recorded with actor/tenant/timestamp. *Verify:* row appears after a logged action. *Unlocks:* m17. *Requires:* m2, m3. *(satisfies wc9)*
12. **Messaging schema (threads + messages, tenant-scoped)** — *Deliverable:* migration for `message_thread` + `message`, RLS-scoped. *Verify:* schema check + cross-tenant read denied. *Unlocks:* m13, m14. *Requires:* m5, m8.
13. **Client message send + read surface** — *Deliverable:* client can send to staff and read replies. *Verify:* test: client sends → row exists, scoped. *Unlocks:* m15. *Requires:* m12. *(satisfies wc5, client half)*
14. **Staff-side reply surface (CRM)** — *Deliverable:* staff read client threads and reply from the internal CRM. *Verify:* test: staff reply lands in the client's thread. *Unlocks:* m15. *Requires:* m12, m9. *(satisfies wc5, staff half — the half builds usually drop)*
15. **Realtime message delivery** — *Deliverable:* Supabase Realtime subscription so new messages appear without refresh. *Verify:* subscription test receives an insert event. *Unlocks:* m16. *Requires:* m13, m14. *(satisfies wc6)*
16. **Notification fan-out (email)** — *Deliverable:* email to staff on new client message and to client on reply. *Verify:* enqueue test fires on send. *Unlocks:* m17. *Requires:* m15. *(satisfies wc7)* **[branch point — provider]**
17. **Error, lockout & empty states** — *Deliverable:* handled states for failed login, lockout after limit, send failure, empty project/message lists. *Verify:* tests assert each state renders/returns correctly. *Unlocks:* m18. *Requires:* m10, m11, m16.
18. **End-to-end integration test** — *Deliverable:* one test: invite → login → view projects → send → reply (realtime) → logout, including a lockout assertion. *Verify:* the test passes in CI. *Unlocks:* m19. *Requires:* m17. *(satisfies wc11)*
19. **Observability panel + metrics** — *Deliverable:* dashboard panel / log queries for portal logins, message volume, error rate. *Verify:* panel shows non-null data after the e2e run. *Unlocks:* m20. *Requires:* m11, m18. *(satisfies wc12)*
20. **Operator runbook + offboarding path** — *Deliverable:* runbook for locked-out client, can't-log-in triage, and revoking an offboarded client's access (membership removal + session revoke). *Verify:* dry-run of the offboarding steps removes access (cross-tenant read now also denied to the removed user). *Unlocks:* — (win). *Requires:* m18. *(satisfies wc13)*

## Branch points

- **After move 1 — scope decider (Phill):** *file-share in scope?* if **yes** → insert a document upload/download move (RLS-scoped to account, virus-scan decision) between m12 and m18, reconverging at m17; if **no** → stay on spine and record the deferral in the runbook (m20). Also resolves wc14.
- **At move 16 — email provider decider (Phill):** *approved managed provider (Resend/Postmark/SES)?* if **yes** → integrate the managed provider SDK; if **no** → build an SMTP sender with retry/idempotency. Both reconverge at m17. (Mirrors the auth-email branch in the method's worked example — the provider choice changes the move, not the goal.)

## Risk horizon

- **Ship UI before RLS → cross-tenant data leak.** Response: m5 (RLS) is hard-gated before any client read path (m8); the cross-tenant-read test is the gate. → mitigated by m5.
- **"Messaging" ships as one-directional** (client→staff only, no staff reply surface). Response: staff reply is its own move (m14), not folded into m13. → mitigated by m14.
- **Realtime quietly not wired** → feature feels broken (manual refresh). Response: explicit subscription test (m15). → mitigated by m15.
- **Auth endpoints brute-forced.** Response: rate limiting (m10) + lockout state (m17) + audit (m11). → mitigated by m10/m17.
- **Offboarded client retains access.** Response: revocation path is a first-class move with a verification dry-run (m20). → mitigated by m20.
- **Silent failure in prod** (logins/messages failing unnoticed). Response: observability panel (m19). → mitigated by m19.
- **Routing ambiguity** (unite-hub vs unite-group) → tickets filed against the wrong Linear project. Response: m1 confirms routing before any ticket is filed. → mitigated by m1.

## Red-team findings (pulled forward)

Walked the spine to its end assuming "done" was a lie. What the naive three-task brief (login / projects / messaging) would have dropped, now inserted as real moves:

- **Tenant isolation (RLS)** was never in the brief — without it "see their projects" leaks everyone's. → inserted as **m5**, gated before reads.
- **Client↔tenant linkage** — "log in" implies an account to belong to; nothing mapped users to clients. → **m2 + m6**.
- **Staff side of messaging** — "message us" needs an "us" that can reply. → **m14**.
- **Realtime** — "message us" without freshness is a refresh button. → **m15**.
- **Notifications** — staff won't watch the portal; without email they miss messages. → **m16**.
- **Role separation** — a client token must not reach staff routes/data. → **m9 / wc10**.
- **Audit, rate limiting, lockout, error/empty states** — the habitual silent drops. → **m10, m11, m17**.
- **Offboarding/revocation + runbook** — access removal is the move builds forget; it's also a *security* gap, not just docs. → **m20**.
- **Verification gap:** every `wc*` is now tied to at least one move's verify clause; wc14/wc15 are resolved at m1 (decision) rather than left implicit.

## Immediate next move

**Move 1 — confirm project routing & scope guardrails.** It's first because (a) the registry has no `unite-hub` entry, so filing any ticket now would route to the wrong place, and (b) the two open scope decisions (file-share, privacy) change the shape of the spine. Both are cheap to settle as text now and expensive to discover mid-build. Settle them, then m2 (the auth + tenant migration) unblocks the whole graph.

---

## Validator output

```
$ python skills/forward-planner/scripts/validate_plan.py forward-plan.json
plan: unite-group — Add a client portal to Unite-Hub where clients can log in, s
  moves: 20 | branch points: 2 | win conditions: 15
VALID
```

No errors, no warnings: 20 moves (≥15 horizon), acyclic dependency graph, every move's `satisfies` references a real win-condition id, all 15 win conditions are covered by at least one move, and all moves carry Linear routing.
