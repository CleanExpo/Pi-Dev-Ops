-- ============================================================================
-- UNI-1947 Pillar 2 — Seed real portal_content for the 3 known portals
-- ============================================================================
-- Lifts the hardcoded content out of /clients/dimitri-itr/page.tsx and
-- /clients/bulcs-holdings/page.tsx into the portal_content JSONB column on
-- nexus_clients, so the post-refactor pages render IDENTICAL data without
-- any hardcoded arrays.
--
-- For bulcs-holdings: the row does not exist yet in nexus_clients (the page
-- predates the Unite-Group onboarding flow that creates rows), so we INSERT
-- with ON CONFLICT DO NOTHING then UPDATE the portal_content.
--
-- For ccw-crm: a row exists from prior onboarding. We seed minimal initial
-- content so /clients/ccw has something real to render — the existing
-- /clients/ccw page is owned by Toby and can be expanded separately.
--
-- All three UPDATEs are guarded with a WHERE portal_content = '{}'::jsonb
-- so re-running this migration never clobbers admin-edited content.
--
-- Per the no-mock-data rule: placeholder links (`href: "#"`) from the
-- original pages are deliberately omitted. Only real-URL links are seeded.
-- ============================================================================

-- ── bulcs-holdings — INSERT row if missing, then UPDATE portal_content ────────
INSERT INTO public.nexus_clients (
  slug, company_name, contact_name, contact_email, brand_config, status, plan
)
VALUES (
  'bulcs-holdings',
  'Bulcs Holdings',
  'Ivi Sims',
  'ivi@bulcsholdings.com',
  '{}'::jsonb,
  'active',
  'pro'
)
ON CONFLICT (slug) DO NOTHING;

-- ── dimitri-itr — seed from /clients/dimitri-itr/page.tsx ─────────────────────
UPDATE public.nexus_clients
SET portal_content = jsonb_build_object(
  'welcome_text',
  'Welcome, Duncan. Your ITR Platform engagement with Unite-Group is live. Kick-off Discovery starts the week of 19 May 2026 — first written status note Friday 23 May. Working MVP target lands Month 4–5; production launch around Month 8–10. Quality over rushing.',
  'deliverables', jsonb_build_array(
    jsonb_build_object('category', 'Discovery & Architecture Review', 'status', 'in-progress', 'detail', 'Months 1–2 — scope lock, integration map, ATO partner application kicks off (their queue is the slowest piece)'),
    jsonb_build_object('category', 'Brand & Button-Name Lock-In', 'status', 'in-progress', 'detail', 'Working name ''Otto'' — finalists: Otto / Sorted / Beau / Tick / Lodgey. Trademark + .com.au sweep included.'),
    jsonb_build_object('category', 'ATO MyGov Partner Application', 'status', 'in-progress', 'detail', 'Started Month 1 — ATO controls their own timeline. Blocks live pre-fill until approved.'),
    jsonb_build_object('category', 'DIMITRI Pre-fill Agent', 'status', 'planned', 'detail', 'One-question-at-a-time interview, Y/N/Tell-me-more responses, D13 deductions, FBT / CGT / crypto curlies. Months 3–4.'),
    jsonb_build_object('category', 'TFN Custody + TASA Compliance Layer', 'status', 'planned', 'detail', 'TFNs never enter an LLM context window. TASA s90-5 boundary policed in copy + features. Months 3–4.'),
    jsonb_build_object('category', 'XPM Tax-Agent Handoff', 'status', 'planned', 'detail', 'Complete packet push to Xero Practice Manager so the tax agent''s team can run ID / AML / TFN and lodge. Months 5–6.'),
    jsonb_build_object('category', 'NOAH Post-Lodgement Agent', 'status', 'planned', 'detail', 'NOA trigger → Stripe fee gate → NOA delivery → 11 wealth-planning questions → referral booking → encrypted ZIP. Months 5–6.'),
    jsonb_build_object('category', 'Encrypted Client Envelope', 'status', 'planned', 'detail', 'AES-256-GCM, key tied to client email, no platform-side decrypt path. Months 5–6.'),
    jsonb_build_object('category', 'Approved-Website Embed Button', 'status', 'planned', 'detail', '1-line script for partner sites — brokers / banks / tax agents / financial planners / lawyers / employers. Per-partner attribution. Months 7–8.'),
    jsonb_build_object('category', 'First Partner Pilot', 'status', 'planned', 'detail', 'Sams Home Loans pilot integration. Months 7–8.'),
    jsonb_build_object('category', 'Production Rollout', 'status', 'planned', 'detail', 'Multi-partner expansion, additional tax-agent partners, marketing engine via Synthex. Months 9–12.')
  ),
  'touchpoints', jsonb_build_array(
    jsonb_build_object('name', 'Duncan Perkins Home Loan Essentials', 'domain', 'homeloanessentials.com.au', 'status', 'active'),
    jsonb_build_object('name', 'Sams Home Loans (pilot partner)', 'status', 'planned'),
    jsonb_build_object('name', 'BLinks tax agency', 'status', 'planned'),
    jsonb_build_object('name', 'Xero Practice Manager (handoff)', 'domain', 'xero.com', 'status', 'planned')
  ),
  'quick_links', jsonb_build_array(
    jsonb_build_object('label', 'ITR Platform Proposal', 'href', '/proposals/duncan-itr-platform-2026-05-13', 'note', 'Signed retainer terms — read first'),
    jsonb_build_object('label', 'Phill direct', 'href', 'mailto:contact@unite-group.in', 'note', 'contact@unite-group.in')
  )
)
WHERE slug = 'dimitri-itr'
  AND COALESCE(portal_content, '{}'::jsonb) = '{}'::jsonb;

