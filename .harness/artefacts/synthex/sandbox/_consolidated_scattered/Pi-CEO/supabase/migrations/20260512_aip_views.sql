-- AIP Day-1 — per-kind views over aip_entities.
-- Spec: ~/2nd Brain/2nd Brain/Wiki/aip-first-slice-schema.md § 2 "First-slice entity types".
-- One view per kind, projecting properties jsonb fields as typed columns. Exposed under
-- /rest/v1/v_<kind> via PostgREST. Hot fields can later promote to generated columns
-- without breaking these views.

-- GoogleIdentity:
--   email, kind in {workspace,personal,service}, onepassword_item_id?, recovery_email?, last_active_at?
create or replace view v_google_identity as
select
  e.uri,
  e.id,
  (e.properties->>'email')                       as email,
  (e.properties->>'identity_kind')               as identity_kind,
  (e.properties->>'onepassword_item_id')         as onepassword_item_id,
  (e.properties->>'recovery_email')              as recovery_email,
  (e.properties->>'last_active_at')::timestamptz as last_active_at,
  e.source,
  e.created_at,
  e.updated_at
from aip_entities e
where e.kind = 'GoogleIdentity';

-- GcpProject:
--   project_number, project_id, owner_identity_uri, billing_account?
create or replace view v_gcp_project as
select
  e.uri,
  e.id,
  (e.properties->>'project_number')     as project_number,
  (e.properties->>'project_id')         as project_id,
  (e.properties->>'owner_identity_uri') as owner_identity_uri,
  (e.properties->>'billing_account')    as billing_account,
  e.source,
  e.created_at,
  e.updated_at
from aip_entities e
where e.kind = 'GcpProject';

-- VercelProject:
--   vercel_project_id, slug, team_id, current_git_sha?, framework
create or replace view v_vercel_project as
select
  e.uri,
  e.id,
  (e.properties->>'vercel_project_id') as vercel_project_id,
  (e.properties->>'slug')              as slug,
  (e.properties->>'team_id')           as team_id,
  (e.properties->>'current_git_sha')   as current_git_sha,
  (e.properties->>'framework')         as framework,
  e.source,
  e.created_at,
  e.updated_at
from aip_entities e
where e.kind = 'VercelProject';

-- OAuthClient:
--   client_id, secret_rotated_at?, authorized_origins[], authorized_redirect_uris[], status, gcp_project_uri
create or replace view v_oauth_client as
select
  e.uri,
  e.id,
  (e.properties->>'client_id')                                   as client_id,
  (e.properties->>'secret_rotated_at')::timestamptz              as secret_rotated_at,
  (e.properties->'authorized_origins')                           as authorized_origins,
  (e.properties->'authorized_redirect_uris')                     as authorized_redirect_uris,
  (e.properties->>'status')                                      as status,
  (e.properties->>'gcp_project_uri')                             as gcp_project_uri,
  e.source,
  e.created_at,
  e.updated_at
from aip_entities e
where e.kind = 'OAuthClient';

-- PortfolioService:
--   slug (dr/nrpg/carsi/ccw/synthex/unite/ra), brand_name, current_git_sha?, status, wiki_page_path?
create or replace view v_portfolio_service as
select
  e.uri,
  e.id,
  (e.properties->>'slug')            as slug,
  (e.properties->>'brand_name')      as brand_name,
  (e.properties->>'current_git_sha') as current_git_sha,
  (e.properties->>'status')          as status,
  (e.properties->>'wiki_page_path')  as wiki_page_path,
  e.source,
  e.created_at,
  e.updated_at
from aip_entities e
where e.kind = 'PortfolioService';
