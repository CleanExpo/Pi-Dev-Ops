# Pi-Dev-Ops — Codebase Wiki (root index)

Navigation entry point for the self-updating per-directory `WIKI.md` files (RA-1968).
Each linked wiki summarises recent changes and intent for its directory. Wikis are
**derived** — regenerated from commits by `scripts/run_codebase_wiki.py`; never hand-edit them.

- **Refresh one dir:** `python3 scripts/run_codebase_wiki.py --since=<base-sha> --directories=<dir>` (add `--dry-run` to preview cost)
- **Auto-refresh:** post-merge `.github/workflows/codebase-wiki.yml` updates changed dirs on `main`
- **How to work with it:** see `CLAUDE.md` → "Working with the wiki (session convention)"

## Directory wikis

| Directory | Wiki | Last regenerated (UTC) |
|---|---|---|
| `app` | [app/WIKI.md](app/WIKI.md) | 2026-05-28 |
| `src` | [src/WIKI.md](src/WIKI.md) | 2026-05-23 |
| `swarm` | [swarm/WIKI.md](swarm/WIKI.md) | 2026-05-27 |
| `scripts` | [scripts/WIKI.md](scripts/WIKI.md) | 2026-05-27 |
| `skills` | [skills/WIKI.md](skills/WIKI.md) | 2026-05-26 |
| `mcp` | [mcp/WIKI.md](mcp/WIKI.md) | 2026-05-10 |
| `dashboard` | [dashboard/WIKI.md](dashboard/WIKI.md) | 2026-05-09 |
| `packages` | [packages/WIKI.md](packages/WIKI.md) | 2026-05-17 |
| `supabase` | [supabase/WIKI.md](supabase/WIKI.md) | 2026-05-28 |
| `tests` | [tests/WIKI.md](tests/WIKI.md) | 2026-05-28 |
| `aip` | [aip/WIKI.md](aip/WIKI.md) | 2026-05-17 |
| `adrs` | [adrs/WIKI.md](adrs/WIKI.md) | 2026-05-24 |
| `docs` | [docs/WIKI.md](docs/WIKI.md) | 2026-05-17 |
| `decks` | [decks/WIKI.md](decks/WIKI.md) | 2026-05-17 |
| `live-nexus` | [live-nexus/WIKI.md](live-nexus/WIKI.md) | 2026-05-17 |
| `preview-canvas` | [preview-canvas/WIKI.md](preview-canvas/WIKI.md) | 2026-05-09 |
| `remotion-studio` | [remotion-studio/WIKI.md](remotion-studio/WIKI.md) | 2026-05-17 |
| `hermes-plugins` | [hermes-plugins/WIKI.md](hermes-plugins/WIKI.md) | 2026-05-14 |
| `claude-hooks-mirror` | [claude-hooks-mirror/WIKI.md](claude-hooks-mirror/WIKI.md) | 2026-05-17 |
| `.github` | [.github/WIKI.md](.github/WIKI.md) | 2026-06-10 |
| `.harness` | [.harness/WIKI.md](.harness/WIKI.md) | 2026-05-24 |
| `.claude` | [.claude/WIKI.md](.claude/WIKI.md) | 2026-05-09 |
| `.research` | [.research/WIKI.md](.research/WIKI.md) | 2026-05-09 |
| `.marketing` | [.marketing/WIKI.md](.marketing/WIKI.md) | 2026-05-17 |

_Index generated 2026-06-30. Regenerate the table after adding a new directory wiki._
