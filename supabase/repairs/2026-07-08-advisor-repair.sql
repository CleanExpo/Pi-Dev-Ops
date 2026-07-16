-- Pi CEO Supabase advisor repair — 2026-07-08
-- One-shot, idempotent. Apply in the SQL Editor (project zbryrmxmgfmslqzizsto).
-- Context: dashboard showed 42.7% request success rate; security advisors showed
-- 4 ERROR-level RLS-disabled tables, 6 SECURITY DEFINER views, and an
-- anon-executable SECURITY DEFINER function. The mesh_agents 409 storm is fixed
-- in code (routes/mesh.py on_conflict); margot_research_queue + mesh policies
-- live in the canonical files (supabase/migration.sql, mesh/schema/0001).
-- This file holds ONLY the cross-app objects Pi-Dev-Ops does not own, so they
-- stay out of the canonical Pi-Dev-Ops migration.

-- 1. RLS-disabled ERROR advisors — every backend writes via service_role
--    (bypasses RLS), so enabling closes anon exposure without breaking writers.
ALTER TABLE public.heartbeat_log     ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.workflow_runs     ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.triage_log        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.claude_api_costs  ENABLE ROW LEVEL SECURITY;

-- 2. SECURITY DEFINER view ERRORs — flip to invoker semantics (PG15+),
--    preserving definitions; no recreation needed.
ALTER VIEW public.v_google_identity   SET (security_invoker = on);
ALTER VIEW public.v_gcp_project       SET (security_invoker = on);
ALTER VIEW public.v_vercel_project    SET (security_invoker = on);
ALTER VIEW public.v_oauth_client      SET (security_invoker = on);
ALTER VIEW public.v_portfolio_service SET (security_invoker = on);
ALTER VIEW public.mesh_fleet          SET (security_invoker = on);

-- 3. set_app_tenant is SECURITY DEFINER and executable by anon/authenticated
--    via /rest/v1/rpc/. The pilot clients call it with the service key;
--    nothing legitimate uses anon here.
REVOKE EXECUTE ON FUNCTION public.set_app_tenant(text) FROM anon, authenticated;

-- 4. Mutable search_path WARNs on the two trigger functions (bodies only touch
--    NEW.* and now(); pinning is safe).
ALTER FUNCTION public.intake_set_updated_at() SET search_path = '';
ALTER FUNCTION public.cc_update_updated_at_column() SET search_path = '';

-- Deliberately NOT included: moving the `vector` extension out of public
-- (WARN-level) — disruptive to dependent columns; schedule separately if wanted.
