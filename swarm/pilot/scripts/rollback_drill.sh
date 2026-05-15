#!/usr/bin/env bash
# rollback_drill.sh — Pilot V1 rollback rehearsal (DRY RUN only)
#
# DRY RUN ONLY — never executes on production.
# Run pre-cutover: Mon 2026-05-18 against a SCRATCH Supabase branch.
#
# Per [[feedback-substrate-change-discipline]] Discipline 4:
#   rollback-drill before deploy. Prove the rollback path works.
#   Switch back under load. Verify success. If you can't undo cleanly, can't ship.
#
# Rollback SQL from Phase 1 commit c50ff6a (applied in REVERSE order):
#   1. drop table if exists public.pilot_suggestion_messages;
#   2. drop table if exists public.pilot_preferences;
#   3. drop table if exists public.pilot_suggestions;
#   4. drop function if exists public.set_app_tenant(text);
#
# Usage:
#   SCRATCH_DB_URL="postgres://postgres:pass@localhost:5432/pilot_scratch" \
#     bash swarm/pilot/scripts/rollback_drill.sh
#
# Or with Supabase CLI scratch branch:
#   SCRATCH_DB_URL="$(supabase db url --branch scratch)" \
#     bash swarm/pilot/scripts/rollback_drill.sh
#
# Exits 0 on full success (forward+rollback+re-forward all clean).
# Exits 1 on any failure — cutover is NOT safe until this passes.

set -euo pipefail

: "${SCRATCH_DB_URL:?SCRATCH_DB_URL must be set — point at a scratch DB, not production}"

MIGRATION="supabase/migrations/20260515_pilot_v1_phase1.sql"

guard_not_production() {
  if echo "$SCRATCH_DB_URL" | grep -qiE "(prod|phill\b)"; then
    echo "ERROR: SCRATCH_DB_URL looks like a production URL. Aborting." >&2
    exit 1
  fi
}

psql_scratch() {
  psql "$SCRATCH_DB_URL" "$@"
}

echo "=== Pilot V1 rollback drill ==="
echo "Target: $SCRATCH_DB_URL"
guard_not_production

# Step 1: Apply the forward migration to ensure clean base state.
echo ""
echo "--- Step 1: Apply forward migration ---"
psql_scratch -f "$MIGRATION"
echo "Forward migration applied."

# Step 2: Verify tables exist.
echo ""
echo "--- Step 2: Verify tables + function present ---"
psql_scratch -c "\dt public.pilot_*" | grep -E "pilot_suggestions|pilot_preferences|pilot_suggestion_messages"
psql_scratch -c "\df public.set_app_tenant" | grep set_app_tenant
echo "Tables and function confirmed present."

# Step 3: Apply rollback SQL (reverse of Phase 1, per commit c50ff6a message).
echo ""
echo "--- Step 3: Apply rollback SQL (reverse order) ---"
psql_scratch <<'SQL'
drop table if exists public.pilot_suggestion_messages;
drop table if exists public.pilot_preferences;
drop table if exists public.pilot_suggestions;
drop function if exists public.set_app_tenant(text);
SQL
echo "Rollback SQL applied."

# Step 4: Verify tables and function are gone.
echo ""
echo "--- Step 4: Verify clean drop ---"
TABLE_COUNT=$(psql_scratch -tAc \
  "select count(*) from pg_tables where schemaname='public' and tablename like 'pilot_%'")
FUNC_COUNT=$(psql_scratch -tAc \
  "select count(*) from pg_proc p join pg_namespace n on p.pronamespace=n.oid
   where n.nspname='public' and p.proname='set_app_tenant'")
if [ "$TABLE_COUNT" -ne 0 ]; then
  echo "ERROR: $TABLE_COUNT pilot_* table(s) still exist after rollback." >&2
  exit 1
fi
if [ "$FUNC_COUNT" -ne 0 ]; then
  echo "ERROR: set_app_tenant function still exists after rollback." >&2
  exit 1
fi
echo "Drop confirmed — 0 pilot_* tables, 0 set_app_tenant functions."

# Step 5: Re-apply forward migration to confirm reversibility.
echo ""
echo "--- Step 5: Re-apply forward migration (confirm reversibility) ---"
psql_scratch -f "$MIGRATION"
psql_scratch -c "\dt public.pilot_*" | grep -E "pilot_suggestions|pilot_preferences|pilot_suggestion_messages"
echo "Re-apply confirmed — reversibility verified."

echo ""
echo "=== ROLLBACK DRILL PASSED — cutover is safe to schedule. ==="
