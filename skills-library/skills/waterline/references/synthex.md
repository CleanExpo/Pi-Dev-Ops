# Pack — Synthex

Doctrine and pointers only. **Nothing in this file may decay.** No ticket IDs, no epic
numbers, no "current status", no model IDs, no counts. If a fact could be different next
Tuesday, it does not belong here — fetch it at run time.

## What Synthex is

Unite Group's **in-house autonomous marketing agency** (synthex.social). An internal
application, not a public SaaS — Stripe billing, pricing pages, "going public" and
launch-readiness are permanently out of scope and are never blockers. It services Unite
Group's own businesses and the agency's client accounts.

The North Star: the best marketing agency that can be built with today's models, running
autonomously up to the waterline — trend detection, competitor analysis, research,
copywriting, content studio, autopilot — delivering client outcomes that are countable:
phone calls, bookings, ranking, visibility.

## The waterline

**Read it live, do not restate it:** `Synthex/CONSTITUTION.md`, section
**"The Waterline — autonomy gate"**. If that heading is missing, stop — the gate has moved
and a remembered gate is not a gate.

Shape, for orientation only: agents act above the line; four classes fall below it and hand
back to Phill.

## Never

- Any auth that is not Supabase. Never Clerk, NextAuth, Auth.js.
- A query that is not org-scoped. Multi-tenant; every Prisma query carries `organizationId`.
- `prisma db push` against production. Migrations go through Supabase `apply_migration`.
- A new npm dependency, SaaS, framework or datastore to solve something already carried —
  prove it isn't already here first (`dependency-discipline`).
- An image or video from model imagination. All generation is grounded on the owned
  reference library through `lib/services/ai/image-generation.ts`; no owned references
  means BLOCKED, and the fix is adding real photos, never a bypass.
- A "done" claim without the command output that proves it.
- pnpm. This project is npm.

## Vocabulary

Australian English in all product copy — colour, organise, recognise, licence (noun),
authorise. Currency AUD, dates DD/MM/YYYY. Commits `type(scope): description`.

## Fetch at run time, never store

- Live backlog and course → Linear, team `SYN`.
- Estate context → `brain.js find`.
- What the ship carries (env) → `npx vercel env ls`, Railway MCP.
- Routing to a specialist → the crew table in `Synthex/.claude/skills/north-star/SKILL.md` §5.

If a fetch fails, write `COURSE: UNVERIFIED` in the brief and proceed on that basis. Never
substitute a remembered state for a live one.
