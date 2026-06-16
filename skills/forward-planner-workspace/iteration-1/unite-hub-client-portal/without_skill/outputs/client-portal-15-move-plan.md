# Unite-Hub Client Portal — Full Route Mapped 15 Moves Ahead

**Goal:** Clients log in, see their projects, and message the team.
**Stack:** Next.js (App Router) + TypeScript + Supabase (Postgres, Auth, Storage, Realtime, RLS).
**Document purpose:** Map the *entire* route before any code is written, including the parts that are easy to forget and that have historically caused "the build is missing something" surprises. Each move lists what to build, the easy-to-forget items inside it, the gate that proves the move is done, and what it unblocks.

---

## How to read this

- **Moves 1–15 are ordered by dependency**, not by visible feature value. The visible features (login, project list, messaging) sit in moves 6–9. Everything before them is foundation; everything after is the stuff that turns a demo into a product clients trust.
- **"Easy to forget" boxes** are the answer to your core complaint. These are the items that are invisible in the happy-path demo but block launch or cause incidents later.
- **Each move has an explicit Definition of Done (DoD)** so "missing something" becomes detectable, not discovered in production.

---

## The 15 moves at a glance

| # | Move | Why it must come here | Visible to client? |
|---|------|----------------------|--------------------|
| 1 | Decide the tenancy & identity model | Everything downstream keys off "who is this client and what can they see" | No |
| 2 | Data model + RLS contract | The portal's security is the schema, not the UI | No |
| 3 | Auth: client invite, login, session, recovery | Clients are not staff; separate auth surface | Yes (login) |
| 4 | Authorization layer (route + data guards) | Login ≠ permission; this is the second wall | No |
| 5 | Portal shell, layout, navigation, empty states | The frame everything renders into | Yes |
| 6 | Projects: list + detail (read) | First real feature | Yes |
| 7 | Messaging: threads, send, read state | Second real feature | Yes |
| 8 | Realtime + notifications (in-app, email) | Messaging is dead without delivery awareness | Yes |
| 9 | File sharing / attachments | Clients always ask for this immediately | Yes |
| 10 | Staff-side admin: who sees what, impersonation, replies | The portal is two-sided; staff side is half the build | Internal |
| 11 | Audit log, observability, error tracking | You cannot operate what you cannot see | No |
| 12 | Security hardening + privacy/compliance | Client data = legal exposure | No |
| 13 | Email/domain, transactional infra, deliverability | Invites and notifications must actually arrive | Partly |
| 14 | Onboarding, offboarding, lifecycle, billing hooks | Accounts are born, change, and die | Yes |
| 15 | Testing, staging, launch runbook, rollback | Proves the whole route end-to-end | No |

---

## Move 1 — Decide the tenancy & identity model

**Build:** A written decision (not code) on how a "client" maps to data.

Answer these before touching the schema:
- Is a client a **single user**, or an **organization with multiple users** (e.g., owner + their team)? This is irreversible-expensive later. Default recommendation: **organization-based** even if most clients are one person today.
- Can one human belong to **multiple client orgs** (agencies, parent companies)? If yes, identity ≠ membership — you need a join table from day one.
- Do staff and clients share one `auth.users` pool with a role flag, or two separate auth surfaces? Recommendation: **one Supabase auth pool, role-based separation** via a `profiles.role` / membership tables, so staff can be impersonated and audited cleanly.
- What is the **canonical link** between a client org and existing CRM records (the projects table you already have)?

> **Easy to forget**
> - Multi-org membership. Retrofitting it after launch means a data migration and an RLS rewrite.
> - The "internal staff who is also testing as a client" case — decide now whether that's impersonation (move 10) or a real client account.
> - Soft-delete vs hard-delete semantics for an org (move 14 depends on this).

**DoD:** A one-page decision doc committed to the repo describing org↔user↔project relationships, with the chosen cardinalities drawn out. No ambiguity remains about "who can see what."

**Unblocks:** Move 2.

---

## Move 2 — Data model + the RLS contract

**Build:** Schema migrations + Row Level Security policies. In Supabase, **RLS is the portal's actual security boundary** — the React app is just a convenience layer over it.

