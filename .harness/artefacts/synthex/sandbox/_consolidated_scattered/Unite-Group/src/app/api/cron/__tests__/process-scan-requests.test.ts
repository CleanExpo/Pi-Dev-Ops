// UNI-1948 — Tests for the Pi-CEO scanner cron worker.

import { GET } from '../process-scan-requests/route';
import { computeSecurityScore, computeOverallHealth } from '../process-scan-requests/_helpers';

// ---- Mocks ----

const pendingMaybeSingle = jest.fn();
const businessMaybeSingle = jest.fn();
const claimUpdate = jest.fn();
const completeUpdate = jest.fn();
const failUpdate = jest.fn();
const snapshotInsertSelectSingle = jest.fn();

// Track call order of update() so we can route to claim/complete/fail.
let updateCalls: Array<'claim' | 'complete' | 'fail'> = [];

jest.mock('@/lib/supabase/admin', () => ({
  getAdminClient: () => ({
    from: (table: string) => {
      if (table === 'scan_requests') {
        return {
          select: () => ({
            eq: () => ({
              order: () => ({
                limit: () => ({ maybeSingle: pendingMaybeSingle }),
              }),
            }),
          }),
          update: (payload: { status?: string }) => {
            // route by payload.status: running=claim, completed=complete, failed=fail
            const kind: 'claim' | 'complete' | 'fail' =
              payload.status === 'running'
                ? 'claim'
                : payload.status === 'completed'
                ? 'complete'
                : 'fail';
            updateCalls.push(kind);
            const handler =
              kind === 'claim' ? claimUpdate : kind === 'complete' ? completeUpdate : failUpdate;
            return {
              eq: () => ({
                eq: () => handler(),
                then: (resolve: (v: { error: null }) => void) => resolve({ error: null }),
              }),
            };
          },
        };
      }
      if (table === 'businesses') {
        return {
          select: () => ({
            eq: () => ({
              not: () => ({
                order: () => ({
                  limit: () => ({ maybeSingle: businessMaybeSingle }),
                }),
              }),
            }),
          }),
        };
      }
      if (table === 'pi_ceo_health_snapshots') {
        return {
          insert: () => ({
            select: () => ({ single: snapshotInsertSelectSingle }),
          }),
        };
      }
      throw new Error('unexpected table ' + table);
    },
  }),
}));

const realFetch = global.fetch;

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function authedRequest(): Request {
  return new Request('http://x/api/cron/process-scan-requests', {
    headers: { Authorization: 'Bearer test-cron-secret' },
  });
}

beforeEach(() => {
  pendingMaybeSingle.mockReset();
  businessMaybeSingle.mockReset();
  claimUpdate.mockReset().mockResolvedValue({ error: null });
  completeUpdate.mockReset().mockResolvedValue({ error: null });
  failUpdate.mockReset().mockResolvedValue({ error: null });
  snapshotInsertSelectSingle.mockReset();
  updateCalls = [];
  process.env.CRON_SECRET = 'test-cron-secret';
  process.env.GITHUB_TOKEN = 'test-github-token';
  delete process.env.SUPABASE_ACCESS_TOKEN;
  delete process.env.LINEAR_API_KEY;
});

afterEach(() => {
  global.fetch = realFetch;
});

// ---- Scoring unit tests ----

describe('computeSecurityScore', () => {
  it('returns 100 for a clean repo', () => {
    expect(
      computeSecurityScore({
        dep_alerts_open: 0,
        supabase_security_count: 0,
        ci_failing: false,
        github_known: true,
      })
    ).toBe(100);
  });

  it('penalises dependabot alerts (capped at 50)', () => {
    expect(
      computeSecurityScore({
        dep_alerts_open: 200,
        supabase_security_count: null,
        ci_failing: false,
        github_known: true,
      })
    ).toBe(50);
  });

  it('penalises failing CI by 10', () => {
    expect(
      computeSecurityScore({
        dep_alerts_open: 0,
        supabase_security_count: 0,
        ci_failing: true,
        github_known: true,
      })
    ).toBe(90);
  });

  it('penalises unknown github by 20', () => {
    expect(
      computeSecurityScore({
        dep_alerts_open: null,
        supabase_security_count: null,
        ci_failing: false,
        github_known: false,
      })
    ).toBe(80);
  });
});

describe('computeOverallHealth', () => {
  it('weights security 40% / deploys 40% / tickets 20%', () => {
    const now = new Date().toISOString();
    // security=100, deploys (commit today)=100, tickets=100 → 100
    expect(
      computeOverallHealth({
        security_score: 100,
        latest_commit_at: now,
        linear_in_progress: 0,
      })
    ).toBe(100);
  });

  it('decays deploys component after 30 days', () => {
    const old = new Date(Date.now() - 60 * 86_400_000).toISOString();
    // security=100 → 40, deploys=0, tickets (unknown)=50 → 50
    expect(
      computeOverallHealth({
        security_score: 100,
        latest_commit_at: old,
        linear_in_progress: null,
      })
    ).toBe(50);
  });
});

// ---- Worker integration tests ----

