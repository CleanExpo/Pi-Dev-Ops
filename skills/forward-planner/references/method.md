# forward-planner — the method, expanded

This expands the eight-step method in SKILL.md. Read it when a plan is large, heavily contingent, or when the spine keeps coming out as vague phases instead of verifiable moves.

## Table of contents

1. The mindset shift: breakdown vs. foresight
2. Step-by-step, expanded
3. The branching discipline (how to not explode the tree)
4. The red-team pass in detail
5. A short worked example

---

## 1. The mindset shift: breakdown vs. foresight

Decomposition is *downward*: take a brief, split it into its parts. It can only ever produce what the brief already contains. Foresight is *forward and backward*: fix a destination, locate the present, and reason about the whole route — including the parts no one wrote down.

The tell that you've slipped back into mere decomposition: your moves are nouns from the brief ("the API", "the dashboard") rather than transitions toward a named end-state ("expose `/sessions` returning 200 with auth, verified by integration test"). When you catch that, return to the win condition and ask what it *requires*, not what the brief *mentions*.

## 2. Step-by-step, expanded

**Win condition.** Write 5–15 conditions, each independently checkable. Prefer conditions a machine could one day verify: "route X returns 2xx", "table Y has columns A, B", "test suite Z passes", "Stripe webhook registered and signature-verified". Vague conditions ("good UX") are fine to list but mark them as `human_judged` so they aren't mistaken for automated gates.

**Read the board.** Spend real effort here; a plan built on a misread board is wasted. Internally, prefer reading the actual files over assuming. Externally, search for what's changed recently in the relevant tech and what mature implementations include (this is often where you discover required-but-unobvious moves like rate limiting, idempotency keys, audit logging).

**Compute the gap.** Literally list win-condition items and mark each present / partial / absent against the board. The absent and partial items are your plan's raw material. Doing this as an explicit table prevents the "I assumed it was there" class of miss.

**Lay the spine.** Topologically order the gap by dependency. Aim for 15+ moves; if you have fewer, you're probably bundling several deliverables into one move — split them. If you have far more than ~25, you may be planning at too fine a grain; group trivially-coupled steps. Each move needs a one-line *deliverable* and a one-line *verify*.

**Look ahead.** For each move, jot its `unlocks` and `requires`. The `requires` that aren't already earlier in the spine are *discovered prerequisites* — insert them before the move that needs them. This reordering loop is the heart of "15 moves ahead": you're propagating consequences backward into the sequence until it's internally consistent.

**Branch points.** See section 3.

**Red-team.** See section 4.

**Emit.** Brief first (it's your reasoning trace), then the structured plan (derived from the brief). Validate the plan.

## 3. The branching discipline

A branch point is a move whose *outcome* changes what should happen next. Three honest sources of branching:

- **Test/result-contingent**: "if load test passes at target → ship; if not → add caching layer first."
- **Decision-contingent**: "if Phill approves managed auth → integrate provider; if self-hosted → build session service."
- **External-contingent**: "if upstream API ships v2 by milestone → adopt it; else → wrap v1."

Rules that keep the tree sane:

1. **Default to spine.** Most moves have one sensible next move. Only fork when you can name two outcomes that genuinely lead to *different* move sequences.
2. **Re-converge.** After a branch, point both arms back at a common downstream move where possible. Branches that never re-merge double the plan's size for little gain.
3. **Bound the depth.** Avoid branches inside branches inside branches. If you're three forks deep, you're guessing, not planning — collapse the speculative depth into a single "re-plan here" move that re-runs forward-planner when the outcome is known.
4. **Name the decider.** Every branch records *who or what* resolves it (a test, a person, an event) so the loop knows what to wait for.

## 4. The red-team pass in detail

Stand at the end of the spine and assume the project is "done." Now try to prove it isn't. Run this checklist against the win condition — these are the categories this system most often drops silently:

- **Auth & authz**: who can call this, and is that enforced and tested?
- **Data lifecycle**: migrations, backfills, seed data, deletion/retention.
- **Failure states**: timeouts, retries, partial failure, idempotency, rollback.
- **Observability**: can you tell, in production, whether it actually worked? (Silent success is indistinguishable from silent failure.)
- **Boundaries**: the integration or hand-off that no single move "owned".
- **Docs & runbook**: can a human operate and recover this without you?
- **Verification gap**: is each win condition *actually* checked by a move, or just assumed?

Anything this surfaces is a real move you were about to miss. Insert it into the spine now and re-check dependencies. The discipline is to do this *while planning*, when fixing the gap is a line of text — not after building, when it's a re-architecture.

## 5. A short worked example

*Goal (as briefed):* "Add a client portal login to Unite-Hub."

*Naive decomposition* would yield: build login page, add auth API, connect to DB. Three tasks. It would report "done" — and then password reset, session expiry, and rate limiting would surface as "missing somethings."

*Forward-planner* instead:

- **Win condition** (excerpt): users can register, log in, log out, reset password; sessions expire and refresh; auth endpoints are rate-limited; all of the above covered by integration tests; audit log records auth events.
- **Board**: portal has a static login *page* but no auth API; Supabase has a `users` table without an auth schema; no session handling; no rate limiter.
- **Gap**: auth API, session lifecycle, password reset flow + email, rate limiting, audit logging, tests — none present.
- **Spine (excerpt, ordered)**: (1) auth schema migration → (2) registration endpoint + test → (3) login endpoint issuing session + test → (4) session-validation middleware → (5) logout + session revocation → (6) password-reset request endpoint → (7) reset-email delivery → (8) reset-confirm endpoint → (9) session expiry + refresh → (10) rate limiting on auth routes → (11) audit logging of auth events → (12) error/lockout states → (13) end-to-end integration test of the full flow → (14) observability dashboard panel → (15) operator runbook for auth incidents.
- **Branch point** at move 7: "if managed email provider approved → integrate it; else → build SMTP sender," re-converging at move 8.
- **Red-team** catches that move 13's "full flow" never verified *lockout* behavior from move 12 → add a move 13b. It also notes the win condition's "audit log" had no *verification* move → strengthen move 11's verify clause.

The same three-task brief becomes a 15+ move plan that already contains the pieces that would otherwise have become apologies.
