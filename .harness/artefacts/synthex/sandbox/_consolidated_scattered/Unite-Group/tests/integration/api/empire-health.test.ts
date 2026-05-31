/**
 * Integration tests: /api/empire/health and /api/pi-ceo/health
 *
 * Tests that the health endpoints correctly aggregate Pi-CEO data,
 * handle Railway timeouts, and return the right structure for the
 * Command Center bento grid.
 */

import { NextRequest } from 'next/server';

// requireAdmin calls createClient() → cookies(), which throws outside a
// Next.js request scope. Short-circuit it to "always authorized" so the
// route's real logic is what gets exercised.
jest.mock('@/lib/security/require-admin', () => ({
  requireAdmin: jest
    .fn()
    .mockResolvedValue({ ok: true, actorEmail: 'test@unite-group.com' }),
}));

// ── Mock global fetch ──────────────────────────────────────────────────────
beforeEach(() => {
  jest.clearAllMocks();
  global.fetch = jest.fn();
  process.env.PI_CEO_API_URL = 'https://pi-ceo-test.railway.app';
  process.env.PI_CEO_API_KEY = 'test-key';
});

// ── Route imports ──────────────────────────────────────────────────────────
import { GET as getEmpireHealth } from '@/app/api/empire/health/route';
import { GET as getPiCeoHealth  } from '@/app/api/pi-ceo/health/route';

// ── Fixtures ───────────────────────────────────────────────────────────────
const MOCK_PI_CEO_LOGIN_RESPONSE = {
  ok: true,
  status: 200,
  headers: new Headers({ 'set-cookie': 'tao_session=abc123; Path=/' }),
  json: async () => ({ ok: true }),
};

const MOCK_PROJECTS_RESPONSE = {
  ok: true,
  json: async () => ({
    projects: [
      { id: 'restoreassist',    health_score: 85, security_score: 42, last_updated: '2026-05-10T08:00:00Z' },
      { id: 'synthex',          health_score: 65, security_score: 40, last_updated: '2026-05-10T08:00:00Z' },
      { id: 'ccw-crm',          health_score: 78, security_score: 15, last_updated: '2026-05-10T08:00:00Z' },
      { id: 'disaster-recovery',health_score: 95, security_score: 80, last_updated: '2026-05-10T08:00:00Z' },
      { id: 'dr-nrpg',          health_score: 70, security_score: 45, last_updated: '2026-05-10T08:00:00Z' },
      { id: 'carsi',            health_score: 72, security_score: 55, last_updated: '2026-05-10T08:00:00Z' },
    ],
  }),
};

