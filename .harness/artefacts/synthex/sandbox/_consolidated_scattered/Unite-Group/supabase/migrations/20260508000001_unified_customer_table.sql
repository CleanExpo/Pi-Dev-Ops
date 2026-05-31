-- Unite-Group Unified Customer Table
-- Purpose: Platform data foundation — one customer record linked to all Unite-Group products
-- This single table makes cross-sell visible and NRR calculable for M&A diligence
-- Board decision: 2026-05-08

CREATE TABLE IF NOT EXISTS unified_customers (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  -- Identity
  name TEXT NOT NULL,
  email TEXT UNIQUE NOT NULL,
  phone TEXT,
  company TEXT,

  -- Geography
  country TEXT DEFAULT 'AU',
  state TEXT,

  -- Unite-Group product subscriptions (which products they use)
  uses_restore_assist BOOLEAN DEFAULT FALSE,
  uses_nrpg BOOLEAN DEFAULT FALSE,
  uses_synthex BOOLEAN DEFAULT FALSE,
  uses_carsi BOOLEAN DEFAULT FALSE,
  uses_ccw_crm BOOLEAN DEFAULT FALSE,
  uses_unite_crm BOOLEAN DEFAULT FALSE,

  -- External product IDs for cross-referencing
  restore_assist_user_id TEXT,
  synthex_account_id TEXT,
  ccw_crm_customer_id TEXT,
  stripe_customer_id TEXT,

  -- Revenue signals
  total_arr_aud NUMERIC(12,2) DEFAULT 0,
  nrr_pct NUMERIC(5,2),               -- Net Revenue Retention %
  product_count INTEGER GENERATED ALWAYS AS (
    (uses_restore_assist::int + uses_nrpg::int + uses_synthex::int +
     uses_carsi::int + uses_ccw_crm::int + uses_unite_crm::int)
  ) STORED,

  -- Lifecycle
  first_product_at TIMESTAMPTZ,
  last_active_at TIMESTAMPTZ,
  churn_risk TEXT CHECK (churn_risk IN ('low', 'medium', 'high', 'churned')),

  -- Audit
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- CCW is the first external customer — insert as the seed record
INSERT INTO unified_customers (
  name, email, company, country, state,
  uses_ccw_crm, uses_synthex,
  ccw_crm_customer_id,
  total_arr_aud, churn_risk,
  first_product_at, last_active_at
) VALUES (
  'Carpet Cleaners Warehouse', 'contact@ccw.com.au',
  'Carpet Cleaners Warehouse', 'AU', 'QLD',
  TRUE, TRUE,
  'ccw-crm-001',
  2400.00, 'low',
  '2026-05-03', NOW()
) ON CONFLICT (email) DO NOTHING;

-- Indexes for M&A diligence queries (cross-sell reports run fast)
CREATE INDEX idx_unified_customers_product_count ON unified_customers (product_count DESC);
CREATE INDEX idx_unified_customers_arr ON unified_customers (total_arr_aud DESC);
CREATE INDEX idx_unified_customers_churn ON unified_customers (churn_risk);
CREATE UNIQUE INDEX idx_unified_customers_email ON unified_customers (email);

-- Row-level security
ALTER TABLE unified_customers ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Service role full access" ON unified_customers;
CREATE POLICY "Service role full access" ON unified_customers
  USING (auth.role() = 'service_role');
DROP POLICY IF EXISTS "Authenticated read own org" ON unified_customers;
CREATE POLICY "Authenticated read own org" ON unified_customers
  FOR SELECT USING (auth.role() = 'authenticated');

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$ BEGIN NEW.updated_at = NOW(); RETURN NEW; END; $$ LANGUAGE plpgsql;
CREATE TRIGGER unified_customers_updated_at
  BEFORE UPDATE ON unified_customers
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

COMMENT ON TABLE unified_customers IS
  'Platform data foundation: one record per customer, linked to all Unite-Group products.
   product_count > 1 = cross-sell proof for M&A diligence. NRR tracked here.';
