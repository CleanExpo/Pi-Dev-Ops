// System Health aggregator tests.
//
// Strategy: import `computeSystemHealth` directly so we don't have to mock the
// 30s cache or NextResponse. Mock `getAdminClient` and global fetch for every
// downstream signal so we can drive each one to ok / warn / err independently
// and then assert the overall roll-up.

import { computeSystemHealth } from '../_helpers';

// ---- Supabase mock plumbing ----

const businessesLimitChain = jest.fn();
const snapshotsOrderChain = jest.fn();

jest.mock('@/lib/supabase/admin', () => {
  return {
    getAdminClient: () => ({
      from: (table: string) => {
        if (table === 'businesses') {
          return {
            select: () => ({
              limit: businessesLimitChain,
            }),
          };
        }
        if (table === 'pi_ceo_health_snapshots') {
          return {
            select: () => ({
              order: snapshotsOrderChain,
            }),
          };
        }
        throw new Error(`Unexpected table: ${table}`);
      },
    }),
  };
});

// ---- Adapter response driver ----
//
// system-health now probes each source adapter exactly ONCE (Synthex canary).
// The `integrations` signal measures adapter health, NOT brand-content health:
//   - Adapter returns a status field (any of ok/warn/err/unknown) → adapter ok
//   - Adapter route 5xx/timeout/garbled body                       → adapter err
//
// Test driver: each kind gets either an adapter "body status" string (the
// adapter is alive, returning content with this status) or the literal value
// 'ROUTE_DOWN' (the adapter route itself 5xx's — adapter is broken).

type AdapterBodyStatus = 'ok' | 'warn' | 'err' | 'unknown';
type AdapterDriver = AdapterBodyStatus | 'ROUTE_DOWN';

const adapterResponses: Record<'github' | 'linear' | 'vercel' | 'railway' | 'supabase', AdapterDriver> = {
  github: 'ok',
  linear: 'ok',
  vercel: 'ok',
  railway: 'ok',
  supabase: 'ok',
};

function setAdapter(kind: keyof typeof adapterResponses, resp: AdapterDriver) {
  adapterResponses[kind] = resp;
}

function resetAdapters() {
  adapterResponses.github = 'ok';
  adapterResponses.linear = 'ok';
  adapterResponses.vercel = 'ok';
  adapterResponses.railway = 'ok';
  adapterResponses.supabase = 'ok';
}

