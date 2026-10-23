/**
 * /api/flow-board?repo= — per-project open PRs and default-branch CI.
 *
 * Each field reports its own failed read as `unavailable` with a reason; a good
 * read of nothing is `ok` with a count of 0. The repo must be in the registry.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { GET } from "@/app/api/flow-board/route";
import { parseRepoTruth } from "@/lib/control/card-truth";
import { resetRepoTruthCache } from "@/lib/control/repo-truth-server";

const pull = (n: number) => ({
  number: n, title: `PR ${n}`, html_url: `https://github.com/CleanExpo/carsi/pull/${n}`,
  created_at: "2026-10-20T00:00:00Z", labels: [],
});
const rollup = (state: string | null) => ({
  data: { repository: { defaultBranchRef: { name: "main", target: { oid: "abc1234def", statusCheckRollup: state ? { state } : null } } } },
});
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

function stubGithub(pulls: () => Response, graphql: () => Response) {
  const fetchMock = vi.fn(async (url: string | URL | Request) => (String(url).endsWith("/graphql") ? graphql() : pulls()));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const get = (repo?: string) =>
  GET(new Request(`http://localhost/api/flow-board${repo === undefined ? "" : `?repo=${encodeURIComponent(repo)}`}`));

beforeEach(() => { resetRepoTruthCache(); vi.stubEnv("GITHUB_TOKEN", "test-token"); });
afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); });

describe("GET /api/flow-board", () => {
  it("refuses a repo that is not in the registry, without calling GitHub", async () => {
    const fetchMock = stubGithub(() => json([]), () => json(rollup("SUCCESS")));
    const res = await get("evil/repo");
    expect(res.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("EMPTY: a good read of no PRs is 0 open PRs, not unavailable", async () => {
    stubGithub(() => json([]), () => json(rollup("SUCCESS")));
    const body = await (await get("CleanExpo/carsi")).json();
    expect(body.repo).toBe("CleanExpo/carsi");
    expect(body.pull_requests).toEqual({ status: "ok", value: { count: 0, capped: false } });
    expect(body.ci).toEqual({ status: "ok", value: { branch: "main", sha: "abc1234def", state: "success" } });
  });

  it("LOADED: counts open PRs and reports a failing default branch", async () => {
    stubGithub(() => json([pull(1), pull(2)]), () => json(rollup("FAILURE")));
    const body = await (await get("CleanExpo/carsi")).json();
    expect(body.pull_requests.value.count).toBe(2);
    expect(body.ci.value.state).toBe("failure");
  });

  it("a default branch with no checks reports none, not passing", async () => {
    stubGithub(() => json([]), () => json(rollup(null)));
    const body = await (await get("CleanExpo/carsi")).json();
    expect(body.ci.value.state).toBe("none");
  });

  it("ERROR: a failed PR read is unavailable with the reason; CI still reads", async () => {
    stubGithub(() => json({ message: "x" }, 502), () => json(rollup("SUCCESS")));
    const body = await (await get("CleanExpo/carsi")).json();
    expect(body.pull_requests).toEqual({ status: "unavailable", reason: "GitHub pulls HTTP 502" });
    expect(body.ci.status).toBe("ok");
  });

  it("ERROR: GraphQL errors make CI unavailable, never passing", async () => {
    stubGithub(() => json([]), () => json({ data: { repository: null }, errors: [{ message: "Could not resolve" }] }));
    const body = await (await get("CleanExpo/carsi")).json();
    expect(body.ci).toEqual({ status: "unavailable", reason: "GitHub CI read failed: Could not resolve" });
  });

  it.each([
    ["HTTP 403 on both reads", () => json({ message: "rate limited" }, 403), "GitHub CI HTTP 403"],
    ["a GraphQL errors body", () => json({ data: null, errors: [{ message: "RATE_LIMITED" }] }), "GitHub CI read failed: RATE_LIMITED"],
  ])("CARD TRUTH end to end: %s reaches the card as UNAVAILABLE, never 0 PRs or passing", async (_case, graphql, ciReason) => {
    stubGithub(() => json({ message: "rate limited" }, 403), graphql);
    const res = await get("CleanExpo/carsi");
    expect(res.status).toBe(200);
    const truth = parseRepoTruth(await res.json());
    expect(truth?.pull_requests).toEqual({ status: "unavailable", reason: "GitHub pulls HTTP 403" });
    expect(truth?.ci).toEqual({ status: "unavailable", reason: ciReason });
  });

  it("ERROR: no server token makes both fields unavailable", async () => {
    vi.stubEnv("GITHUB_TOKEN", "");
    const fetchMock = stubGithub(() => json([]), () => json(rollup("SUCCESS")));
    const body = await (await get("CleanExpo/carsi")).json();
    expect(body.pull_requests).toEqual({ status: "unavailable", reason: "GITHUB_TOKEN not set" });
    expect(body.ci).toEqual({ status: "unavailable", reason: "GITHUB_TOKEN not set" });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("caches per repo: two reads cost one request per field", async () => {
    const fetchMock = stubGithub(() => json([]), () => json(rollup("SUCCESS")));
    await get("CleanExpo/carsi");
    await get("CleanExpo/carsi");
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("cache is keyed per repo: a second repo gets its own read, never the first repo's", async () => {
    const fetchMock = vi.fn(async (url: string | URL | Request) => {
      const u = String(url);
      if (u.endsWith("/graphql")) return json(rollup("SUCCESS"));
      return json(u.includes("/repos/CleanExpo/carsi/") ? [pull(1)] : [pull(1), pull(2), pull(3)]);
    });
    vi.stubGlobal("fetch", fetchMock);
    const carsi = await (await get("CleanExpo/carsi")).json();
    const ra = await (await get("CleanExpo/RestoreAssist")).json();
    expect(carsi.repo).toBe("CleanExpo/carsi");
    expect(carsi.pull_requests.value.count).toBe(1);
    expect(ra.repo).toBe("CleanExpo/RestoreAssist");
    expect(ra.pull_requests.value.count).toBe(3);
    expect(fetchMock).toHaveBeenCalledTimes(4);
  });

  it("cache expires after 60 s: a hit before it, a re-fetch after it", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    try {
      vi.setSystemTime(new Date("2026-10-22T00:00:00Z"));
      const fetchMock = stubGithub(() => json([]), () => json(rollup("SUCCESS")));
      await get("CleanExpo/carsi");
      vi.setSystemTime(new Date("2026-10-22T00:00:59Z"));
      await get("CleanExpo/carsi");
      expect(fetchMock).toHaveBeenCalledTimes(2);
      vi.setSystemTime(new Date("2026-10-22T00:01:01Z"));
      await get("CleanExpo/carsi");
      expect(fetchMock).toHaveBeenCalledTimes(4);
    } finally {
      vi.useRealTimers();
    }
  });

  it("keeps the Pi-Dev-Ops board when no repo is given", async () => {
    const fetchMock = stubGithub(() => json([]), () => json(rollup("SUCCESS")));
    const body = await (await get()).json();
    expect(body.repo).toBe("CleanExpo/Pi-Dev-Ops");
    expect(String(fetchMock.mock.calls[0][0])).toContain("/repos/CleanExpo/Pi-Dev-Ops/pulls");
  });
});