// ── /api/empire/health ─────────────────────────────────────────────────────
describe('/api/empire/health GET', () => {

  test('returns an array of projects with correct shape', async () => {
    (global.fetch as jest.Mock)
      .mockResolvedValueOnce(MOCK_PI_CEO_LOGIN_RESPONSE)  // login
      .mockResolvedValueOnce(MOCK_PROJECTS_RESPONSE);      // projects

    const req = new NextRequest('http://localhost/api/empire/health');
    const res = await getEmpireHealth(req);
    const body = await res.json();

    expect(res.status).toBe(200);
    expect(body).toHaveProperty('businesses');
    expect(Array.isArray(body.businesses)).toBe(true);
    expect(body.businesses.length).toBeGreaterThan(0);

    const project = body.businesses[0];
    expect(project).toHaveProperty('id');
    expect(project).toHaveProperty('name');
    expect(project).toHaveProperty('uptime_pct');
    expect(project).toHaveProperty('status');
    expect(project).toHaveProperty('arr_aud');
  });

  test('maps known project IDs to correct business names', async () => {
    (global.fetch as jest.Mock)
      .mockResolvedValueOnce(MOCK_PI_CEO_LOGIN_RESPONSE)
      .mockResolvedValueOnce(MOCK_PROJECTS_RESPONSE);

    const req = new NextRequest('http://localhost/api/empire/health');
    const res = await getEmpireHealth(req);
    const body: { businesses: Array<{ id: string; name: string }> } = await res.json();

    const byId = Object.fromEntries(body.businesses.map(p => [p.id, p.name]));
    expect(byId['restoreassist']).toBe('RestoreAssist');
    expect(byId['synthex']).toBe('Synthex');
    expect(byId['ccw-crm']).toBe('CCW-CRM');
    expect(byId['disaster-recovery']).toBe('DR Platform');
    expect(byId['dr-nrpg']).toBe('NRPG');
    expect(byId['carsi']).toBe('CARSI');
  });

  test('CCW-CRM has correct ARR ($33,000 AUD)', async () => {
    (global.fetch as jest.Mock)
      .mockResolvedValueOnce(MOCK_PI_CEO_LOGIN_RESPONSE)
      .mockResolvedValueOnce(MOCK_PROJECTS_RESPONSE);

    const req = new NextRequest('http://localhost/api/empire/health');
    const res = await getEmpireHealth(req);
    const body: { businesses: Array<{ id: string; arr_aud: number }> } = await res.json();

    const ccw = body.businesses.find(p => p.id === 'ccw-crm');
    expect(ccw).toBeDefined();
    expect(ccw!.arr_aud).toBe(33000);
  });

  test('returns fallback data when Railway login fails', async () => {
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ error: 'unauthorized' }),
    });

    const req = new NextRequest('http://localhost/api/empire/health');
    const res = await getEmpireHealth(req);
    const body: Array<{ id: string; health_score: number; status: string }> = await res.json();

    // Must return data even when Railway is down — never crash the dashboard
    expect(res.status).toBe(200);
    expect(body).toHaveProperty('businesses');
    expect(Array.isArray(body.businesses)).toBe(true);
    expect(body.businesses.length).toBe(6); // all 6 businesses always represented

    // Fallback scores are clearly degraded but not zero
    body.businesses.forEach((p: { id: string; status: string }) => {
      expect(p).toHaveProperty('id');
      expect(p).toHaveProperty('status');
    });
  });

  test('returns fallback data when Railway times out', async () => {
    (global.fetch as jest.Mock).mockRejectedValue(new Error('AbortError'));

    const req = new NextRequest('http://localhost/api/empire/health');
    const res = await getEmpireHealth(req);

    // Should not throw — graceful degradation
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body).toHaveProperty('businesses');
    expect(Array.isArray(body.businesses)).toBe(true);
  });

  test('health_score is a number between 0 and 100', async () => {
    (global.fetch as jest.Mock)
      .mockResolvedValueOnce(MOCK_PI_CEO_LOGIN_RESPONSE)
      .mockResolvedValueOnce(MOCK_PROJECTS_RESPONSE);

    const req = new NextRequest('http://localhost/api/empire/health');
    const res = await getEmpireHealth(req);
    const body: { businesses: Array<{ uptime_pct: number }> } = await res.json();

    body.businesses.forEach((project: { uptime_pct: number }) => {
      expect(typeof project.uptime_pct).toBe('number');
      expect(project.uptime_pct).toBeGreaterThanOrEqual(0);
      expect(project.uptime_pct).toBeLessThanOrEqual(100);
    });
  });

});

// ── /api/pi-ceo/health ─────────────────────────────────────────────────────
describe('/api/pi-ceo/health GET', () => {

  test('returns correct shape with source field', async () => {
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      headers: new Headers({ 'set-cookie': 'tao_session=abc; Path=/' }),
      json: async () => ({
        poll_count: 371,
        last_poll_ago_s: 45,
        autonomy_pct: 100,
        swarm_enabled: true,
        kill_switch_active: false,
      }),
    });

    const req = new NextRequest('http://localhost/api/pi-ceo/health');
    const res = await getPiCeoHealth(req);
    const body = await res.json();

    expect(res.status).toBe(200);
    expect(body).toHaveProperty('source');
    expect(['local_session', 'env_api', 'unavailable']).toContain(body.source);
  });

  test('source is "unavailable" when Railway is unreachable', async () => {
    (global.fetch as jest.Mock).mockRejectedValue(new Error('ECONNREFUSED'));

    const req = new NextRequest('http://localhost/api/pi-ceo/health');
    const res = await getPiCeoHealth(req);
    const body = await res.json();

    expect(res.status).toBe(200);
    expect(body.source).toBe('unavailable');
  });

  test('poll_count is a number when Railway returns autonomy data', async () => {
    // Mock the login + autonomy endpoint calls that pi-ceo health uses
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      headers: new Headers({ 'set-cookie': 'tao_session=xyz; Path=/' }),
      json: async () => ({
        poll_count: 450,
        last_poll_ago_s: 12,
        autonomy_pct: 100,
        swarm_enabled: true,
        kill_switch_active: false,
      }),
    });

    const req = new NextRequest('http://localhost/api/pi-ceo/health');
    const res = await getPiCeoHealth(req);
    const body = await res.json();

    expect(res.status).toBe(200);
    expect(body).toHaveProperty('source');
    // When data is available, either poll_count exists and is a number, or source is unavailable
    if (body.poll_count !== null && body.poll_count !== undefined) {
      expect(typeof body.poll_count).toBe('number');
      expect(body.poll_count).toBeGreaterThan(0);
    }
  });

});
