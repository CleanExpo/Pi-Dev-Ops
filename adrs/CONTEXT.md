# Pilot Bot — Domain Context

Ubiquitous-language glossary for the Pilot bot ("Agency" pattern internal-only Telegram bot). Locked via `/grill-with-docs` interviews with Phill 2026-05-15.

Source spec: `[[agency-bot-design-2026-05-14]]` + `docs/superpowers/plans/2026-05-14-agency-bot-pilot.md`.

---

## Glossary

### fingerprint
The dedup key for a Pilot suggestion. **Hybrid C, leaning A:** source-local string is the primary key (cheap, stable, no false-positives); a semantic hash is recorded as a secondary column for cross-source dedup queries.

- **Cardinality:** 1 source-local fingerprint per `pilot_suggestions` row (NOT NULL, indexed).
- **Source-local shape examples:** `linear:RA-2947`, `gmail:msg-id-abc123`, `github:CleanExpo/Pi-Dev-Ops@4db5e03`, `margot:<job-id>`, `wiki:<slug>`.
- **Semantic shape:** `sha256(pillar + canonicalised_headline + target_entity)` — 12-char prefix.
- **Tenant scoping:** semantic-dedup is **ON by default for Phill's own tenant** (voice is consistent across his branding — same idea surfacing from Linear + Margot SHOULD dedup). **OFF by default for client tenants brought into Unite-Group** (each client's idea-space is independent; cross-client semantic dedup would surface false-positives). Config flag lives at `BrandConfig.pilotConfig.semantic_dedup_enabled` per `[[adrs/002-tenant-identification]]`.
- **Anti-pattern:** never hash the full suggestion body — wording variance breaks the hash; that's why semantic uses canonicalised-headline only.

### pillar
A strategic theme a suggestion advances. **Array-typed.** A single suggestion can advance ≥1 pillars (cross-pillar initiatives are common — e.g. one Linear ticket spans ATIA + Restoration).

- **Cardinality:** ≥1 pillars per `pilot_suggestions` row. Column type: `text[]` (PostgreSQL array).
- **Master enum authority:** the 11-value canonical list lives in the **YAML frontmatter of `[[master-plan-2b-by-2028-v3]]`** — single source of truth. Code reads it at startup (cached with TTL or webhook invalidation), NEVER hardcoded.
- **Per-source mapping:** each ingestion source (Linear, Margot, GitHub, Gmail, wiki) extracts its native identifier (team key, research-tag, repo-path, label, slug) and **delegates to `PillarCanonicaliser`** which maps raw → ≥1 master pillars. Sources do NOT carry their own pillar enum.
- **Multi-pillar suggestion:** if the canonicaliser returns 2+ master pillars, all are stored in the array; downstream UIs surface them as chips.
- **Anti-pattern:** sources with built-in pillar enums (`_TEAM_TO_PILLAR`, `_VALID_PILLARS`) — these are category errors and must be removed (per `[[adrs/001-pillar-canonicalisation]]`).
- **Decision record:** `[[adrs/001-pillar-canonicalisation]]`.

### canonicaliser
A pure function that maps a source-native identifier onto the master pillar enum.

- **Shape:** `PillarCanonicaliser.canonicalise_<source>(raw_identifier: str) -> list[str]` — returns ≥1 master pillars from the wiki-frontmatter-sourced canonical list.
- **Contract:** every supported source has its own method (`canonicalise_linear`, `canonicalise_margot`, `canonicalise_github`, etc.). Sources delegate; canonicaliser owns translation.
- **Fallback:** if no mapping resolves, returns `["uncategorised"]` (NOT empty) — preserves the ≥1 cardinality invariant. Surfacing in UI as a `🟡 uncategorised` chip is the signal to add the mapping.
- **Master enum is read-only to the canonicaliser** — never mutates, only reads.

### master enum (pillar)
The canonical 11-value pillar list. Lives in `[[master-plan-2b-by-2028-v3]]` YAML frontmatter under key `pillars:`. Loaded at startup, cached, invalidated on wiki sync.

- **Why wiki not code:** business alignment > architectural convenience. Phill edits the master plan; pillar list updates without a code deploy.
- **Why frontmatter not body:** YAML is machine-readable; prose is not.
- **TTL or webhook?** Decided in plan, not glossary.

---

### tenant
The **billing + isolation boundary** for Pilot suggestions, preferences, and audit logs. **Distinct from `brand`** even though they're 1:1 today.

- **Identification:** `tenant_slug` (VARCHAR) on every Pilot table. Derived from the canonical `Synthex/packages/brand-config/src/brands/{slug}.ts` filename — slug NOT UUID, so it round-trips to the TypeScript file without a lookup table.
- **Cardinality (v1):** 1 tenant per `BrandConfig` file. Future-proofed for 1:N via the `TenantConfig` envelope (`brands: Record<string, BrandConfig>`); enforced in v1 by `Object.keys(brands).length === 1 && tenant_slug === brand_slug`.
- **Isolation:** Postgres RLS on every Pilot table, policy = `tenant_slug = current_setting('app.current_tenant_slug')`. Single Supabase project (`lksfwktwtmyznckodsau`), not per-tenant projects.
- **CI/CD guardrail:** GitHub Action on every PR asserts RLS is ENABLED on every `pilot_*` table + a positive assertion that `SELECT * FROM pilot_suggestions` returns 0 rows without a tenant context set. Direct remediation for the Margot RLS leak per `[[portfolio-health-snapshot-2026-05-14]]`.
- **Anti-pattern:** treating `tenant` and `brand` as synonyms in code. They align in v1; conflating them in types locks out the future agency model.
- **Decision record:** `[[adrs/002-tenant-identification]]`.