Tables (minimum):
- `organizations` (client orgs) — with `status` (active/suspended/archived).
- `memberships` (user_id, org_id, role) — the access join table.
- `projects` — add `org_id` FK if not present; this is what scopes visibility.
- `message_threads` (org_id, project_id nullable, subject, created_by).
- `messages` (thread_id, author_id, body, created_at, edited_at, deleted_at).
- `message_reads` (message_id/thread_id, user_id, read_at) — for unread counts.
- `attachments` (owner table ref, storage_path, filename, mime, size, uploaded_by).
- `invitations` (email, org_id, role, token_hash, expires_at, accepted_at).
- `audit_events` (actor, action, target, metadata, created_at).
- `notifications` (user_id, type, payload, read_at).

RLS policy contract — write these as the spec *before* the SQL:
- A client user can `SELECT` a project **only if** a membership row links them to that project's `org_id`.
- A client can `INSERT` a message **only into threads belonging to an org they're a member of**.
- A client can **never** see another org's rows (default-deny; every table starts `ENABLE ROW LEVEL SECURITY` with no permissive policy until written).
- Staff role bypasses via a separate policy keyed on `profiles.role = 'staff'`, ideally through a `SECURITY DEFINER` helper function, not scattered `OR` clauses.

> **Easy to forget**
> - **Default-deny on every new table.** Enabling RLS without a policy locks everyone out (good); adding a table later *without* enabling RLS silently exposes everything (bad). Add a CI check that fails if any table lacks RLS.
> - **The `storage.objects` bucket also needs RLS policies** — file access is a separate policy surface from table rows. Forgetting this is the classic "client downloads another client's file via the public URL" leak.
> - **Service-role key bypasses ALL RLS.** Any server route using the service-role key is outside the security model — inventory these and treat each as a privileged endpoint.
> - **`message_reads` / unread counts** — trivial to omit, and then the UI can't show "3 unread," which is the first thing clients notice is missing.
> - **Indexes on `org_id`, `thread_id`, `created_at`** — RLS predicates run on every query; without these the portal gets slow exactly as it succeeds.

**DoD:** Migrations apply cleanly to a fresh DB; an automated test logs in as Client A and *fails* to read Client B's project, thread, and file. Generated TypeScript types regenerated.

**Unblocks:** Everything. This is the spine.

---

## Move 3 — Auth: invite, login, session, recovery

**Build:** The client authentication surface. Clients don't sign themselves up — they're **invited**.

- Invite flow: staff creates an `invitations` row → email with a single-use, time-limited, hashed token → client sets password / uses magic link → membership created → invitation marked accepted.
- Login: email+password and/or magic link. Decide one as primary.
- Session: Supabase Auth cookies via the SSR helpers; middleware refreshes the session on every request.
- Password reset, email change, and **token expiry/resend** flows.

