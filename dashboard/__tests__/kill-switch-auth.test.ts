/**
 * Can an anonymous caller kill or resume the swarm?
 *
 * Until 2026-08-02 the answer was yes. `/api/kill-switch` is in neither
 * PROTECTED_API_PREFIXES nor PUBLIC_API_PREFIXES in proxy.ts, so it fell through the proxy's
 * auth block entirely — and the route attaches `Authorization: Bearer PI_CEO_PASSWORD` to its
 * own upstream call, so the caller needed no credential at all. A confused deputy on a safety
 * control, with `resume` able to restart automation that was deliberately stopped.
 *
 * This asserts the POST path refuses an unauthenticated caller, and — the part that makes the
 * refusal meaningful rather than a blanket 401 — that it ACCEPTS the two legitimate ones.
 *
 * POSITIVE CONTROLS ARE THE POINT HERE. "Returns 401" is also what a route returns when it is
 * broken, misconfigured, or when the handler throws before reaching its logic. If the accepted
 * credentials do not get past auth, this file proves only that the endpoint is dead.
 */
import { describe, it, expect, beforeAll } from "vitest";
import { createHmac, randomBytes } from "node:crypto";

// Generated per run, never written as literals. The secrets scanner correctly flags a
// secret-shaped string in any file — it cannot tell a fixture from a credential by reading
// it, and narrowing its scope to accommodate a test is how a real one eventually walks
// through. Second instance of this; route-exercise.mjs was the first.
const PASSWORD = randomBytes(24).toString("hex");
const KS_SECRET = randomBytes(24).toString("hex");

beforeAll(() => {
  process.env.DASHBOARD_PASSWORD = PASSWORD;
  process.env.KILL_SWITCH_SECRET = KS_SECRET;
  // Deliberately absent so the upstream fetch cannot fire during these tests: the handler
  // returns 503 once past auth. That 503 is the signal we want — it means auth was PASSED.
  delete process.env.PI_CEO_URL;
  delete process.env.RAILWAY_URL;
});

/** A valid pi_session cookie, minted the same way app/api/auth/login signs one. */
function sessionCookie(): string {
  const issuedAt = String(Math.floor(Date.now() / 1000));
  const sig = createHmac("sha256", PASSWORD).update(issuedAt).digest("hex");
  return `pi_session=${issuedAt}.${sig}`;
}

async function post(headers: Record<string, string> = {}, op = "kill") {
  const { POST } = await import("../app/api/kill-switch/route");
  return POST(
    new Request(`https://pi.invalid/api/kill-switch?op=${op}`, {
      method: "POST",
      headers: { "content-type": "application/json", ...headers },
      body: JSON.stringify({ reason: "test" }),
    }),
  );
}

describe("kill-switch mutation auth", () => {
  it("REFUSES an anonymous kill", async () => {
    const res = await post();
    expect(
      res.status,
      "an anonymous POST reached the kill path. The route supplies PI_CEO_PASSWORD upstream " +
        "itself, so this is a privileged operation with no credential required.",
    ).toBe(401);
  });

  it("REFUSES an anonymous resume", async () => {
    // The sharper direction: resume can restart automation the founder deliberately stopped.
    expect((await post({}, "resume")).status).toBe(401);
  });

  it("REFUSES a wrong shared secret", async () => {
    expect((await post({ "x-kill-switch-secret": "not-the-secret" })).status).toBe(401);
  });

  it("REFUSES a forged session cookie", async () => {
    const issuedAt = String(Math.floor(Date.now() / 1000));
    expect((await post({ cookie: `pi_session=${issuedAt}.deadbeef` })).status).toBe(401);
  });

  it("REFUSES an expired session cookie", async () => {
    const old = String(Math.floor(Date.now() / 1000) - 90_000); // TTL is 86400
    const sig = createHmac("sha256", PASSWORD).update(old).digest("hex");
    expect((await post({ cookie: `pi_session=${old}.${sig}` })).status).toBe(401);
  });

  // ---- POSITIVE CONTROLS — without these, every assertion above is satisfied by a dead route.
  it("CONTROL: a valid session cookie gets PAST auth", async () => {
    const res = await post({ cookie: sessionCookie() });
    expect(
      res.status,
      "a valid session was rejected — the 401s above would then prove only that the endpoint " +
        "is broken, not that it is guarded.",
    ).not.toBe(401);
    // PI_CEO_URL is unset in this suite, so past-auth lands on the not-configured branch.
    expect(res.status).toBe(503);
  });

  it("CONTROL: a valid shared secret gets PAST auth", async () => {
    const res = await post({ "x-kill-switch-secret": KS_SECRET });
    expect(res.status).not.toBe(401);
    expect(res.status).toBe(503);
  });

  it("CONTROL: fails closed when no secret is configured", async () => {
    const saved = process.env.KILL_SWITCH_SECRET;
    delete process.env.KILL_SWITCH_SECRET;
    try {
      // An unconfigured secret must not become "allow anyone presenting a header".
      expect((await post({ "x-kill-switch-secret": "anything" })).status).toBe(401);
    } finally {
      process.env.KILL_SWITCH_SECRET = saved;
    }
  });
});
