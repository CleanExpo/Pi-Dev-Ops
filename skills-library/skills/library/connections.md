# Library — Connections Registry

Check-out card for external systems. Read on demand, never @include. One line per connection: how to reach it, where auth lives. If a route fails, fall back per `connector-routing` skill (Composio is the cross-environment default; claude.ai connectors are per-account fragile; Desktop MCP is local-only).

## MCP servers (load schemas via ToolSearch)

> **Prefix reality (audited 2026-06-15):** the old literal `mcp__claude_ai_*` prefixes NO LONGER EXIST. Connectors now register under hashed-UUID prefixes (e.g. Linear = `mcp__2f101dc2-…`, Supabase = `mcp__8777c965-…`). Do NOT hardcode prefixes in skills — resolve by capability via ToolSearch (e.g. `ToolSearch "linear list_issues"`). The "auth status" column reflects the 2026-06-15 session.

| Connection | Auth | Status | Notes |
|---|---|---|---|
| Plaud | OAuth, `~/.plaud/tokens-mcp.json`, `login` tool | HEALTHY | Read `plaud-shared` skill first; durations in ms; page_size ≥ 10 |
| Linear | two lanes | desktop MCP HEALTHY | Local `linear-server` MCP (global) works; the claude.ai cloud connector is a SEPARATE OAuth (user-only) and still **NEEDS AUTH**. Task/ticket SoT for client work. Writes gated by the auto-mode permission classifier — needs an explicit allow rule to close/edit tickets |
| Supabase | claude.ai connector | HEALTHY | Portfolio DBs; prefer local dev before remote migrations. **RestoreAssist production is NOT on Supabase**: live restoreassist.app (DO app `29d505b9…`) runs on DigitalOcean managed Postgres cluster `db-restore-assit` (`5bcebb31-1215-418a-9e84-1881b0e6e519`), read host-only from `doctl apps spec get`. Supabase `udooysjajglluvuxkijp` (restoreassist-prod-2026) is STALE since 22/08/2026 (0 `SketchRoom` rows) — never apply to it. Before any RestoreAssist DB action, match `databaseFingerprint` + `migrationLedgerFingerprint` from `https://restoreassist.app/api/health/migrations` (verified 21/09/2026). `oxei…` is an older staging clone — DON'T target it |
| Gmail / Calendar / Drive | claude.ai connector | HEALTHY | Drive: personal Gmail needs OAuth refresh-token, NOT service accounts (SA = Workspace Shared Drives only) |
| Stripe — Unite-Group | API key in `~/.hermes/.env` | HEALTHY | `acct_1SK3Z3…`. Never ask user to paste keys |
| Stripe — Synthex | separate server | HEALTHY | `acct_1SzE5K…` — DISTINCT account, not a duplicate of the Unite-Group server |
| Stripe (claude.ai mcp.stripe.com) | claude.ai connector | **NEEDS AUTH** | 3rd Stripe registration; auth on first use |
| Margot | local | HEALTHY | deep_research, image_generate, corpus_status |
| Exa | claude.ai connector | HEALTHY | `web_search_exa` / `web_fetch_exa` — preferred internet/web-data lookup lane (feedback memory 2026-06). Previously undocumented; catalogued 2026-07-06 |
| Vercel | claude.ai connector | HEALTHY | deployments, build/runtime logs, projects; distinct from the `plugin:vercel` lane below |
| chrome-devtools | local | HEALTHY | Prefer `browser` skill (browser-harness) for general automation |
| vibetest | local | HEALTHY | UI swarm testing |
| semrush / Composio / BigQuery / plugin:vercel | per-connector authenticate tool | **NEEDS AUTH** | Auth on first use |
| M365 / Slack / Spotify | claude.ai connector | HEALTHY | Spotify previously undocumented — confirmed live 2026-06-15 |
| claude-in-chrome | extension | HEALTHY | Repaired 2026-07 (duplicate registration removed). Browser automation lane — route via `browser-routing` skill |
| aip-readonly | local | HEALTHY | Repaired 2026-07 (needed `MCP_TIMEOUT` + `npm install` in `Pi-Dev-Ops/aip`). Was marked DEAD 2026-06-15 |
| Telegram | plugin | HEALTHY | reply/react/edit_message; access via /telegram:access only |

## CLIs (on $PATH unless noted)

