# ADR 004: Implementation conventions — tenant context setter + memory.is_blocked

**Date:** 2026-05-15
**Status:** Accepted

## Context

Two implementer ambiguities surfaced during the 2026-05-15 plan-rewrite for Pilot V1 (greenfield reframe of [[pilot-v1-implementation]]). Without resolution the implementer subagent would either bounce back to controller or invent inconsistent solutions across phases. This ADR resolves both.

## Decisions

### 1. Tenant context setter — `set_app_tenant(slug text)` Postgres function via supabase-py rpc

The RLS policies from [[adrs/002-tenant-identification]] read from `current_setting('app.current_tenant_slug', true)`. The application layer needs a clean way to set this on each connection. Three candidates considered:

- **`SET LOCAL app.current_tenant_slug = 'phill'`** — standard Postgres, transaction-scoped, but supabase-py doesn't easily expose raw SQL outside RPC. Rejected.
- **Direct `set_config()` builtin via RPC** — would need supabase-py to call `set_config('app.current_tenant_slug', slug, true)` as a function call. Supabase RPC only invokes user-defined functions, not Postgres builtins directly. Rejected.
- **Thin user-defined wrapper `set_app_tenant(slug text)`** — ADOPTED.

Phase 1 migration appends:

```sql
create or replace function public.set_app_tenant(slug text)
returns void
language sql
security definer
set search_path = public
as $$
  select set_config('app.current_tenant_slug', slug, true);
$$;

revoke all on function public.set_app_tenant(text) from public;
grant execute on function public.set_app_tenant(text) to authenticated, service_role;
```

Application use:

```python
client.rpc("set_app_tenant", {"slug": tenant_slug}).execute()
```

`Memory.__init__(tenant_slug=...)` calls this once per instance. The `db_session` middleware from Phase 5-6 wraps it as a contextmanager for ad-hoc cross-tenant operations. The `set_config(..., is_local=true)` 3rd arg scopes the setting to the current transaction, so RLS isolation is preserved across pooled connections.

### 2. `memory.is_blocked(fingerprint, tenant_slug) -> bool` — add to Phase 1 memory.py

`suggester._rank` (Phase 5-6) calls `memory.is_blocked(fp)` to filter previously-rejected suggestions. The original V0 plan referenced this method but never defined it. Resolution: add as the **fifth** method in Phase 1's Task 3 (alongside `get_pause_state`, `set_pause_state`, `record_message`, `get_message_for_suggestion`).

Body:

```python
def is_blocked(self, fingerprint: str, tenant_slug: str) -> bool:
    """True if a 'never' rule matches this fingerprint for this tenant."""
    r = (self.client.table("pilot_preferences")
         .select("rule")
         .eq("tenant_slug", tenant_slug)
         .eq("fingerprint_pattern", fingerprint)
         .eq("rule", "never")
         .limit(1)
         .execute())
    return bool(r.data)
```

Test (appended to Phase 1 Task 3 Step 1's failing-test block):

```python
def test_is_blocked_returns_true_when_never_rule_exists():
    c = MagicMock()
    c.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"rule": "never"}
    ]
    with patch.object(m, "_client", return_value=c):
        assert m.Memory().is_blocked("linear:RA-1234", "phill") is True

def test_is_blocked_returns_false_when_no_rule():
    c = MagicMock()
    c.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
    with patch.object(m, "_client", return_value=c):
        assert m.Memory().is_blocked("linear:RA-1234", "phill") is False
```

Note for implementer: this adds 2 tests + 1 method to Phase 1 Task 3. Total Phase 1 method count becomes 5 (was 4 in the rewritten plan). Self-review pass criteria stay the same.

## Consequences

**Easier:**
- Tenant context set with a single one-line RPC call from any caller (memory.py, scheduler.py, suggester.py, digest.py, callbacks).
- `is_blocked` localised to memory.py — single source of truth for "did the user reject this fingerprint before?".
- Both decisions align with substrate-change discipline #2 (source-restore before refactor): no .pyc-only paths, no service-role bypasses, no fragile session-state assumptions.

**Harder:**
- One extra Postgres function to maintain (security definer + grant). Phase 7-8 pgTAP guardrail should assert this function exists with the correct signature + security mode.
- `is_blocked` short-circuits before suggestions reach the composer. Phase 5-6 must wire it before `_rank` returns, not after.

**Now hard to undo:**
- `set_app_tenant` function name is the durable API contract for tenant context. Renaming breaks every caller across the codebase.
- The 5-method memory.py shape is the durable contract for Phase 2-6 callers.

## Cross-refs

- [[adrs/002-tenant-identification]] — parent decision that this implements.
- [[adrs/003-interactive-game-mode]] — `is_blocked` complements `pause_state` (pause-state halts emission; `is_blocked` filters specific fingerprints from emission).
- [[pilot-v1-phase-1]] · [[pilot-v1-phase-5-6]] — plans that reference these helpers.
- [[feedback-substrate-change-discipline]] — #2 source-restore before refactor (no .pyc-only paths).
- [[feedback-tight-code]] — `set_app_tenant` is 6 lines; `is_blocked` is 8 lines. Both within budget.
