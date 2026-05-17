import { describe, it, expect, vi, beforeEach } from "vitest";

describe("/api/save", () => {
  beforeEach(() => {
    vi.resetModules();
    process.env.DRIVE_SERVICE_ACCOUNT_JSON = JSON.stringify({
      client_email: "sa@p.iam.gserviceaccount.com",
      private_key: "-----BEGIN PRIVATE KEY-----\nMIIE...\n-----END PRIVATE KEY-----\n",
    });
    process.env.DRIVE_FOLDER_ID = "folder-xyz";
  });

  it("returns 500 when DRIVE_SERVICE_ACCOUNT_JSON missing", async () => {
    delete process.env.DRIVE_SERVICE_ACCOUNT_JSON;
    const { POST } = await import("../route");
    const res = await POST(
      new Request("http://x", {
        method: "POST",
        body: JSON.stringify({
          meetingId: "m1",
          title: "t",
          startedAt: "2026-05-17T14:00:00+10:00",
          endedAt: "2026-05-17T15:00:00+10:00",
          transcript: [],
          topics: [],
          actions: [],
          brand: "u",
        }),
      })
    );
    expect(res.status).toBe(500);
  });

  it("returns 500 when DRIVE_FOLDER_ID missing", async () => {
    delete process.env.DRIVE_FOLDER_ID;
    const { POST } = await import("../route");
    const res = await POST(
      new Request("http://x", {
        method: "POST",
        body: JSON.stringify({
          meetingId: "m1",
          title: "t",
          startedAt: "2026-05-17T14:00:00+10:00",
          endedAt: "2026-05-17T15:00:00+10:00",
          transcript: [],
          topics: [],
          actions: [],
          brand: "u",
        }),
      })
    );
    expect(res.status).toBe(500);
  });

  it("returns 400 on invalid JSON body", async () => {
    const { POST } = await import("../route");
    const res = await POST(new Request("http://x", { method: "POST", body: "not-json" }));
    expect(res.status).toBe(400);
  });

  it("calls mintServiceAccountToken + createDriveFile with composed markdown", async () => {
    const mockMint = vi.fn().mockResolvedValue("ya29.fake");
    const mockCreate = vi
      .fn()
      .mockResolvedValue({ fileId: "f1", webViewLink: "https://drive/f1" });
    vi.doMock("@/lib/drive-client", () => ({
      mintServiceAccountToken: mockMint,
      createDriveFile: mockCreate,
    }));
    vi.resetModules();
    const { POST } = await import("../route");
    const res = await POST(
      new Request("http://x", {
        method: "POST",
        body: JSON.stringify({
          meetingId: "m1",
          title: "Acme Q2 Pricing",
          startedAt: "2026-05-17T14:32:00+10:00",
          endedAt: "2026-05-17T15:31:42+10:00",
          transcript: [{ timestamp: "14:28", speaker: "A", text: "hi" }],
          topics: ["Q2 pricing"],
          actions: [],
          brand: "unite-group",
        }),
      })
    );
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.fileId).toBe("f1");
    expect(body.driveUrl).toBe("https://drive/f1");
    expect(mockMint).toHaveBeenCalledTimes(1);
    expect(mockCreate).toHaveBeenCalledTimes(1);
    const createArgs = mockCreate.mock.calls[0][0];
    expect(createArgs.filename).toMatch(/^2026-05-17_acme-q2-pricing\.md$/);
    expect(createArgs.content).toContain("meeting_id: m1");
    expect(createArgs.content).toContain("# Acme Q2 Pricing");
  });

  it("returns 502 when Drive create throws", async () => {
    vi.doMock("@/lib/drive-client", () => ({
      mintServiceAccountToken: vi.fn().mockResolvedValue("t"),
      createDriveFile: vi.fn().mockRejectedValue(new Error("Drive 403 forbidden")),
    }));
    vi.resetModules();
    const { POST } = await import("../route");
    const res = await POST(
      new Request("http://x", {
        method: "POST",
        body: JSON.stringify({
          meetingId: "m",
          title: "t",
          startedAt: "2026-05-17T14:00:00+10:00",
          endedAt: "2026-05-17T14:01:00+10:00",
          transcript: [],
          topics: [],
          actions: [],
          brand: "u",
        }),
      })
    );
    expect(res.status).toBe(502);
  });
});