| CLI | Invoke | Auth | Notes |
|---|---|---|---|
| browser-harness | `browser-harness <<'PY' ... PY` | uses user's running Chrome | Skill: `browser`. First nav = new_tab(), never goto_url() |
| composio | `composio run/execute/search` | `composio link` per app | Cross-environment default for 3rd-party services |
| nlm | `nlm ...` | Google login | NotebookLM; skill: `nlm-skill` |
| autogit | `autogit on/ship/undo/status` (npm global, pnpm node bin) | git creds | Auto stage→scan→commit→push on agent Stop; OPT-IN per repo via `autogit on` |
| gh | `gh ...` | logged in (`CleanExpo`) | GitHub PRs/issues/API |
| chrome-agent | `chrome-agent launch\|status\|attach\|stop` | none (drives local Chrome via CDP) | **CDP-anchor tier, 0.5.7, installed 2026-08-17.** Raw Chrome DevTools Protocol passthrough, no abstraction. Scope: **critic observation and raw-CDP escape hatches ONLY** — `agent-browser` stays the daily driver for actuation. Earns its place on ONE capability: multi-client **isolated event subscriptions**, so a blind critic can `attach +Network.responseReceived +Console.messageAdded` on its own stream while a worker drives the same browser — an anchor the artefact did not author. Consumed from **PyPI (MIT, Corey Gallon / captivus)**; we do **not** maintain a fork — `CleanExpo/chrome-agent` was an unmodified copy of v0.5.7 that also inherited a live `publish.yml` running `uv publish --trusted-publishing always`. Install: `uv tool install chrome-agent` with `UV_NATIVE_TLS=1` (AVG re-signs TLS; rustls dies `UnknownIssuer` without it). Needs Python ≥3.11 + Chrome |

### Parked (dormant — do NOT delete; may revive)
- **Vercel CLI — `zenithfresh25-1436` account.** Removed from the everyday catalog 2026-07-08 (founder: keep for possible later use, do not delete). The CLI is authed to the dead `zenithfresh25@gmail.com` account; for any active Vercel work **re-auth to the `unite-group` team first** (see [[reference_vercel_signin_pathway]]). Until re-authed, treat Vercel CLI as unavailable for everyday deploys/env reads.

## APIs / credentials

