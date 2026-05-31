-- Pillar 3 (UNI-1947) — second wave of source-link columns on public.businesses.
--
-- Adds vercel_project, railway_service_id, supabase_project_ref. Pairs with the
-- existing GitHub + Linear adapter routes; powers the new Vercel / Railway /
-- Supabase-Management adapter routes in this commit train.
--
-- Values seeded below are verified 2026-05-13 via:
--   GET https://api.vercel.com/v9/projects
--   POST https://backboard.railway.app/graphql/v2  (services list)
--   GET https://api.supabase.com/v1/projects
-- NO INVENTED IDS — any brand without a clear upstream match is left NULL and
-- will surface a truthful "not configured" empty-state in the dashboard.

ALTER TABLE public.businesses
  ADD COLUMN IF NOT EXISTS vercel_project        TEXT,
  ADD COLUMN IF NOT EXISTS railway_service_id    TEXT,
  ADD COLUMN IF NOT EXISTS supabase_project_ref  TEXT;

COMMENT ON COLUMN public.businesses.vercel_project IS
  'Vercel project ID (prj_...) or slug. NULL means not configured — adapter returns status=unknown.';
COMMENT ON COLUMN public.businesses.railway_service_id IS
  'Railway service UUID. NULL means not configured.';
COMMENT ON COLUMN public.businesses.supabase_project_ref IS
  'Supabase project ref (20-char). NULL means not configured.';

-- Seed real, verified values for the six canonical brand rows.

UPDATE public.businesses SET
  vercel_project       = 'prj_gbQmHn6quoHgG3AswRrDoUlYaF40',
  supabase_project_ref = 'znyjoyjsvjotlzjppzal'
WHERE slug = 'synthex';

UPDATE public.businesses SET
  vercel_project       = 'prj_Aw90JJ2x7mTMatTxa3ymgcU7WPV2',
  supabase_project_ref = 'udooysjajglluvuxkijp'
WHERE slug = 'restoreassist';

UPDATE public.businesses SET
  vercel_project       = 'prj_dvNqTXXZxYENjFozhFnqIO72ABhW',
  supabase_project_ref = 'zwzbglqzmpyfzdkblxyf'
WHERE slug = 'disaster-recovery';

UPDATE public.businesses SET
  vercel_project       = 'prj_15zLJSeVhpqXcWf1s2U1fHdIHOtw',
  supabase_project_ref = 'lccqasmurmsisnnjqqmr'
WHERE slug = 'dr-nrpg';

UPDATE public.businesses SET
  vercel_project       = 'prj_hIQAdXiHQGGec6nNKEGzn7SyMh9p',
  supabase_project_ref = 'ofzafxvxobjggjisrbsa'
WHERE slug = 'carsi';

UPDATE public.businesses SET
  vercel_project       = 'prj_oTCifkMVqP1NFoTJFBv6u82JmBYd',
  railway_service_id   = '5fa355c8-cb90-49fa-9b01-b0b01e9e78da',
  supabase_project_ref = 'vwfgksqkajnpfjospbpe'
WHERE slug = 'ccw-crm';
