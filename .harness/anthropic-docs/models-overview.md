# Models overview

**Source:** https://platform.claude.com/docs/en/about-claude/models/overview
**Fetched:** 2026-07-01 (manual sync from platform.claude.com)

---

## Latest models (Pi-Dev-Ops defaults)

| Tier | Claude API ID | Alias | Context | Max output | Pricing (in/out MTok) |
|------|---------------|-------|---------|------------|------------------------|
| Opus | `claude-opus-4-8` | `claude-opus-4-8` | 1M | 128k | $5 / $25 |
| Sonnet | `claude-sonnet-5` | `claude-sonnet-5` | 1M | 128k | $3 / $15 ($2 / $10 intro through Aug 31 2026) |
| Haiku | `claude-haiku-4-5-20251001` | `claude-haiku-4-5` | 200k | 64k | $1 / $5 |

**Adaptive thinking:** Opus 4.8 and Sonnet 5 — yes. Haiku 4.5 — no (extended thinking only).

**Effort default:** `high` on Opus 4.8 and Sonnet 5 (API + Claude Code).

## Mythos-class (optional — not default in Pi-Dev-Ops)

| Model | API ID | Notes |
|-------|--------|-------|
| Claude Fable 5 | `claude-fable-5` | GA Jun 9 2026; most capable widely released; $10 / $50 MTok |
| Claude Mythos 5 | `claude-mythos-5` | Glasswing / invitation only |

Pi-Dev-Ops uses `refusalFallback()` in `dashboard/lib/models.ts` for Fable/Mythos → Opus 4.8 server-side fallback only when those models are explicitly selected.

## Legacy (migrate away)

| Model | API ID | Status |
|-------|--------|--------|
| Opus 4.7 | `claude-opus-4-7` | Legacy — use Opus 4.8 |
| Opus 4.6 | `claude-opus-4-6` | Legacy |
| Sonnet 4.6 | `claude-sonnet-4-6` | Legacy — use Sonnet 5 |
| Sonnet 4.5 | `claude-sonnet-4-5-20250929` | Legacy |
| Opus 4.1 | `claude-opus-4-1-20250805` | Deprecated — retires Aug 5 2026 |

## Versioning note

Every Claude model ID is a **pinned snapshot**. Dateless IDs (4.6 generation onward) are still pinned snapshots, not evergreen pointers.

## Pi-Dev-Ops wiring

SSOT: `app/server/model_registry.py` · Dashboard: `dashboard/lib/models.ts` · Harness: `.harness/config.yaml` (`sonnet` short name → `claude-sonnet-5`).
