# Command centre consolidation — discovery and cutover plan

**Date:** 2026-08-01 · **Status:** DISCOVERY ONLY. Nothing executed. No live system changed.
**Brief:** retire the standalone command centre, point its public domain at the Pi-Dev-Ops one.

---

## Headline: the brief's premise does not survive discovery

`unite-group.in` is **not a standalone command centre.** It serves `apps/web` from the Unite-Group repo — a **58-page, 280-API-route platform** of which the command centre is **9 pages**.

Pointing that domain at the Pi-Dev-Ops dashboard would not consolidate two command centres. It would take down 49 pages of unrelated platform — auth, billing, CRM, campaigns, contacts, bookkeeper, approvals — to replace 9 command-centre pages with a 36-route dashboard that shares **11 of 134 environment variables** with it.

**Recommendation: do not do the cutover as briefed.** A defensible version of the goal exists and is at the end of this document.

---

## Phase 1 — Both ends, mapped

### The domain question: you own one of them, and they are different sites

| | `unite-group.in` | `unite-group.ink` |
|---|---|---|
| DNS (via 8.8.8.8) | `76.76.21.21` — Vercel | `216.150.16.65` — Vercel |
| Nameservers | `ns1/ns2.vercel-dns.com` | `ns1/ns2.vercel-dns.com` |
| Apex HTTP | **200**, redirects `/auth/login?redirectTo=%2F` | **404** — apex unassigned |
| Assigned subdomain | `www` → apex | `live.` → `live-nexus` project |
| Page title | **"Unite-Group Nexus"** (contains "command centre") | `live.` → "Unite Group Nexus — **Live Meeting Notes**" |
| In your Vercel domain registry | **NO** | **YES** — Vercel registrar, expires 2027-03-04 |
| Attached to a project you control | **YES** — `unite-group` project | `live.` only |

**Authoritative production domain for the command centre: `unite-group.in`.**

Reconciling the earlier finding: my 2026-08-01 production pull listed `unite-group.ink` and not `.in`, because it read the **Vercel domain registry**, and `.in` is not in it. Both domains are real, both are live, and **they serve different applications**. The earlier list was not wrong — it was answering a narrower question than this brief asks.

**The ownership split, stated plainly.** `vercel domains inspect unite-group.in --scope unite-group` returns:

> `Error: You don't have access to the domain unite-group.in under unite-group.`

Yet `get_project unite-group` lists `unite-group.in` in its `domains` array. So: **you control the Vercel project that serves `.in`, but the domain object itself sits outside your Vercel account** — registered at a third-party registrar, or in another Vercel account, with NS delegated to Vercel. You own `.ink` outright.

**Consequence for Phase 3: the DNS/domain step cannot be performed from this Vercel account at all.** It is blocked on access, not merely on a gate.

### The two applications

| | Standalone (`unite-group.in`) | Pi-Dev-Ops |
|---|---|---|
| Vercel project | `unite-group` (`prj_IfUuJNLjXTE8VXqEGwLAleIGhiA0`) | `pi-dev-ops` (`prj_I5sYqNTlL51DlvyzSFjiHX6FrLAX`) |
| Repo / root dir | Unite-Group → `apps/web` | Pi-Dev-Ops → `dashboard` |
| Public URL | `unite-group.in` (auth-gated) | `pi-dev-ops.vercel.app` — **no custom domain** |
| Title | "Unite-Group Nexus" | "Pi CEO — Autonomous Dev Platform" |
| Pages / API routes | 58 / 280 | 36 total / 21 |
| Latest deployment target | **`null` — a preview, not production** | `production` |
| Framework / Node | Next.js / 22.x | Next.js / 24.x |

⚠️ **`unite-group`'s latest deployment has `target: null`.** The production alias is being served by an older deployment than the newest build. Worth understanding before any cutover — it suggests production promotion is not happening on merge.

---

## Phase 2 — What exists only on the one we would retire

### Environment: 123 of 134 variables exist only on the standalone

**11 shared. 123 unique to `apps/web`. 18 unique to `dashboard`.**

Answering your specific watch-item — **yes, it holds secrets and a database the Pi-Dev-Ops version does not:**