> **Easy to forget**
> - **Invite token reuse and expiry.** Tokens must be single-use, hashed at rest, and expire. An un-expiring invite link is a permanent backdoor.
> - **What happens when an invited email already has an account** (existing staff member, or invited to a second org). Don't create a duplicate user.
> - **Email verification state** vs portal access — can an unverified client see data?
> - **Session edge cases:** logout everywhere, session after password reset, the Next.js middleware token-refresh dance (this is the #1 Supabase+App Router footgun).
> - **Rate limiting on login + invite-accept** to stop credential stuffing and token brute force.
> - **Lockout / suspended org** — a valid login into a suspended org must be denied gracefully, not 500.

**DoD:** A new client receives an invite, sets a password, logs in, gets logged out, resets the password, and logs back in — all on staging, with expired/reused tokens correctly rejected.

**Unblocks:** Moves 4–9.

---

## Move 4 — Authorization layer (the second wall)

**Build:** Route-level and data-level guards in the Next.js app. Login proves *identity*; this proves *permission*. RLS (move 2) is the database wall; this is the application wall — you want both (defense in depth).

- A server-side guard that resolves the current user → their memberships → allowed org(s) on every portal request.
- Route protection in middleware for `/portal/*`.
- A single `getAuthorizedOrg()` / `requireMembership(projectId)` helper used by every loader and server action — never re-implement the check inline.
- Explicit handling of the **multi-org switcher** (if move 1 said multi-org): which org is "active" lives in a deliberate place (URL segment recommended over cookie, so it's shareable and unambiguous).

> **Easy to forget**
> - **Server actions and route handlers re-check auth.** RLS protects the DB, but an API route that uses the service-role key bypasses RLS — those routes MUST manually authorize.
> - **IDOR on every parameterized route** (`/portal/projects/[id]`): never trust the ID in the URL; always verify membership server-side.
> - **The "no orgs yet" / "removed from all orgs" state** — a logged-in user with zero memberships needs a real screen, not a crash.
> - **404 vs 403:** leaking existence of another client's project via a 403 is itself an info leak; return 404 for things the user isn't allowed to know exist.

**DoD:** Manual IDOR test on every dynamic route returns 404 for unauthorized IDs; a user removed from their last org is routed to a clean "no access" screen.

**Unblocks:** Safe rendering of all features.

---

## Move 5 — Portal shell: layout, navigation, states

**Build:** The frame every feature renders into, separate from the staff app.

- `/portal` layout: header (org name, user menu, org switcher if multi-org), sidebar/nav (Projects, Messages, Files), responsive/mobile.
- **The four states for every data view**, designed up front: loading (skeletons), empty, error, and populated. Most "missing something" complaints are actually missing empty/error states.
- Branding: client-facing pages should feel like Unite-Hub's product, distinct from the internal CRM chrome.

> **Easy to forget**
> - **Empty states** ("No projects yet," "No messages — start a conversation"). These are the first thing a brand-new client sees, and a blank screen reads as "broken."
> - **Error boundaries** so one failed widget doesn't white-screen the whole portal.
> - **Mobile.** Clients check status from their phone far more than staff do. The portal is mobile-first in a way the internal CRM may not be.
> - **Accessibility basics** (focus order, labels, contrast) — cheap now, a lawsuit-shaped retrofit later for a client-facing surface.
> - **Loading skeletons / suspense boundaries** so the App Router streaming doesn't show layout jank.

**DoD:** Navigate the empty portal on desktop and mobile; every nav destination shows a deliberate empty state and survives a forced data error without white-screening.

**Unblocks:** Moves 6–9 render into a finished frame.

---

## Move 6 — Projects: list + detail (read-only first)

**Build:** The first real client-visible feature.

- Project list scoped to the active org (RLS + authorization already guarantee scope).
- Project detail: status, timeline/milestones, key dates, the team contact, whatever the CRM already tracks that's safe to expose.
- **A field-level allow-list:** the CRM project record contains internal notes, margins, internal assignees. Decide explicitly which fields are client-visible. Default-hide; opt-in to show.

> **Easy to forget**
> - **Internal fields leaking through.** The single most common client-portal incident: exposing the whole project row instead of a curated DTO. Build a `toClientProject()` mapper and never return the raw row.
> - **Status vocabulary mismatch** — internal statuses ("blocked on AR," "ghosting client") must map to client-safe labels.
> - **Stale/cached data** — if a staff member updates a project, how fast does the client see it? Decide and state the freshness contract.
> - **Pagination / large project lists** for your biggest clients.

**DoD:** A client sees only their org's projects, only the allow-listed fields, with correct labels; an internal-only field is provably absent from the API response.

**Unblocks:** Messaging can attach to a project (move 7).

---

## Move 7 — Messaging: threads, send, read state

**Build:** Two-way messaging between client and team.

- Thread model: a thread belongs to an org, optionally scoped to a project.
- Compose, send, display (with author, timestamp).
- Edit/delete windows (decide policy — usually soft-delete, "message removed").
- Unread/read state per user (the `message_reads` table from move 2).

> **Easy to forget**
> - **Who is "us"?** A client message must route to the right staff member(s). Define the assignment/inbox model now (per-project owner? shared team inbox? both?). This is half the messaging feature and is usually forgotten until clients say "nobody replied."
> - **Read receipts and unread counts** — required for the nav badge clients expect.
> - **Input sanitization / XSS** — client-authored content rendered to staff (and vice versa) must be escaped/sanitized. Treat all message bodies as hostile.
> - **Empty thread, optimistic send + failure rollback, ordering under concurrency.**
> - **Length limits, basic spam/flood protection.**
> - **Notification hooks** — every send must enqueue a notification (move 8), or the other side never knows.

**DoD:** Client and staff exchange messages on staging; unread counts update; a removed message shows correctly; a `<script>` in a message body renders inert.

**Unblocks:** Move 8 (delivery), move 10 (staff replies).

---

## Move 8 — Realtime + notifications (in-app + email)

**Build:** Make messaging feel alive and ensure nobody misses anything.

- Realtime: Supabase Realtime subscriptions so new messages appear without refresh (respecting RLS on the channel).
- In-app notifications: the `notifications` table + a bell/badge.
- **Email notifications** for new messages and key events, with sensible batching/digest to avoid spamming.
- Per-user notification preferences (at minimum on/off for email).

> **Easy to forget**
> - **Realtime must respect RLS** — a naive channel subscription can broadcast another org's messages. Verify the realtime authorization explicitly.
> - **Notification preferences + unsubscribe** — legally required for email; clients will mute you if you over-send.
> - **The "notify the right staff" routing** (depends on move 7's assignment model).
> - **Idempotency / dedupe** — don't send three emails because of three reconnects.
> - **Offline / missed-while-away** — in-app notification must persist so a client who was offline still sees it.
> - **Reconnection handling** — Realtime/SSE drops constantly through proxies; poll the table as source of truth, treat realtime as an accelerant, not the truth.

**DoD:** A message sent by staff appears in the client's open tab within seconds, increments the bell, and (if enabled) generates exactly one email; a muted user gets the in-app notification but no email.

**Unblocks:** A usable, trustworthy messaging product.

---

## Move 9 — File sharing / attachments

**Build:** Clients will ask for this on day one regardless of scope.

- Supabase Storage buckets with **RLS policies on `storage.objects`** scoped by org/project (this is a *separate* policy surface from table RLS).
- Upload (with size/type limits), download via short-lived signed URLs (never public URLs for client data), list, delete.
- Attach files to messages and/or projects.

> **Easy to forget**
> - **Signed URLs, never public buckets.** The classic leak is a guessable/public storage URL bypassing all auth.
> - **File-type allow-list + size caps + malware consideration.** An uploaded HTML/SVG file can be an XSS vector if served inline; force download or sanitize.
> - **Storage RLS** — table RLS does not cover the bucket.
> - **Orphaned files** when a message/project/org is deleted (move 14 cleanup).
> - **Virus scanning** if clients upload arbitrary files staff will open.
> - **Quotas / cost** — storage is a real bill at scale.

**DoD:** Client A uploads a file, downloads it via a signed URL that expires; Client B cannot reach Client A's file by any URL; a disallowed file type is rejected.

**Unblocks:** Feature-complete client surface.

---

## Move 10 — Staff-side admin (the other half of the build)

**Build:** The portal is two-sided. Everything clients see needs a staff counterpart, and this is routinely under-scoped to half its real size.

- Staff view of all client threads / a shared inbox, with assignment and reply.
- Staff manage memberships: invite, remove, change roles, suspend an org.
- **Impersonation / "view as client"** so support can reproduce what a client sees — fully audited (move 11).
- Control which projects/fields are exposed per client.

> **Easy to forget**
> - **Staff reply path** — clients can message in, but if staff have no good inbox, messages rot. This is a feature, not an afterthought.
> - **Impersonation auditing** — "staff X viewed as client Y" must be logged; impersonation without audit is a compliance failure.
> - **Bulk/edge admin actions:** removing the last member of an org, re-inviting, transferring ownership.
> - **Internal-only annotations** on client threads (staff notes the client can't see) — clearly separated to avoid accidental exposure.

**DoD:** A staff member receives, assigns, and replies to a client thread; impersonates a client (logged); suspends an org and confirms the client is denied access.

**Unblocks:** Operability — the portal can actually be run by your team.

---

## Move 11 — Audit log, observability, error tracking

**Build:** The ability to see what's happening and prove what happened.

- `audit_events` writes on security-relevant actions: login, invite, accept, role change, impersonation, file download, message delete, org suspend.
- Error tracking (Sentry or equivalent) wired to both client and server, with PII scrubbing.
- Basic metrics/dashboards: active clients, messages/day, failed logins, email delivery.
- Structured server logs.

> **Easy to forget**
> - **Audit the privileged actions specifically** — impersonation, role changes, data exports. Auditing only logins misses the dangerous stuff.
> - **PII scrubbing in error reports** — client names/emails in Sentry breadcrumbs is a privacy incident.
> - **Email deliverability monitoring** — you need to know invites/notifications are landing, not silently bouncing (ties to move 13).
> - **Alerting thresholds** — a spike in failed logins or 403s should page someone.

**DoD:** Each privileged action produces an audit row; a thrown error reaches the tracker with PII redacted; a deliberately bounced email is visible in monitoring.

**Unblocks:** Move 12 and safe operation.

---

## Move 12 — Security hardening + privacy/compliance

**Build:** Treat client data as legal exposure, because it is.

- Penetration-style pass: IDOR sweep, RLS bypass attempts, storage URL leaks, auth edge cases, rate-limit verification.
- `detect-secrets` scan; rotate anything exposed; confirm service-role key is server-only and never shipped to the client bundle.
- Security headers (CSP, HSTS, etc.), CSRF protection on mutations, secure cookie flags.
- Privacy: privacy policy + terms surfaced to clients, data-processing basis, **data export and deletion (DSAR / GDPR "right to be forgotten")** paths.
- Data retention policy for messages/files.

> **Easy to forget**
> - **Service-role key in the client bundle** — grep the build output; this single mistake voids the entire RLS model.
> - **Data export & deletion requests** — clients (or regulators) will ask; building this reactively under a 30-day legal clock is miserable.
> - **CSP that actually allows Supabase/Storage/Realtime origins** — too strict breaks the app, too loose invites XSS.
> - **Cookie flags** (HttpOnly, Secure, SameSite) on the session.
> - **Retention/auto-purge** — messages and files don't live forever; decide and automate.
> - **Consent + ToS acceptance recorded** at first login.

**DoD:** Secret scan clean; IDOR/RLS test suite green; client bundle proven free of service-role key; a data-export and a data-deletion request both demonstrably work on staging.

**Unblocks:** Legal/ethical readiness to onboard real clients.

---

## Move 13 — Email / domain / transactional infra + deliverability

**Build:** Invites and notifications are worthless if they land in spam. This is infrastructure, separated out because it's perennially forgotten until "the client never got the invite."

- Transactional email provider configured (Resend/Postmark/SES), separate from marketing mail.
- **SPF, DKIM, DMARC** on the sending domain.
- Branded, tested email templates: invite, password reset, new-message notification, digest.
- From-address, reply-to, and bounce handling.
- Local/staging email capture so you don't email real people during dev.

> **Easy to forget**
> - **SPF/DKIM/DMARC** — without these, invites silently spam-folder and you'll blame the app for weeks.
> - **A warmed-up sending domain/subdomain** distinct from your primary so portal mail can't tank your corporate deliverability.
> - **Reply-to routing** — if a client hits "reply" on a notification email, where does it go?
> - **Staging must not email real clients** — a sandbox/allow-list is mandatory.
> - **Localized/timezone-correct timestamps** in emails.

**DoD:** An invite and a notification email pass a deliverability check (inbox, not spam) with DKIM/DMARC aligned; staging emails are captured, not sent to real addresses.

**Unblocks:** Moves 3 and 8 actually function in the real world.

---

## Move 14 — Account lifecycle: onboarding, offboarding, billing hooks

**Build:** Accounts are born, change, and die. Each transition is a feature.

- Onboarding: first-login welcome, guided empty states, initial data population.
- Org/membership changes: add/remove users, role changes, ownership transfer.
- Offboarding: suspend, archive, and hard-delete an org — including cascading cleanup of messages, files, and notifications.
- Billing/plan hooks if the portal is gated by subscription status (suspend access on non-payment, etc.).
- Re-invite / reactivation.

> **Easy to forget**
> - **Cascade deletes / orphan cleanup** — deleting an org must remove its files from Storage, its messages, its notifications. Orphaned storage objects are a cost and privacy leak.
> - **Suspended/archived vs deleted** as distinct states (ties back to move 1).
> - **"Last admin removed"** guardrails so an org can't be locked out of itself.
> - **Reactivation** of a previously suspended/archived org without data loss.
> - **Billing-status → access** coupling if relevant — and the grace-period behavior.

**DoD:** Create, suspend, reactivate, and hard-delete an org on staging; confirm hard-delete leaves zero orphaned rows or storage objects and that the client is cleanly denied during suspension.

**Unblocks:** A portal that survives real-world account churn.

---

## Move 15 — Testing, staging, launch runbook, rollback

**Build:** Prove the whole route end-to-end before real clients touch it.

- Automated tests: unit (mappers/guards), integration (RLS cross-tenant denial), E2E (invite → login → view project → message → upload → notification).
- A **multi-tenant isolation test** as a permanent CI gate: Client A must never read/touch Client B's anything.
- Staging environment mirroring prod (separate Supabase project, separate email sandbox).
- Migration strategy: forward-only, reversible where possible, tested on a prod-shaped DB.
- Launch runbook: pre-launch checklist, smoke test, feature flag / gradual rollout (one friendly client first), monitoring watch.
- **Rollback plan** for both code and schema.

> **Easy to forget**
> - **The cross-tenant isolation test as a blocking CI gate** — this is the one test that, if green forever, lets you sleep.
> - **Seed/fixture data for staging** that mirrors a realistic multi-org setup.
> - **Migration rollback** — schema changes are the hardest thing to undo; rehearse it.
> - **A canary client** — launch to one tolerant client before all of them.
> - **Smoke test on prod post-deploy** (login + read + send) so a bad deploy is caught in minutes, not by a client email.
> - **Backups verified restorable** — having backups ≠ being able to restore them.

**DoD:** Full E2E suite green in CI including cross-tenant denial; staging mirrors prod; a documented, rehearsed rollback; a green smoke test against the deployed environment.

**Unblocks:** Launch.

---

## The "easy to forget" master checklist (consolidated)

Pulled out so it can be skimmed during build review. If the build feels "missing something," it's almost always one of these:

**Security & isolation**
- [ ] RLS enabled + default-deny on *every* table, with a CI check
- [ ] RLS policies on `storage.objects`, not just tables
- [ ] Service-role key is server-only; proven absent from client bundle
- [ ] Every parameterized route re-checks membership (no IDOR); 404 not 403 for unknown-existence
- [ ] Cross-tenant isolation test as a permanent CI gate
- [ ] Message bodies sanitized (XSS) both directions
- [ ] Signed, expiring URLs for files; no public buckets
- [ ] Rate limiting on login, invite-accept, message send

**Identity & lifecycle**
- [ ] Multi-org membership modeled from day one (if applicable)
- [ ] Invite tokens single-use, hashed, expiring
- [ ] Existing-email-invited case handled (no duplicate users)
- [ ] Suspended/archived/deleted org states distinct and enforced
- [ ] "Last admin removed" guardrail
- [ ] Cascade delete cleans messages, files, notifications (no orphans)

**The half-features people skip**
- [ ] Unread counts / read state (`message_reads`)
- [ ] Staff inbox + assignment + reply path ("who is 'us'?")
- [ ] Impersonation, fully audited
- [ ] Empty / loading / error states for every view
- [ ] Mobile + accessibility for the client surface
- [ ] Client-field allow-list (no internal data leaking through)

**Delivery & operations**
- [ ] SPF/DKIM/DMARC + warmed sending domain
- [ ] Notification preferences + unsubscribe
- [ ] Realtime respects RLS; poll as source of truth, realtime as accelerant
- [ ] Email idempotency (no duplicate sends on reconnect)
- [ ] Audit log on privileged actions (impersonation, role changes, exports)
- [ ] PII scrubbed from error tracking
- [ ] Staging never emails real clients

**Compliance & resilience**
- [ ] Data export + deletion (DSAR/GDPR) paths
- [ ] Retention/auto-purge policy
- [ ] ToS/consent acceptance recorded
- [ ] CSP allows Supabase/Storage/Realtime origins
- [ ] Migration rollback rehearsed
- [ ] Backups verified restorable
- [ ] Canary client + prod smoke test post-deploy

---

## Suggested build order vs. demo order (the key insight)

The temptation is to build login → project list → messaging (moves 3, 6, 7) and demo it. That demo will look done and **be missing**: tenant isolation tests (15), storage RLS (9), staff reply path (10), email deliverability (13), and data deletion (12). Those are exactly the "missing something" gaps.

**Recommended sequencing:**
1. Foundation first: moves 1–2 fully before any UI. The schema and RLS contract are the product.
2. Build the security gates (move 4 + the cross-tenant test from move 15) *alongside* the first feature, not after.
3. Build each client feature (6–9) with its staff counterpart (10) and its delivery (8/13) as one unit — not "all client features, then go back for staff/email."
4. Treat moves 11–14 as launch-blocking, not post-launch polish. They are why portals get pulled after a leak.

This way "done" and "shippable" are the same milestone, and the surprises are surfaced on move 1, not in production.
