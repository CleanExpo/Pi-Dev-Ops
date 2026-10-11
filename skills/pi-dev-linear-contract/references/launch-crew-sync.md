Moved from SKILL.md. Read when syncing launch-crew findings to Linear or reviewing that sync.

## Launch-crew finding sync (added by the launch crew)

The launch crew ([`ship-it`](../../ship-it/SKILL.md) → [`launch-project-audit`](../../launch-project-audit/SKILL.md) + [`launch-review`](../../launch-review/SKILL.md) + [`launch-enhance-debloat`](../../launch-enhance-debloat/SKILL.md)) routes its findings into Linear through THIS contract — it does not define its own.

### Push (findings → Linear)
1. Read the latest `.harness/audits/audit-*.md`, `review-*.md`, `enhance-*.md`.
2. Map each finding to the correct project via `config/harness/projects.json`, matching on the entry's
   **`id`** — never `repo`, which is not unique (`CleanExpo/Pi-Dev-Ops` carries both `pi-dev-ops` and
   `margot`). Where a finding's id is genuinely unclear, ask once and persist the answer.
3. Create one issue per finding (de-duplicate first — search existing issues, update rather than duplicate):
   - **Title** — short, concrete.
   - **Description** — what / where (file/URL) / why it matters / suggested fix, plus the `run_id` + footer block this contract already mandates.
   - **Priority** — CRITICAL → Urgent/High, WARNING → Medium, SUGGESTION → Low.
   - **Source label** — `pm` / `growth` / `engineer` / `design` / `build-state` / `security`.
4. **Mark build-ready work with the EXISTING markers, not a new tag:** set status **`Ready for Pi-Dev`** + label **`pi-dev:autonomous`** ONLY on safe, reversible findings. Anything irreversible or business-judgment (production deploy, deleting data, pricing, legal copy, any 🚫-tier path) is left WITHOUT the autonomous label — it waits for a human.

### Pull (Linear → builders)
The autonomy queue is already defined above (status `Ready for Pi-Dev` + label `pi-dev:autonomous`). The launch crew adds no new loop — sandboxed building runs through the existing [`tao-loop`](../../tao-loop/SKILL.md) + [`tao-judge`](../../tao-judge/SKILL.md), per-feature phases through `ship-chain`, and the terminal ≥8/10 gate through `ship-release`. On merge + production deploy the issue closes via the existing GitHub/Vercel/Railway status round-trip.

### Verification
- Each launch-crew finding maps to exactly one issue at the right priority — no duplicates across runs.
- Only safe/reversible findings carry status `Ready for Pi-Dev` + `pi-dev:autonomous`; no 🚫-path or business-judgment issue is autonomous.
- No new machine tag (e.g. `[hermes:build]`) is introduced — the contract's existing markers are the single source of truth.