| Category | A-only variables | Verdict |
|---|---|---|
| **Payments** | `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` | **MUST MIGRATE FIRST** — live billing. Dropping this stops revenue collection and breaks webhook reconciliation. |
| **Accounting** | `XERO_CLIENT_SECRET` | **MUST MIGRATE FIRST** — books integration |
| **Direct database** | `DATABASE_URL`, `DB_POOL_SIZE`, `DB_POOLER_MODE`, `ENABLE_DB_POOLER`, `DB_IDLE_TIMEOUT`, `DB_MAX_LIFETIME` | **MUST MIGRATE FIRST** — a direct Postgres connection with pooling config. The dashboard has no equivalent and reaches Supabase only via the JS client. |
| **Identity / OAuth** | `GOOGLE_CLIENT_SECRET`, `MICROSOFT_CLIENT_SECRET`, `LINKEDIN_CLIENT_SECRET`, `TIKTOK_CLIENT_SECRET`, `REDDIT_CLIENT_SECRET`, `DR_CLIENT_SECRET`, `FACEBOOK_APP_ID` | **MUST MIGRATE FIRST** — every social/SSO login breaks |
| **Email** | `SENDGRID_API_KEY`, `DEFAULT_FROM` | **MUST MIGRATE FIRST** — transactional email stops |
| **Model / AI vendors** | `OPENAI_API_KEY`, `GEMINI_API_KEY`, `PERPLEXITY_API_KEY`, `HEYGEN_API_KEY`, `ELEVENLABS_API_KEY`, `HF_API_TOKEN`, `ANTHROPIC_AUTH_TOKEN`, `CLAUDE_CODE_OAUTH_TOKEN` | **MUST MIGRATE** if the corresponding features move |
| **Media / scraping** | `CLOUDINARY_*` (4), `APIFY_API_KEY`, `APIFY_API_TOKEN` | **MUST MIGRATE** if media/ingest features move |
| **CRM / ops flags** | `CRM_AUTO_EXECUTE`, `CRM_DISPATCH_ARMED`, `COST_METERING_ENABLED`, `CFO_GATE_REVIEW*`, `CC_LINEAR_LIVE` | **MUST MIGRATE FIRST** — these arm live automation; silently losing them changes behaviour rather than breaking it, which is worse |
| **E2E / test** | `E2E_*` (5), `TEST_OAUTH_VAR_A/B`, `PLAYWRIGHT_TEST_PASSWORD`, `CI` | **SAFE TO DROP** — test-harness only |
| **Evidence flags** | `*_APPEND_EVIDENCE` (4), `CREDENTIAL_SEED_ENABLED` | **SAFE TO DROP** — build-time evidence toggles |

⚠️ `E2E_SUPABASE_SERVICE_ROLE_KEY` is a service-role key present in the app's env surface. Safe to drop *as a variable*, but it should be **rotated**, not merely abandoned.

### Data sources — they overlap, but not completely

| App | Supabase projects referenced |
|---|---|
| `apps/web` | `lksfwktwtmyznckodsau` (Unite-Group prod) · **`xgqwfwqumliuguzhshwv`** |
| `dashboard` | `lksfwktwtmyznckodsau` (Unite-Group prod) · `zbryrmxmgfmslqzizsto` (Pi CEO) |

**Good news:** both already read the same primary database, `lksfwktwtmyznckodsau`. A shared substrate exists.

⚠️ **`xgqwfwqumliuguzhshwv` is not one of the 10 Supabase projects in your account** (pulled 2026-08-01). It appears in `src/lib/operator-gateway/jobs.ts` and its test. Either a dead reference, or a project on an account this session cannot see. **Unresolved — must be identified before any cutover**, because if it is live, the operator gateway depends on a database nobody has inventoried.

### Feature surface only on the standalone

Route groups under `(founder)/founder` — 50 pages, of which only 9 are command-centre:

`advisory` · `agents` · `analytics` · `approvals` · `boardroom` · `bookkeeper` · `brand-video` · `calendar` · `campaigns` (+ new, [id]) · `chat` · `contacts` · … plus `(auth)` login / reset / forgot-password, `docs`, `terms-of-service`, `privacy-policy`, `(preview)`.

**Command-centre pages (the only genuinely overlapping surface):** `command-centre` · `/hermes-control-panel` · `/knowledge` · `/operations` · `/operator-gateway` · `/portfolio` · `/providers` · `/studio` · `/wiki-graph`.