| What | Where | Notes |
|---|---|---|
| Anthropic API | `ANTHROPIC_API_KEY`, `_3` | `_1`/`_2`/Railway-prod out of credit, `_4` invalid; 1Password has none |
| Stripe (Unite Group) | `~/.hermes/.env` | resolve programmatically, never paste |
| DataForSEO | wired inside `seo*` skills | all SEO data |
| OpenRouter | sub-agent tasks + independent review | ⚠️ LIVE key is in `D:/Synthex/.env.local` ONLY — the copies in `%LOCALAPPDATA%\hermes\.env`, `~/.claude/secrets/openrouter.key` and `D:/Synthex/.env` are REVOKED and 401. Verify with `GET /api/v1/credits`; a bare 401 discriminates nothing (no-auth returns 401 too). Per 06-11 mandate default to Max plans for primary work |
| xAI / Grok | **monthly Grok subscription account**, signed in through the vendor's own app/CLI — the same shape as Claude Max and the ChatGPT/Codex plan. NOT an API key. NOT a `.env` entry | NO ACCOUNT YET — Phill buys the monthly plan when he is ready | Checked 16/09/2026: no Grok app in `/Applications`, no `grok` CLI on PATH, no login store, and no API key in any of the 8 stores (`find-cred grok`). The `Grok Bot Safe Storage` Keychain entry is a leftover desktop-app encryption entry — **not** a login and **not** a key. When the subscription exists: install the vendor client, sign in, and the login lands in that client's own token store (Keychain entry or a JSON file), never in `~/.hermes/.env`. `find-cred grok` reads those stores and reports the token expiry, because a CLI can print "logged in" on a dead token. Do NOT substitute OpenRouter — metered, and against the 06-11 Max/monthly-plan mandate |
| DeepSeek | **`~/.hermes/.env` → `DEEPSEEK_API_KEY`.** PREPAID API credit, not a subscription | **LIVE 18/09/2026 — $5.00 prepaid, proved working** | **CORRECTED 18/09/2026. The previous entry here was WRONG** and it caused a wrong answer to Phill: it claimed "monthly subscription account, signed in through its own app/CLI. NOT an API key. NOT a `.env` entry". DeepSeek sells **no** CLI-OAuth subscription. Its own docs (`api-docs.deepseek.com/quick_start/agent_integrations/deepcode/`) state Deep Code CLI uses "API key authentication, not OAuth or subscription login". The old row was written by analogy to Grok/Claude Max and never checked against DeepSeek's actual product — the Grok row above may carry the same unverified assumption. **Two endpoints, BOTH proved live 18/09 with HTTP 200:** OpenAI-shaped `https://api.deepseek.com/v1/chat/completions` (`Authorization: Bearer`), and **Anthropic-shaped `https://api.deepseek.com/anthropic/v1/messages`** (`x-api-key` + `anthropic-version: 2023-06-01`) — the second means existing Anthropic-protocol code works by changing only the base URL, so **no third-party CLI is needed**. Do NOT install `@vegamo/deepcode-cli`: single maintainer (`parsec326`), and DeepSeek's docs disclaim support for it. Models `deepseek-flash` and `deepseek-v4-pro`; both returned real text. **TRAP: they are reasoning models** — at `max_tokens: 16` both returned `thinking` blocks with EMPTY text and `stop_reason: max_tokens`; at 600 both returned `DEEPSEEK_OK` with `end_turn`. Budget generously or a live lane reads as broken. Balance check: `GET https://api.deepseek.com/user/balance`. Prepaid, so it **cannot overspend** — safer than the uncapped OpenRouter key. DeepSeek publishes no `llms.txt`; the docs library records `not_llms_txt`, which is the truthful status, not a failure |
| Hermes (incl. Telegram, Slack, Discord) | **Claude Max subscription** via provider `anthropic` (`CLAUDE_CODE_OAUTH_TOKEN` / `claude_code` OAuth in the pool). Switched 16/09/2026 from `minimax` + `MINIMAX_API_KEY` | ON MAX — no API credits | Telegram/Slack/Discord are surfaces on one gateway, but **each profile can override the provider — a global `hermes config set` does NOT reach them all**. `hermes profile list` is the check. As at 16/09/2026: `default` (serves the Margot Telegram bot), `dr` and `pm-core` are on the Max lane; `ownest` was moved off a MoA preset that sent both reference and aggregator calls to metered OpenRouter; the four `empire*` profiles stay pinned to `openai-codex` (a ChatGPT-subscription lane, not credits) which is **logged out** — they fail loudly rather than spend, and need `hermes auth add openai-codex --type oauth`. A gateway restart is required for a running surface to pick up any change. The pooled `ANTHROPIC_API_KEY` was **removed and suppressed**, so a failed Max lane fails loudly instead of billing — undo with `hermes auth add anthropic --type api-key`. `fallback_providers` is `[]`, so no silent hop to OpenRouter. Proved live: `hermes chat --oneshot -q "…"` returned `MAX_LANE_OK`. Backups: `~/.hermes/config.yaml.bak-before-max-switch-20260916`, `~/.hermes/auth.json.bak-before-max-switch-20260916` |
| ElevenLabs TTS | `~/.hermes/.env` → `ELEVENLABS_API_KEY` + `ELEVENLABS_VOICE_ID` | Phill's paid plan. Voice Artist / TTS via REST API. Default voice in `ELEVENLABS_VOICE_ID`. Used by `faceless-video` + CARSI course-media. Resolve key programmatically, never paste |
| ElevenLabs MCP (convai agents) | official `elevenlabs-mcp` (PyPI) via `uvx elevenlabs-mcp`; `ELEVENLABS_API_KEY` env per-server | Register per-project (`claude mcp add`), NOT global (27 tools = context cost). Manages convai agents (`create_agent`, `list_conversations`, `make_outbound_call`, `list_phone_numbers`, `check_subscription`). NO Twilio-import tool, NO per-agent usage tool. Metering = REST `GET /v1/usage/character-stats?breakdown_type=resource` + `/v1/user/subscription`. Portfolio plan: Unite-Group `docs/planning/elevenlabs-portfolio-readiness-2026-07-14.md`. Verified 14/07/2026 |

## Image / media generation

