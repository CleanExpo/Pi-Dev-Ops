import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
const mocks = vi.hoisted(() => ({ piCeoFetch: vi.fn() }));
vi.mock("@/lib/pi-ceo-session", () => mocks);
import { GET as swarm } from "@/app/api/swarm-status/route";
import { GET as zte } from "@/app/api/zte/route";
beforeEach(() => { vi.clearAllMocks(); vi.stubEnv("PI_CEO_URL", "http://test.invalid"); vi.stubEnv("HARNESS_AUDIT_PATH", ""); });
afterEach(() => vi.unstubAllEnvs());
const upstream = (value: unknown) => mocks.piCeoFetch.mockResolvedValue(new Response(JSON.stringify(value)));
describe("control observation truth", () => {
  it("does not turn the autonomy configuration into an active swarm", async () => {
    upstream({ enabled: true, poll_count: 5, stale: false });
    expect(await (await swarm()).json()).toMatchObject({ state: "UNKNOWN", autonomous_prs_today: null, green_merges: null });
  });
  it("reports unknown when swarm telemetry is unavailable", async () => {
    mocks.piCeoFetch.mockResolvedValue(null);
    expect(await (await swarm()).json()).toMatchObject({ state: "UNKNOWN", autonomous_prs_limit: null });
  });
  it("RA-7849: reads the swarm's own status endpoint, not the autonomy poller's", async () => {
    upstream({ swarm_enabled_env: false, swarm_shadow_env: true, kill_switch_active: false, pr_quota: { used: 0, limit: 5 } });
    expect(await (await swarm()).json()).toMatchObject({ state: "OFF", autonomous_prs_today: 0, autonomous_prs_limit: 5 });
    expect(mocks.piCeoFetch.mock.calls[0][0]).toBe("/api/swarm/status");
  });
  it("RA-7849: an enabled swarm reports shadow, active, rate-limited or killed from its own flags", async () => {
    const base = { swarm_enabled_env: true, kill_switch_active: false, pr_quota: { used: 1, limit: 5 } };
    upstream({ ...base, swarm_shadow_env: true });
    expect((await (await swarm()).json()).state).toBe("SHADOW");
    upstream({ ...base, swarm_shadow_env: false });
    expect((await (await swarm()).json()).state).toBe("ACTIVE");
    upstream({ ...base, swarm_shadow_env: false, pr_quota: { used: 5, limit: 5 } });
    expect((await (await swarm()).json()).state).toBe("RATE_LIMITED");
    upstream({ ...base, swarm_shadow_env: false, kill_switch_active: true });
    expect((await (await swarm()).json()).state).toBe("OFF");
  });
  it("does not invent a score or active model when telemetry is absent", async () => {
    mocks.piCeoFetch.mockResolvedValue(null);
    expect(await (await zte()).json()).toMatchObject({ score: null, model: null, model_id: null, source: "unavailable" });
  });
  it("a measured score does not establish model identity", async () => {
    upstream({ score: 30 });
    expect(await (await zte()).json()).toMatchObject({ score: 30, model: null, model_id: null });
  });
  it("does not convert null or partial autonomy evidence to a zero score", async () => {
    upstream({ score: null, effective_autonomy_pct: null, metric_scope: "poll_and_launch_only" });
    expect(await (await zte()).json()).toMatchObject({ score: null, source: "unavailable" });
  });
});