**Everything outside those 9 is MUST MIGRATE FIRST or DO NOT RETIRE.** The auth pages alone are load-bearing: `unite-group.in` redirects to `/auth/login`, so the domain *is* the front door to the platform's authentication.

---

## Phase 3 — Cutover plan (NOT EXECUTED)

### Gate summary — every step touching production or DNS

| # | Step | Gate |
|---|---|---|
| G1 | Identify who holds the `unite-group.in` domain record | **BLOCKED — founder access required.** Not performable from this Vercel account. |
| G2 | Identify or retire `xgqwfwqumliuguzhshwv` | **GATE** — unknown production database |
| G3 | Copy 123 env vars into the target project | **GATE** — secrets |
| G4 | Rotate `E2E_SUPABASE_SERVICE_ROLE_KEY` and any exposed key | **GATE** — credentials |
| G5 | Attach `unite-group.in` to the `pi-dev-ops` project | **GATE** — DNS / production |
| G6 | Detach from `unite-group` project | **GATE** — production |
| G7 | Promote a production deployment on `pi-dev-ops` | **GATE** — production |
| G8 | Decommission the `unite-group` project | **GATE** — irreversible |

**Every step in the cutover is gated. There is no un-gated portion.** That is itself a signal about the shape of this change.

### If the cutover proceeds as briefed — steps and rollback

1. **G1** — establish domain control. Without this nothing else can run.
2. **G3** — replicate all 123 env vars into `pi-dev-ops`. *Rollback: none needed; additive.*
3. Build parity: the Pi-Dev-Ops dashboard must implement the 49 non-command-centre pages, or those features are lost. **This is a rewrite, not a cutover.**
4. **G7** — promote `pi-dev-ops` to production and verify against the auth flow.
5. **G5/G6** — move the domain. *Rollback: re-attach `unite-group.in` to the `unite-group` project; DNS is unchanged because both are Vercel-fronted, so propagation is seconds, not hours.*
6. Soak for one full scheduled cycle before **G8**. *Rollback after G8: none — decommission is irreversible.*

**Rollback summary:** steps 1–5 are reversible in minutes because the nameservers do not change — only the project attachment does. **Step 6 (G8) is the point of no return.** Do not perform it in the same session as the cutover.

### The recommendation I actually stand behind

The briefed goal — one command centre — is right. The briefed mechanism is wrong, because it treats a 58-page platform as if it were a 9-page app.

**Do this instead, in order:**

1. **Do not move `unite-group.in`.** It is the platform's front door and its auth entry point.
2. **Consolidate the command centre only.** Decide which of the two command-centre implementations wins on its merits — the Pi-Dev-Ops dashboard is newer, on Node 24, and actually deploying to production, which the `unite-group` project is not.
3. **If Pi-Dev-Ops wins**, give it a subdomain of the domain you actually own — e.g. `cc.unite-group.ink` — and retire the 9 command-centre pages from `apps/web`, redirecting them. Zero domain-ownership risk, zero platform downtime, fully reversible.
4. **Revisit `unite-group.in` only if** the Pi-Dev-Ops dashboard ever reaches feature parity with all 58 pages. On current evidence that is a rewrite, and should be scoped as one.

Step 3 achieves "one command centre" without betting the platform on a domain you may not own.

### Open questions blocking a decision

1. **Who holds the `unite-group.in` registration?** Determines whether the briefed cutover is possible at all.
2. **What is `xgqwfwqumliuguzhshwv`?** An uninventoried database referenced by the operator gateway.
3. **Why is `unite-group`'s latest deployment `target: null`?** Production may not be promoting on merge.
4. **Which command-centre implementation wins?** Not answerable from route counts alone — needs a feature comparison of the 9 overlapping pages.

---

## Confirmation: nothing was changed

This discovery used only read operations: DNS lookups, HTTP `GET`/`HEAD`, `vercel ls` / `inspect` / `domains inspect`, `gh api` reads, Vercel MCP `get_project`, and local `grep`/`find`. No writes, no deploys, no DNS edits, no env changes, no domain attach or detach.

Environment variables were compared **by name only**. No value was read, printed, or stored.

Fence remains in **shadow**. No `HARD_STOP`. No denials seeded.
