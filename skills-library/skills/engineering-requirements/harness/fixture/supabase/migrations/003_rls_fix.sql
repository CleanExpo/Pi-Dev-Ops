-- Tenant-scoped replacement for the permissive policy in 002.
DROP POLICY IF EXISTS "Anon read access" ON public.reports;

CREATE POLICY reports_tenant_select ON public.reports
  FOR SELECT TO authenticated
  USING (tenant_id IN (SELECT tenant_id FROM public.user_tenant_access WHERE user_id = auth.uid()));

REVOKE ALL ON public.reports FROM anon;