### brand
The **voice + visual + presentation identity** for one of Phill's portfolio businesses or client engagements. **Distinct from `tenant`** even though they're 1:1 today.

- **Identification:** `brand_slug` (VARCHAR) — file basename of `Synthex/packages/brand-config/src/brands/{slug}.ts`.
- **Contents:** voice rules, voiceover config, motion language, audience, channel defaults, forbidden words, colour tokens, typography, spacing, plus the new `pilotConfig` block (semantic_dedup_enabled, etc.) — owned end-to-end by `[[remotion-brand-codify]]` for the visual/voice parts, extended by Pilot for behavioural config.
- **Why distinct from tenant:** a single tenant might run multiple brands later (Phill onboards an agency client managing 5 sub-brands under one billing relationship). The 1:N path is `brands: Record<string, BrandConfig>` inside `TenantConfig`.

---

### suggestion card
The atomic UX unit of the Pilot live stream. Each Pilot-generated suggestion is delivered as ONE Telegram message with an `InlineKeyboardMarkup` attached — never plain text. The user triages by tapping a button, NOT by typing.

- **Button layout:** Row 1 = `[✅ Agree] [❌ Dismiss] [🎙 Discuss]`. Row 2 (per-card optional, always-present in greeting) = `[⏸ PAUSE 24h] [⏹ STOP]`.
- **Lifecycle:** card is sent → user taps a button → callback fires → card's `reply_markup` is `editMessageReplyMarkup`'d to a visual processed-state (greyed buttons + ✓/✗ marker) → next card queues.
- **Inspiration:** Magnus Mueller's "Tinder-swipe" Agency pattern from `[[research-browser-harness-pm-synthesis-2026-05-14]]`, adapted to native Telegram primitives — no Mini App, no microphone-permission prompts.
- **Anti-pattern:** plain-text suggestion pings without an `InlineKeyboardMarkup`. They force typed replies, break the swipe flow, and re-introduce the "wall of text" friction that killed `grill-me` for coding work.

### discuss verb
The third button on every suggestion card — `[🎙 Discuss]`. Opens a voice-reply branch.

- **Trigger:** user taps `[🎙 Discuss]` → Pilot replies prompting the user to record a Telegram native voice message (no Mini App, no in-app mic surface).
- **Pipeline:** incoming `Message.Voice` → `getFile` to download → transcription (model TBD in plan) → routed into the discussion thread for that suggestion.
- **Why voice over typed elaboration:** matches CEO-mobile reality (Phill driving / walking / in meetings) and pre-empts the typed-response trap where a short suggestion produces a long typed reply that nobody reviews.

### pause-state
The state-machine controlling the Pilot live stream's emission cadence per tenant. Stored on `pilot_preferences`.

- **Enum values:** `active` · `paused-hard` · `paused-until-{ISO-8601-timestamp}`.
  - `active`: emit suggestions per the configured cadence.
  - `paused-hard`: indefinite pause. Set by user tapping `[⏹ STOP]`. Resumes only on `RESUME` typed message OR tenant config flip.
  - `paused-until-{ts}`: soft time-boxed pause. Set by `[⏸ PAUSE 24h]` (default) or programmatic longer windows. Auto-resumes when `now() > ts`.
- **Cardinality:** 1 pause-state per tenant (per `BrandConfig` in v1). Future 1:N tenant→brand will move pause-state per-brand.
- **Scope separation:** pause-state halts the **interactive live stream only**. The daily L4 Karpathy executive digest (from `[[spec-karpathy-pipeline-audit-2026-05-15]]`) continues independently — it's the async catch-up mechanism that survives any pause.
- **Decision record:** `[[adrs/003-interactive-game-mode]]`.

### interactive game mode
The collective name for Pilot's UX contract: every suggestion is a `suggestion card`, every triage decision is a `[✅ Agree] [❌ Dismiss] [🎙 Discuss]` tap, every pause is a `pause-state` transition. Distinct from the daily executive digest (which is a separate read-only summary surface).

- **Tinder-style cadence:** one card at a time, processed before the next queues. No card-bombing.
- **Friction budget:** ≤3 taps per triage (decision + optional confirmation + optional voice send). If a flow requires more, it gets routed to typed mode or a separate ADR.

---

## Open questions

- Q5+ — TBD per future interview. Pilot V1 domain language is locked per the 3 ADRs.

---

## Decision records

- `[[adrs/001-pillar-canonicalisation]]` — 2026-05-15 — adopt canonicaliser pattern + wiki-frontmatter master enum + array-typed pillar column.
- `[[adrs/002-tenant-identification]]` — 2026-05-15 — Shape C: tenant_slug column + BrandConfig-driven config + RLS via `current_setting` + CI/CD guardrail.
- `[[adrs/003-interactive-game-mode]]` — 2026-05-15 — native Telegram InlineKeyboardMarkup card UX + voice-reply fork + two-verb pause-state state machine + scope separation from L4 daily digest.