function adapterResponseFor(url: string): AdapterDriver | null {
  const match = url.match(/\/api\/empire\/sources\/(github|linear|vercel|railway|supabase)\/([^/?#]+)/);
  if (!match) return null;
  const kind = match[1] as keyof typeof adapterResponses;
  return adapterResponses[kind];
}

const realFetch = global.fetch;

beforeEach(() => {
  businessesLimitChain.mockReset();
  snapshotsOrderChain.mockReset();
  resetAdapters();
  // Default: every downstream API call returns a happy response.
  // Individual tests override per-URL.
  global.fetch = jest.fn(async () => new Response('{}', { status: 200 })) as unknown as typeof fetch;

  // Default env: every integration has a token so probeIntegrations returns ok.
  process.env.VERCEL_INTEGRATION_TOKEN = 'tk';
  process.env.RAILWAY_API_TOKEN = 'tk';
  process.env.SUPABASE_ACCESS_TOKEN = 'tk';
  process.env.PI_CEO_API_KEY = 'tk';
});

afterEach(() => {
  global.fetch = realFetch;
  delete process.env.VERCEL_INTEGRATION_TOKEN;
  delete process.env.RAILWAY_API_TOKEN;
  delete process.env.SUPABASE_ACCESS_TOKEN;
  delete process.env.PI_CEO_API_KEY;
});

// ---- Helpers ----

function happyDatabase() {
  // Supabase head:true query returns { error: null }
  businessesLimitChain.mockResolvedValue({ error: null });
}

function brokenDatabase() {
  businessesLimitChain.mockResolvedValue({ error: { message: 'connection refused' } });
}

function happyScanner() {
  // Fresh snapshot now → ok
  const now = new Date().toISOString();
  snapshotsOrderChain.mockResolvedValue({
    data: [
      { project_id: 'synthex', snapshot_at: now },
      { project_id: 'ccw-crm', snapshot_at: now },
    ],
    error: null,
  });
}

function staleScanner() {
  // 10-day-old snapshot → err
  const tenDaysAgo = new Date(Date.now() - 10 * 86_400_000).toISOString();
  snapshotsOrderChain.mockResolvedValue({
    data: [{ project_id: 'synthex', snapshot_at: tenDaysAgo }],
    error: null,
  });
}

function warnScanner() {
  // 2-day-old snapshot → warn (>24h, <7d)
  const twoDaysAgo = new Date(Date.now() - 2 * 86_400_000).toISOString();
  snapshotsOrderChain.mockResolvedValue({
    data: [{ project_id: 'synthex', snapshot_at: twoDaysAgo }],
    error: null,
  });
}

function setupFetch(overrides: Record<string, (url: string) => Response | Promise<Response>>) {
  global.fetch = jest.fn(async (url: string | URL | Request) => {
    const u = typeof url === 'string' ? url : url instanceof URL ? url.toString() : url.url;
    for (const [pattern, fn] of Object.entries(overrides)) {
      if (u.includes(pattern)) return fn(u);
    }
    // Source adapter probes: honour the setAdapter(...) per-kind driver.
    const driver = adapterResponseFor(u);
    if (driver !== null) {
      if (driver === 'ROUTE_DOWN') {
        // Adapter route is broken on our side — simulates 5xx.
        return new Response('Internal Server Error', { status: 500 });
      }
      return new Response(JSON.stringify({ status: driver }), { status: 200 });
    }
    if (u.includes('/api/empire/businesses')) {
      return new Response(JSON.stringify({ businesses: [{ overall_health: 90 }, { overall_health: 85 }] }), { status: 200 });
    }
    // Vercel deployments default → a single READY deployment, so deploys signal = ok.
    if (u.includes('api.vercel.com/v6/deployments')) {
      return new Response(
        JSON.stringify({ deployments: [{ uid: 'd1', url: 'x', state: 'READY', created: Date.now() }] }),
        { status: 200 },
      );
    }
    return new Response('{}', { status: 200 });
  }) as unknown as typeof fetch;
}

// ---- Test cases ----

describe('computeSystemHealth', () => {
  it('returns overall ok when every signal is healthy', async () => {
    happyDatabase();
    happyScanner();
    setupFetch({});

    const result = await computeSystemHealth('http://localhost:3000');
    expect(result.overall).toBe('ok');
    expect(result.signals.database.status).toBe('ok');
    expect(result.signals.api.status).toBe('ok');
    expect(result.signals.integrations.status).toBe('ok');
    expect(result.signals.businesses.status).toBe('ok');
    expect(result.signals.pi_ceo_scanner.status).toBe('ok');
    expect(result.signals.deploys.status).toBe('ok');
    expect(result.computed_at).toMatch(/^\d{4}-\d{2}-\d{2}T/);
  });

  it('rolls up to err when one signal errors', async () => {
    brokenDatabase(); // DB returns err
    happyScanner();
    setupFetch({});

    const result = await computeSystemHealth('http://localhost:3000');
    expect(result.signals.database.status).toBe('err');
    expect(result.overall).toBe('err');
  });

  it('rolls up to warn when one signal warns and rest ok', async () => {
    happyDatabase();
    warnScanner(); // scanner 2d old → warn
    setupFetch({});

    const result = await computeSystemHealth('http://localhost:3000');
    expect(result.signals.pi_ceo_scanner.status).toBe('warn');
    expect(result.overall).toBe('warn');
  });

  it('marks deploys err when Vercel returns ERROR state', async () => {
    happyDatabase();
    happyScanner();
    setupFetch({
      'api.vercel.com/v6/deployments': () =>
        new Response(
          JSON.stringify({ deployments: [{ uid: 'd1', url: 'x', state: 'ERROR', created: Date.now() }] }),
          { status: 200 },
        ),
    });

    const result = await computeSystemHealth('http://localhost:3000');
    expect(result.signals.deploys.status).toBe('err');
    expect(result.signals.deploys.state).toBe('ERROR');
    expect(result.overall).toBe('err');
  });

  it('marks deploys warn when Vercel returns BUILDING state', async () => {
    happyDatabase();
    happyScanner();
    setupFetch({
      'api.vercel.com/v6/deployments': () =>
        new Response(
          JSON.stringify({ deployments: [{ uid: 'd1', url: 'x', state: 'BUILDING', created: Date.now() }] }),
          { status: 200 },
        ),
    });

    const result = await computeSystemHealth('http://localhost:3000');
    expect(result.signals.deploys.status).toBe('warn');
    expect(result.signals.deploys.summary).toContain('deploying now');
  });

  it('rolls up integrations to err when one source adapter ROUTE 5xx fails', async () => {
    happyDatabase();
    happyScanner();
    setupFetch({});
    // GitHub adapter route returns HTTP 500 → adapter broken.
    setAdapter('github', 'ROUTE_DOWN');

    const result = await computeSystemHealth('http://localhost:3000');
    expect(result.signals.integrations.github).toBe('err');
    expect(result.signals.integrations.status).toBe('err');
    expect(result.signals.integrations.summary).toContain('github');
    expect(result.signals.integrations.summary).toContain('down');
  });

  it('integrations STAYS ok when adapter returns body status=err (brand-content red, adapter alive)', async () => {
    // The exact misleading-signal bug: every adapter is responding correctly,
    // but each happens to report a brand-level err inside the JSON body. The
    // adapters themselves are healthy, so integrations = ok. The business-level
    // err shows up in `businesses`, not `integrations`.
    happyDatabase();
    happyScanner();
    setupFetch({});
    setAdapter('github', 'err');
    setAdapter('linear', 'err');
    setAdapter('vercel', 'err');
    setAdapter('railway', 'err');
    setAdapter('supabase', 'err');

    const result = await computeSystemHealth('http://localhost:3000');
    expect(result.signals.integrations.status).toBe('ok');
    expect(result.signals.integrations.github).toBe('ok');
    expect(result.signals.integrations.linear).toBe('ok');
    expect(result.signals.integrations.vercel).toBe('ok');
    expect(result.signals.integrations.railway).toBe('ok');
    expect(result.signals.integrations.supabase).toBe('ok');
    expect(result.signals.integrations.summary).toBe('5/5 source adapters healthy');
  });

  it('integrations summary lists multiple down adapters', async () => {
    happyDatabase();
    happyScanner();
    setupFetch({});
    setAdapter('vercel', 'ROUTE_DOWN');
    setAdapter('railway', 'ROUTE_DOWN');

    const result = await computeSystemHealth('http://localhost:3000');
    expect(result.signals.integrations.status).toBe('err');
    expect(result.signals.integrations.summary).toMatch(/3\/5.*vercel.*railway.*adapters down/);
  });

  it('classifies businesses by health buckets', async () => {
    happyDatabase();
    happyScanner();
    setupFetch({
      '/api/empire/businesses': () =>
        new Response(
          JSON.stringify({
            businesses: [
              { overall_health: 90 }, // ok
              { overall_health: 75 }, // warn
              { overall_health: 40 }, // err
              { overall_health: null }, // skipped
            ],
          }),
          { status: 200 },
        ),
    });

    const result = await computeSystemHealth('http://localhost:3000');
    expect(result.signals.businesses.total).toBe(4);
    expect(result.signals.businesses.ok_count).toBe(1);
    expect(result.signals.businesses.warn_count).toBe(1);
    expect(result.signals.businesses.err_count).toBe(1);
    expect(result.signals.businesses.status).toBe('err');
  });

  it('marks an integration ok even when the canary brand reports unknown content (adapter still alive)', async () => {
    // Adapter route returns { status: 'unknown' } — the body status is irrelevant
    // for the integrations signal. The adapter route worked → adapter is healthy.
    happyDatabase();
    happyScanner();
    setupFetch({});
    setAdapter('vercel', 'unknown');

    const result = await computeSystemHealth('http://localhost:3000');
    expect(result.signals.integrations.vercel).toBe('ok');
    expect(result.signals.integrations.status).toBe('ok');
  });

  it('marks scanner err when snapshots are >7d old', async () => {
    happyDatabase();
    staleScanner();
    setupFetch({});

    const result = await computeSystemHealth('http://localhost:3000');
    expect(result.signals.pi_ceo_scanner.status).toBe('err');
    expect(result.signals.pi_ceo_scanner.stale_brands).toBeGreaterThan(0);
    expect(result.overall).toBe('err');
  });

  it('flags database warn at 300-1000ms latency', async () => {
    // Simulate latency by delaying the mocked supabase response.
    businessesLimitChain.mockImplementation(
      () =>
        new Promise(resolve => {
          setTimeout(() => resolve({ error: null }), 350);
        }),
    );
    happyScanner();
    setupFetch({});

    const result = await computeSystemHealth('http://localhost:3000');
    expect(result.signals.database.status).toBe('warn');
    expect(result.signals.database.latency_ms).toBeGreaterThanOrEqual(300);
  });

  it('does NOT flag database warn at 201ms latency (real-world fine)', async () => {
    businessesLimitChain.mockImplementation(
      () =>
        new Promise(resolve => {
          setTimeout(() => resolve({ error: null }), 210);
        }),
    );
    happyScanner();
    setupFetch({});

    const result = await computeSystemHealth('http://localhost:3000');
    expect(result.signals.database.status).toBe('ok');
  });

  it('integrations stays ok when every adapter returns body=unknown (routes alive, nothing configured downstream)', async () => {
    happyDatabase();
    happyScanner();
    setupFetch({});
    setAdapter('github', 'unknown');
    setAdapter('linear', 'unknown');
    setAdapter('vercel', 'unknown');
    setAdapter('railway', 'unknown');
    setAdapter('supabase', 'unknown');

    const result = await computeSystemHealth('http://localhost:3000');
    // All adapter routes responded — every row = ok regardless of body content.
    expect(result.signals.integrations.github).toBe('ok');
    expect(result.signals.integrations.linear).toBe('ok');
    expect(result.signals.integrations.vercel).toBe('ok');
    expect(result.signals.integrations.railway).toBe('ok');
    expect(result.signals.integrations.supabase).toBe('ok');
    expect(result.signals.integrations.status).toBe('ok');
  });

  it('integrations err when one adapter route is down even if the others return body=unknown', async () => {
    happyDatabase();
    happyScanner();
    setupFetch({});
    setAdapter('github', 'unknown');
    setAdapter('linear', 'unknown');
    setAdapter('vercel', 'unknown');
    setAdapter('railway', 'unknown');
    setAdapter('supabase', 'ROUTE_DOWN');

    const result = await computeSystemHealth('http://localhost:3000');
    expect(result.signals.integrations.supabase).toBe('err');
    expect(result.signals.integrations.github).toBe('ok');
    expect(result.signals.integrations.status).toBe('err');
  });

  it('overall does NOT flip to err just because integrations is unknown', async () => {
    // All sources unknown, everything else ok → overall ok (no real failure).
    happyDatabase();
    happyScanner();
    setupFetch({});
    setAdapter('github', 'unknown');
    setAdapter('linear', 'unknown');
    setAdapter('vercel', 'unknown');
    setAdapter('railway', 'unknown');
    setAdapter('supabase', 'unknown');

    const result = await computeSystemHealth('http://localhost:3000');
    expect(result.overall).toBe('ok');
  });
});
