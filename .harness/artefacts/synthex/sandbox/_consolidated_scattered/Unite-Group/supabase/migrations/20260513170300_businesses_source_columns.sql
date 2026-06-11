-- Pillar 3 (UNI-1947) — partial schema extension for businesses.
--
-- Adds the GitHub + Linear source-link columns plus the is_sandbox flag now.
-- The Vercel / Railway / Supabase-Management source columns land in a separate
-- commit once those tokens are minted (see plan task 3.1 full spec).

ALTER TABLE public.businesses
  ADD COLUMN IF NOT EXISTS github_repo     TEXT,
  ADD COLUMN IF NOT EXISTS linear_team_id  TEXT,
  ADD COLUMN IF NOT EXISTS is_sandbox      BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN public.businesses.github_repo IS
  'GitHub repo in owner/repo form, e.g. CleanExpo/Synthex. NULL means not configured.';
COMMENT ON COLUMN public.businesses.linear_team_id IS
  'Linear team UUID (not the short key). NULL means not configured.';
COMMENT ON COLUMN public.businesses.is_sandbox IS
  'TRUE for sandbox / placeholder rows. Excluded from dashboard listings by /api/empire/businesses.';

-- Seed the 6 canonical Main-Account brand rows with verified identifiers.
-- Sources verified 2026-05-13 via `gh repo view` and Linear GraphQL teams query.
-- Twin rows (older seed copies under aliased slugs like 'dr', 'nrpg', 'restore', 'ccw')
-- are intentionally left untouched here — they will be filtered out by the
-- existing slug-based dedupe + the new is_sandbox flag once Phill flips it.
UPDATE public.businesses SET
  github_repo    = 'CleanExpo/Synthex',
  linear_team_id = 'b887971b-6761-4260-a111-b94dbb628ebe'
WHERE slug = 'synthex';

UPDATE public.businesses SET
  github_repo    = 'CleanExpo/RestoreAssist',
  linear_team_id = 'a8a52f07-63cf-4ece-9ad2-3e3bd3c15673'
WHERE slug = 'restoreassist';

UPDATE public.businesses SET
  github_repo    = 'CleanExpo/Disaster-Recovery',
  linear_team_id = '43811130-ac12-47d3-9433-330320a76205'
WHERE slug = 'disaster-recovery';

UPDATE public.businesses SET
  github_repo    = 'CleanExpo/DR-NRPG',
  linear_team_id = '43811130-ac12-47d3-9433-330320a76205'
WHERE slug = 'dr-nrpg';

UPDATE public.businesses SET
  github_repo    = 'CleanExpo/CARSI',
  linear_team_id = '91b3cd04-86eb-422d-81e2-9aa37db2f2f5'
WHERE slug = 'carsi';

UPDATE public.businesses SET
  github_repo    = 'CleanExpo/CCW-CRM',
  linear_team_id = 'ab9c7810-4dd6-4ce2-8e8f-e1fc94c6b88b'
WHERE slug = 'ccw-crm';
