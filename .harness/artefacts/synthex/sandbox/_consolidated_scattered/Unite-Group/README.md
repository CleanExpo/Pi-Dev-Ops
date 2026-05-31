# Unite Group — Empire Command Center

Executive dashboard and platform layer for the Unite-Group portfolio of businesses.

## What this is

Unite-Hub is the CEO command center for Unite-Group. It connects to Pi-CEO (the autonomous operating system) to surface real-time health, agent activity, and business metrics across all six portfolio businesses: RestoreAssist, DR/NRPG, Synthex, CARSI, CCW-CRM, and Unite-Group CRM.

## Stack

- **Framework:** Next.js 14 (App Router)
- **Database/Auth:** Supabase (Postgres + Row-Level Security)
- **Deployment:** Vercel
- **UI:** Tailwind CSS + shadcn/ui (Radix primitives)

## Development

```bash
pnpm install
pnpm dev          # http://localhost:3000
pnpm build        # production build
pnpm tsc --noEmit # type-check only
```

## Environment

Copy `.env.example` to `.env.local`:
- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`
- `PI_CEO_API_URL` (Pi-CEO FastAPI on Railway)
- SMTP credentials

## Key Routes

| Path | Purpose |
|---|---|
| `/dashboard` | CEO dashboard — portfolio health + active agents |
| `/api/health` | System health check |
| `/api/pi-ceo/health` | Pi-CEO autonomous system status |

## Autonomous Operations

Pi-CEO workspace: `.pi-ceo/<session>/`. Active session state in `STATUS.md` and `PLAN.md`.

## Changelog

- 2026-05-13: Duncan Perkins / ITR Platform onboarding — portal at /clients/dimitri-itr, magic-link via /api/onboarding/send-magic-link