-- ── bulcs-holdings — seed from /clients/bulcs-holdings/page.tsx ───────────────
UPDATE public.nexus_clients
SET portal_content = jsonb_build_object(
  'welcome_text',
  'Your AI-powered agency engagement is active. Here is the live status across all deliverables. Questions or feedback? Email your account manager at contact@unite-group.in',
  'deliverables', jsonb_build_array(
    jsonb_build_object('category', 'SEO / AEO / GEO', 'status', 'in-progress', 'detail', 'Baseline audit in progress — domains: bulcsholdings.com, moisturemeterexperts.com.au, aeroair.com.au'),
    jsonb_build_object('category', 'Brand Research', 'status', 'done', 'detail', 'Visual identity, tone, audience, and competitor analysis complete across all 5 divisions'),
    jsonb_build_object('category', 'LinkedIn Strategy', 'status', 'in-progress', 'detail', '4-post weekly calendar drafted — awaiting your review and approval'),
    jsonb_build_object('category', 'Video: LGR vs Desiccant', 'status', 'planned', 'detail', 'Storyboard complete — 8-10 min explainer for restoration contractors'),
    jsonb_build_object('category', 'Video: Moisture Documentation', 'status', 'planned', 'detail', 'Storyboard complete — 12 min insurance claims documentation guide'),
    jsonb_build_object('category', 'Video: IAQ for Building Managers', 'status', 'planned', 'detail', 'Storyboard complete — 10 min compliance guide for facility managers'),
    jsonb_build_object('category', 'Client Proposal', 'status', 'done', 'detail', '3-tier proposal document prepared — Foundation $1,500/mo, Growth $2,000/mo, Full Agency $2,500/mo')
  ),
  'touchpoints', jsonb_build_array(
    jsonb_build_object('name', 'Bulcs Holdings', 'domain', 'bulcsholdings.com', 'status', 'active'),
    jsonb_build_object('name', 'IAQ Ventilation', 'domain', 'iaqventilation.com.au', 'status', 'active'),
    jsonb_build_object('name', 'AeroAir', 'domain', 'aeroair.com.au', 'status', 'active'),
    jsonb_build_object('name', 'Moisture Meter Experts', 'domain', 'moisturemeterexperts.com.au', 'status', 'active'),
    jsonb_build_object('name', 'Air Purifier', 'domain', 'airpurifier.net.au', 'status', 'active')
  ),
  'quick_links', jsonb_build_array(
    jsonb_build_object('label', 'Your Website', 'href', 'https://bulcsholdings.com', 'note', 'bulcsholdings.com'),
    jsonb_build_object('label', 'Moisture Meter Experts', 'href', 'https://moisturemeterexperts.com.au', 'note', 'Primary e-commerce')
  )
)
WHERE slug = 'bulcs-holdings'
  AND COALESCE(portal_content, '{}'::jsonb) = '{}'::jsonb;

-- ── ccw-crm — seed minimal initial content ────────────────────────────────────
UPDATE public.nexus_clients
SET portal_content = jsonb_build_object(
  'welcome_text',
  'Welcome, Toby. Your CCW-CRM portal is active and your first paying engagement with Unite-Group is live. Status updates land here as we move through delivery milestones.',
  'deliverables', jsonb_build_array(
    jsonb_build_object('category', 'CCW-CRM Portal Build', 'status', 'done', 'detail', 'Tenant onboarding, magic-link auth, and live customer + ticketing surfaces shipped.'),
    jsonb_build_object('category', 'First Paying Engagement', 'status', 'done', 'detail', '$2,400/yr ARR active — CCW is Unite-Group''s first paying portfolio client.'),
    jsonb_build_object('category', 'Industry Association Roll-out', 'status', 'in-progress', 'detail', 'Founding the dominant ANZ cleaning/restoration industry body alongside CCW.')
  ),
  'touchpoints', jsonb_build_array(
    jsonb_build_object('name', 'Carpet Cleaners Warehouse', 'domain', 'ccwarehouse.com.au', 'status', 'active')
  ),
  'quick_links', jsonb_build_array(
    jsonb_build_object('label', 'CCW Portal', 'href', '/clients/ccw', 'note', 'Customer + ticketing surface')
  )
)
WHERE slug = 'ccw-crm'
  AND COALESCE(portal_content, '{}'::jsonb) = '{}'::jsonb;
