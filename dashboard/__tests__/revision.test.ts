import { afterEach, describe, expect, it, vi } from "vitest";
import { GET } from "../app/api/revision/route";

afterEach(() => vi.unstubAllEnvs());

describe("deployment revision", () => {
  it("reports missing evidence rather than the current checkout", async () => {
    vi.stubEnv("VERCEL_GIT_COMMIT_SHA", "");
    vi.stubEnv("BUILD_REVISION", "");
    const response = GET();
    expect(await response.json()).toEqual({ revision: null });
    expect(response.headers.get("Cache-Control")).toContain("no-store");
  });

  it("exposes the full immutable deployment revision", async () => {
    vi.stubEnv("VERCEL_GIT_COMMIT_SHA", "a".repeat(40));
    vi.stubEnv("BUILD_REVISION", "b".repeat(40));
    expect(await GET().json()).toEqual({ revision: "a".repeat(40) });
  });

  it("rejects arbitrary environment values", async () => {
    vi.stubEnv("VERCEL_GIT_COMMIT_SHA", "not-a-revision");
    expect(await GET().json()).toEqual({ revision: null });
  });
});