| What | Substrate | Auth | Notes |
|---|---|---|---|
| AI image generation | **Artlist AI Toolkit** (`toolkit.artlist.io/image-video-generator`) | in-browser login (Phill's Chrome, browser-harness Way-1) | PRIMARY. Model Nano Banana 2, 16:9/2K. Results at `ai-toolkit-generations.imgix.net` — download EXACT src (rewriting imgix params → 403). Generate one-at-a-time (grid virtualizes). Used by `faceless-video`. NOT Higgsfield. NB: "artist.io" is a typo for artlist.io |
| AI image generation (fallback) | `mcp__margot__image_generate` | margot MCP | Nano Banana 2 / Gemini 3.1 flash-image. Unattended/automated runs only. 1K $0.045, 2K $0.067, 4K $0.151 per img |

## Research / data sourcing (tiered — cheapest first)

| Tier | Substrate | Auth | Notes |
|---|---|---|---|
| 1 | `mcp__margot__deep_research` / `deep_research_max` | margot MCP | Gemini 3.1 Pro cited synthesis; `use_corpus=True` anchors Unite-Group corpus. Primary research route |
| 2 | `WebSearch` (built-in) | none | Set `allowed_domains` to a credibility whitelist (.gov/.edu/who.int/nih.gov/nature.com…) to force Tier 1–2 results |
| 3 | `WebFetch` (built-in) | none | Pull exact stat+context from a chosen URL; fails on auth-walled pages |
| 4 | `browser-harness` | user Chrome | JS/login-walled credible sources WebFetch can't read |
| 5 | **Bright Data (PAID ESCALATION)** | **NOT wired — needs account + API key** | Anti-bot / dataset / geo-locked credible sources only, when tiers 1–4 fail. Add key to `~/.hermes/.env` as `BRIGHTDATA_API_KEY` when first needed; log spend. Used by `source-ingest` |

Captured sources land in `~/2nd Brain/2nd Brain/Sources/` (385+ already), indexed in `Sources/SOURCE-LIBRARY.md`. Skill: `source-ingest`. Cite Tier 1–2 only.

## Planned (not yet built)

- 1Password API broker for client credentials (Synthex auto-login) — per Plaud 06-11 recording.
- Xero ingestion into Unite Group Nexus.

## HeyGen + ElevenLabs course-intro video (CARSI) — CHECK THIS BEFORE improvising any video path
- **Creds live in the DigitalOcean `monkfish-app`** (id `a9d718db-7961-4107-9477-96c72fcf620f`), NOT local env / Vercel / CARSI scripts. Read them via the **valid `DIGITALOCEAN_ACCESS_TOKEN` in `CARSI/.env.local`** (both doctl config contexts are 401-dead; the local `HEYGEN_API_KEY` is also 401-dead — do NOT use it). `GET https://api.digitalocean.com/v2/apps/<id>` Bearer token → `spec.services[].envs` (plaintext): `HEYGEN_API_KEY`, `HEYGEN_AVATAR_ID`, `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`.
- **⚠ USE v3, NOT v2, FOR A RECORDED-TO-CAMERA AVATAR.** A to-camera capture produces a **Digital Twin**, the only avatar class eligible for **Avatar V** (HeyGen's highest-fidelity motion + lip-sync). `/v2/video/generate` has no `engine` field, so it can never reach it — the render succeeds and silently looks like the cheap path. Use `POST api.heygen.com/v3/videos` with `{type:"avatar", avatar_id:<LOOK id>, engine:{type:"avatar_v"}, resolution:"1080p", motion_prompt:"…"}`, after confirming `"avatar_v"` is in `supported_api_engines` from `GET /v3/avatars/looks/{look_id}`; poll `GET /v3/videos/{id}`. Parameter table + footguns: `skills/heygen-director/references/digital-twin-quality.md`.
- **Legacy v2 pipeline (historical, avatar + ElevenLabs voice):** ElevenLabs TTS → HeyGen `POST upload.heygen.com/v1/asset` (audio) → `POST api.heygen.com/v2/video/generate` `{character:{type:avatar,avatar_id},voice:{type:audio,audio_asset_id}}` → poll `v1/video_status.get`. v3 supports ElevenLabs-backed voices natively via `voice_settings.engine_settings`, so the upload hop is no longer needed. Full detail: memory `carsi-heygen-elevenlabs-video-route`.
- **⚠ STALE CONFIG (2026-07-24):** the monkfish `HEYGEN_AVATAR_ID` renders but is an OLD avatar (not in the account's current 1267-avatar list) and `ELEVENLABS_VOICE_ID` = "Clara" (female) may not be the intended voice. VERIFY the avatar+voice against founder intent BEFORE shipping — a successful render is NOT a correct render.
- **FOUNDER-DESIGNATED AVATAR (2026-07-24): `344a0b3abfe3435da41a8820efa669e4`** — supersedes the monkfish value. From a multi-minute to-camera recording, so resolve its look, confirm `avatar_type` and engine eligibility, and render it on Avatar V.
- **Do NOT substitute:** `render-lesson.mjs` (Remotion + macOS `say`) is NOT HeyGen; CARSI `generate-course-lesson-videos.ts` uses HeyGen TTS not ElevenLabs. Canonical skill: `heygen-director`.
