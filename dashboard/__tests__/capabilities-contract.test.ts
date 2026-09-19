import { describe, expect, it } from "vitest";
import { GET } from "@/app/api/capabilities/route";
import * as analysis from "@/app/api/analyze/route";

describe("capability contract", () => {
  it("describes the implemented analysis method and streamed response", async () => {
    const body = await (await GET()).json();
    const analyze = body.endpoints.find((endpoint: { path: string }) => endpoint.path === "/api/analyze");
    expect(typeof analysis[analyze.method as keyof typeof analysis]).toBe("function");
    expect(analyze.inputs.repo).toContain("query");
    expect(analyze.outputs.stream).toContain("text/event-stream");
  });
  it("separates configured model names from verified availability", async () => {
    const body = await (await GET()).json();
    expect(body.supportedModels).toEqual([]);
    expect(body.configuredModels.length).toBeGreaterThan(0);
    expect(body.metadata).toMatchObject({ zteLevel: null, modelAvailability: "unverified" });
  });
});