describe('GET /api/cron/process-scan-requests', () => {
  it('returns noop when queue is empty', async () => {
    pendingMaybeSingle.mockResolvedValue({ data: null, error: null });
    const res = await GET(authedRequest());
    const body = await res.json();
    expect(body.ok).toBe(true);
    expect(body.processed).toBe(0);
    expect(body.message).toBe('queue empty');
    expect(updateCalls).toEqual([]);
  });

  it('fails the row when github_repo is null', async () => {
    pendingMaybeSingle.mockResolvedValue({
      data: { id: 'req-1', slug: 'synthex', requested_at: '2026-05-13T00:00:00Z', status: 'pending' },
      error: null,
    });
    businessMaybeSingle.mockResolvedValue({
      data: {
        id: 'biz-1',
        slug: 'synthex',
        pi_ceo_key: 'synthex',
        github_repo: null,
        supabase_project_ref: null,
        linear_team_id: null,
      },
      error: null,
    });

    const res = await GET(authedRequest());
    const body = await res.json();
    expect(body.status).toBe('failed');
    expect(body.reason).toContain('GitHub repo not configured');
    expect(updateCalls).toEqual(['claim', 'fail']);
    expect(snapshotInsertSelectSingle).not.toHaveBeenCalled();
  });

  it('inserts snapshot and completes row on successful scan', async () => {
    pendingMaybeSingle.mockResolvedValue({
      data: { id: 'req-2', slug: 'synthex', requested_at: '2026-05-13T00:00:00Z', status: 'pending' },
      error: null,
    });
    businessMaybeSingle.mockResolvedValue({
      data: {
        id: 'biz-1',
        slug: 'synthex',
        pi_ceo_key: 'synthex',
        github_repo: 'CleanExpo/Synthex',
        supabase_project_ref: null,
        linear_team_id: null,
      },
      error: null,
    });
    snapshotInsertSelectSingle.mockResolvedValue({
      data: { id: 9001 },
      error: null,
    });

    const today = new Date().toISOString();
    global.fetch = jest.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/repos/CleanExpo/Synthex')) {
        return jsonResponse({
          default_branch: 'main',
          html_url: 'https://github.com/CleanExpo/Synthex',
          archived: false,
          pushed_at: today,
        });
      }
      if (url.includes('/commits/main')) {
        return jsonResponse({
          sha: 'a',
          commit: { message: 'feat', author: { name: 'p', date: today } },
        });
      }
      if (url.includes('/actions/runs')) {
        return jsonResponse({
          workflow_runs: [
            { status: 'completed', conclusion: 'success', updated_at: today },
          ],
        });
      }
      if (url.includes('/dependabot/alerts')) {
        return jsonResponse([{ state: 'open' }]);
      }
      if (url.includes('/pulls')) {
        return jsonResponse([]);
      }
      throw new Error('unexpected url ' + url);
    }) as unknown as typeof fetch;

    const res = await GET(authedRequest());
    const body = await res.json();
    expect(body.status).toBe('completed');
    expect(body.snapshot_id).toBe(9001);
    expect(body.security_score).toBeGreaterThanOrEqual(90); // 100 - 0.5*1 = 99.5 → 100
    expect(body.security_findings).toBe(1);
    expect(updateCalls).toEqual(['claim', 'complete']);
  });

  it('marks row failed when snapshot insert errors', async () => {
    pendingMaybeSingle.mockResolvedValue({
      data: { id: 'req-3', slug: 'synthex', requested_at: '2026-05-13T00:00:00Z', status: 'pending' },
      error: null,
    });
    businessMaybeSingle.mockResolvedValue({
      data: {
        id: 'biz-1',
        slug: 'synthex',
        pi_ceo_key: 'synthex',
        github_repo: 'CleanExpo/Synthex',
        supabase_project_ref: null,
        linear_team_id: null,
      },
      error: null,
    });
    snapshotInsertSelectSingle.mockResolvedValue({
      data: null,
      error: { message: 'unique violation' },
    });

    // Github fetch succeeds — failure is on the insert step.
    const today = new Date().toISOString();
    global.fetch = jest.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/repos/CleanExpo/Synthex')) {
        return jsonResponse({ default_branch: 'main', html_url: 'x', archived: false, pushed_at: today });
      }
      if (url.includes('/commits/main')) {
        return jsonResponse({ sha: 'a', commit: { message: 'c', author: { name: 'p', date: today } } });
      }
      if (url.includes('/actions/runs')) return jsonResponse({ workflow_runs: [] });
      if (url.includes('/dependabot/alerts')) return jsonResponse([]);
      if (url.includes('/pulls')) return jsonResponse([]);
      throw new Error('unexpected ' + url);
    }) as unknown as typeof fetch;

    const res = await GET(authedRequest());
    const body = await res.json();
    expect(body.status).toBe('failed');
    expect(body.reason).toContain('snapshot insert failed');
    expect(updateCalls).toEqual(['claim', 'fail']);
  });

  it('fails the row when business slug is not found', async () => {
    pendingMaybeSingle.mockResolvedValue({
      data: { id: 'req-4', slug: 'ghost', requested_at: '2026-05-13T00:00:00Z', status: 'pending' },
      error: null,
    });
    businessMaybeSingle.mockResolvedValue({ data: null, error: null });

    const res = await GET(authedRequest());
    const body = await res.json();
    expect(body.status).toBe('failed');
    expect(body.reason).toContain('business not found');
    expect(updateCalls).toEqual(['claim', 'fail']);
  });

  it('rejects without bearer token', async () => {
    const res = await GET(new Request('http://x'));
    expect(res.status).toBe(401);
  });
});
