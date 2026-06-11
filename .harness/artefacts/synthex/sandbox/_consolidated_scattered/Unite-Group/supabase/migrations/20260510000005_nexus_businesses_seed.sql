-- Nexus Wave 1: Seed pi_ceo_key + arr_aud on existing business rows
-- businesses table is multi-tenant (unique on founder_id+slug); we update by slug match
-- Board Mandate: Nexus Wave 1

UPDATE public.businesses SET pi_ceo_key = 'synthex',           arr_aud = 0     WHERE slug = 'synthex'  AND pi_ceo_key IS NULL;
UPDATE public.businesses SET pi_ceo_key = 'carsi',             arr_aud = 0     WHERE slug = 'carsi'    AND pi_ceo_key IS NULL;
UPDATE public.businesses SET pi_ceo_key = 'ccw-crm',           arr_aud = 33000 WHERE slug = 'ccw'      AND pi_ceo_key IS NULL;
UPDATE public.businesses SET pi_ceo_key = 'disaster-recovery', arr_aud = 0     WHERE slug = 'dr'       AND pi_ceo_key IS NULL;
UPDATE public.businesses SET pi_ceo_key = 'dr-nrpg',           arr_aud = 0     WHERE slug = 'nrpg'     AND pi_ceo_key IS NULL;
UPDATE public.businesses SET pi_ceo_key = 'restoreassist',     arr_aud = 0     WHERE slug = 'restore'  AND pi_ceo_key IS NULL;

-- Seed CCW as first Nexus paying client
INSERT INTO public.nexus_clients (slug, company_name, contact_email, plan, status, pi_ceo_key, onboarded_at)
VALUES ('ccw-crm', 'Carpet Cleaners Warehouse', 'contact@ccw.com.au', 'pro', 'active', 'ccw-crm', '2026-05-03')
ON CONFLICT (slug) DO NOTHING;
