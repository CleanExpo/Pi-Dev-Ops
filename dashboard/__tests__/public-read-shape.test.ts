/**
 * Can the three deliberately-public reads grow their payload without anyone deciding to?
 *
 * `/api/zte`, `/api/swarm-status` and `/api/curator-proposals` are classified
 * `deliberately-public`: reachable with no credential, by design. Each proxies upstream using
 * `PI_CEO_PASSWORD`, which the caller does not hold — so whatever upstream returns becomes a
 * public payload. "Flagged to revisit if the payload widens" was an intention; by the estate's
 * own standard a review is never coverage, and a gap found and left unbuilt is still open.
 *
 * This is that control. Upstream is stubbed to return a WIDER body than expected — including
 * a plausibly sensitive key — and each route must not publish the additions.
 *
 * Two designs, and the difference is deliberate:
 *   · zte / swarm-status PROJECT into named fields, so extra keys are structurally impossible
 *     to emit. The assertion here is that the projection still holds.
 *   · curator-proposals proxied the body wholesale, so it now FAILS CLOSED on an unexpected
 *     key instead of dropping it. A silent drop would hide a real upstream change just as
 *     well; this way it is loud, and accepting the new key is a one-line deliberate act.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";

const LEAK = "internal_secret_note";

/** A wider-than-expected upstream body, including something that must never surface. */
const NESTED_LEAK = "internal_reviewer_note";

const WIDE = {
  score: 96,
  model: "opus",
  state: "ACTIVE",
  // NESTED widening — round-1 review found the first guard checked only top-level keys, so
  // upstream could widen the objects INSIDE `proposals` and every new field reached anonymous
  // callers. The interesting payload was entirely below the level being checked.
  proposals: [
    { id: 1, skill: "x", status: "pending", [NESTED_LEAK]: "must not be published" },
  ],
  count: 0,
  [LEAK]: "should never reach an anonymous caller",
  operator_email: "founder@example.invalid",
};

const realFetch = globalThis.fetch;

beforeEach(() => {
  process.env.PI_CEO_URL = "https://upstream.invalid";
  process.env.PI_CEO_PASSWORD = "x";
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      new Response(JSON.stringify(WIDE), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    ),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  globalThis.fetch = realFetch;
  vi.resetModules();
});

async function bodyOf(mod: string, path: string) {
  const { GET } = await import(mod);
  const res = await GET(new Request(`https://pi.invalid${path}`));
  return { status: res.status, json: await res.json() };
}

describe("deliberately-public reads cannot widen silently", () => {
  it("CONTROL: the stub is actually being used, and it is wide", async () => {
    // If the stub were not wired, every assertion below would pass against an empty body —
    // a green run over nothing, which is the failure this whole suite exists to prevent.
    const res = await fetch("https://upstream.invalid/anything");
    const j = (await res.json()) as Record<string, unknown>;
    expect(Object.keys(j)).toContain(LEAK);
  });

  it("/api/zte publishes only its projected fields", async () => {
    const { json } = await bodyOf("../app/api/zte/route", "/api/zte");
    expect(Object.keys(json)).not.toContain(LEAK);
    expect(Object.keys(json)).not.toContain("operator_email");
  });

  it("/api/swarm-status publishes only its projected fields", async () => {
    const { json } = await bodyOf("../app/api/swarm-status/route", "/api/swarm-status");
    expect(Object.keys(json)).not.toContain(LEAK);
    expect(Object.keys(json)).not.toContain("operator_email");
  });

  it("/api/curator-proposals WITHHOLDS a body carrying unexpected keys", async () => {
    const { json } = await bodyOf(
      "../app/api/curator-proposals/route",
      "/api/curator-proposals",
    );
    const keys = Object.keys(json);
    expect(
      keys,
      "an unexpected upstream key reached an anonymous caller. This route is public and " +
        "reaches upstream with a credential the caller does not hold, so a payload it has " +
        "never reviewed must not be published.",
    ).not.toContain(LEAK);
    expect(keys).not.toContain("operator_email");
    // And it must say so, rather than quietly returning a thinner body.
    expect(json).toHaveProperty("error");
    // The nested case explicitly: a leak one level down is the one that got through.
    expect(JSON.stringify(json)).not.toContain(NESTED_LEAK);
  });

  it("/api/curator-proposals withholds a body widened ONLY inside proposals[]", async () => {
    // ISOLATION MATTERS. The WIDE payload above also carries unexpected TOP-LEVEL keys, so a
    // shallow top-level-only guard withholds it anyway and the nested assertion passes for the
    // wrong reason — which is exactly what happened when this control was first written. Here
    // every top-level key is expected and the ONLY widening is one level down, so this test
    // can only pass if the check actually descends.
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            count: 1,
            proposals: [{ id: 1, skill: "x", status: "pending", [NESTED_LEAK]: "leaked" }],
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      ),
    );
    vi.resetModules();
    const { json } = await bodyOf(
      "../app/api/curator-proposals/route",
      "/api/curator-proposals",
    );
    expect(
      JSON.stringify(json),
      "a field added INSIDE proposals[] reached an anonymous caller. Every top-level key here " +
        "is expected, so only a guard that descends into nested objects can catch this.",
    ).not.toContain(NESTED_LEAK);
    expect(json).toHaveProperty("error");
  });

  it("CONTROL: curator-proposals still serves a body whose keys are all expected", async () => {
    // Without this, "withholds everything" would pass the assertion above — the route could be
    // broken rather than guarded.
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(JSON.stringify({
          proposals: [{ id: 1, skill: "x", status: "pending" }],
          count: 1,
        }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      ),
    );
    vi.resetModules();
    const { json } = await bodyOf(
      "../app/api/curator-proposals/route",
      "/api/curator-proposals",
    );
    expect(json).toHaveProperty("proposals");
    expect(json).not.toHaveProperty("error");
  });
});
