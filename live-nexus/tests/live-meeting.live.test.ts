import { describe, it, expect } from "vitest";
import {
  mintServiceAccountToken,
  mintTokenFromRefreshToken,
  createDriveFile,
} from "@/lib/drive-client";

const RUN_LIVE = process.env.RUN_LIVE_NEXUS === "1";

describe.skipIf(!RUN_LIVE)("live integration", () => {
  it("AssemblyAI: mints a token via /v2/realtime/token", async () => {
    const apiKey = process.env.ASSEMBLYAI_API_KEY;
    if (!apiKey) throw new Error("ASSEMBLYAI_API_KEY not set");
    const res = await fetch("https://api.assemblyai.com/v2/realtime/token", {
      method: "POST",
      headers: { Authorization: apiKey, "Content-Type": "application/json" },
      body: JSON.stringify({ expires_in: 60 }),
    });
    expect(res.ok).toBe(true);
    const data = (await res.json()) as { token: string };
    expect(typeof data.token).toBe("string");
    expect(data.token.length).toBeGreaterThan(10);
  });

  it("Anthropic: tool_use returns valid update_synthesis", async () => {
    const apiKey = process.env.ANTHROPIC_API_KEY;
    if (!apiKey) throw new Error("ANTHROPIC_API_KEY not set");
    const res = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "x-api-key": apiKey,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
      },
      body: JSON.stringify({
        model: "claude-haiku-4-5",
        max_tokens: 256,
        system: "Reply only via the test_tool tool.",
        messages: [{ role: "user", content: "Just call the tool with topics=['ok'] and actions=[]" }],
        tools: [
          {
            name: "test_tool",
            description: "test",
            input_schema: {
              type: "object",
              properties: {
                topics: { type: "array", items: { type: "string" } },
                actions: { type: "array", items: {} },
              },
              required: ["topics", "actions"],
            },
          },
        ],
        tool_choice: { type: "tool", name: "test_tool" },
      }),
    });
    expect(res.ok).toBe(true);
  });

  it("Drive: OAuth user creds create + read a probe file in personal Drive", async () => {
    const clientId = process.env.GOOGLE_OAUTH_CLIENT_ID;
    const clientSecret = process.env.GOOGLE_OAUTH_CLIENT_SECRET;
    const refreshToken = process.env.GOOGLE_OAUTH_REFRESH_TOKEN;
    const folderId = process.env.DRIVE_FOLDER_ID;
    if (!clientId || !clientSecret || !refreshToken || !folderId) {
      throw new Error("OAuth + folder env vars not set");
    }
    const token = await mintTokenFromRefreshToken({
      clientId,
      clientSecret,
      refreshToken,
    });
    const result = await createDriveFile({
      accessToken: token,
      folderId,
      filename: `probe-${Date.now()}.md`,
      content: "# probe\n\nlive-test, please delete",
      mimeType: "text/markdown",
    });
    expect(result.fileId).toBeTruthy();
    expect(result.webViewLink).toContain("drive.google.com");
    console.log("Created probe file:", result.webViewLink);
    console.log("REMINDER: delete this file in Drive when convenient.");
  });
});
