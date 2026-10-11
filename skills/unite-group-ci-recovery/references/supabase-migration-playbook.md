> Moved from SKILL.md. Read when applying or debugging a Supabase migration, or needing project IDs and the standing auth grant.

## 3 — Supabase migration playbook

### 3.1 Use the MCP `apply_migration` tool, NOT the CLI for multi-statement files

The Supabase CLI's `supabase db query --linked -f <file>` wraps the file body in JSON for the Management API. **Multi-statement migrations (especially with `DO $$ ... $$` blocks or PL/pgSQL functions) break with:**

```
Failed to run sql query: ERROR: 42601: syntax error at or near "["
LINE 1: [
        ^
```

The `[` is the start of the JSON wrapper hitting Postgres as raw SQL.

**Correct path for multi-statement migrations:**

```typescript
mcp__21d7de5d-7115-4af8-a6c3-2b86769b05fb__apply_migration({
  project_id: "znyjoyjsvjotlzjppzal",  // Synthex; see reference_supabase_project_ids
  name: "add_marketing_agent",          // snake_case, no date prefix
  query: "<full multi-statement SQL>"
})
```

The CLI is fine for one-off inline SELECTs (`supabase db query --linked "SELECT ..."`). Avoid it for `-f <file>` unless the file is a single statement.

### 3.2 Standing Supabase auth (granted 2026-05-25)

The user granted standing authorization for SQL ops on linked projects. Per memory `feedback_standing_supabase_auth`:
- Routine reads, idempotent DDL with `IF NOT EXISTS`, RLS adds: proceed
- Show the SQL inline before applying any non-trivial migration
- Pause for genuinely destructive ops (`DROP TABLE`, `TRUNCATE`, `DELETE` without narrow WHERE)
- Pause for prod writes to customer-owned data

### 3.3 Prereq detection — always check FK targets exist before applying

The 2026-05-25 trap: PR #295's `20260525_add_marketing_agent` had a FK to `marketing_agency_qa_reports`. That table was declared in `prisma/schema.prisma` but **never had a CREATE TABLE in any migration file** (latent gap going back months). Apply failed with:

```
ERROR: 42P01: relation "public.marketing_agency_qa_reports" does not exist
```

**Before applying any migration with FKs to other tables, run a `to_regclass()` check** to confirm targets exist on the target DB:

```sql
SELECT to_regclass('public.<parent_table>')::text AS parent;
```

If null, write a prereq migration that creates the missing table(s) first. See PR #297 for the template (`20260524_add_marketing_agency_core_tables`).

### 3.4 Project ID quick reference

Always verify the project ID matches the repo before any DDL. From memory `reference_supabase_project_ids`:

| Repo | Project ID |
|---|---|
| Pi-CEO / Pi-Dev-Ops | `zbryrmxmgfmslqzizsto` |
| Synthex | `znyjoyjsvjotlzjppzal` |
| Disaster-Recovery | `zwzbglqzmpyfzdkblxyf` |
| RestoreAssist | `oxeiaavuspvpvanzcrjc` |
| Unite-Group | `lksfwktwtmyznckodsau` |
| ATO | `xwqymjisxmtcmaebcehw` |
| DR-NRPG | `lccqasmurmsisnnjqqmr` (separate org `jobkjtecrxliqfnrcssa`) |
| CARSI | `ofzafxvxobjggjisrbsa` (separate org `pmsatfzevrriaylbsifp`) |

`pwwwhoaxxtkmowifpuwf` (NodeJS Starter V1) is NOT a real project — it's where the single-project MCP `c879c796` is bound. Never write to it expecting it to be Pi-CEO. The 2026-05-24 incident applied a migration here by mistake.
