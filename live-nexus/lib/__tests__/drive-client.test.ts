import { describe, it, expect, vi, beforeEach } from "vitest";
import { createDriveFile } from "../drive-client";

describe("createDriveFile", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  it("posts multipart upload to Drive with parent folder", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          id: "file-xyz",
          webViewLink: "https://drive.google.com/file/d/file-xyz/view",
        }),
        { status: 200 }
      )
    );

    const result = await createDriveFile({
      accessToken: "ya29.fake_token",
      folderId: "folder-abc",
      filename: "2026-05-17_acme.md",
      content: "# Acme\n\nbody",
      mimeType: "text/markdown",
    });

    expect(result.fileId).toBe("file-xyz");
    expect(result.webViewLink).toBe("https://drive.google.com/file/d/file-xyz/view");

    const call = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(call[0]).toContain("upload/drive/v3/files");
    const init = call[1] as RequestInit;
    expect((init.headers as Record<string, string>).Authorization).toBe(
      "Bearer ya29.fake_token"
    );
  });

  it("includes folder ID as parent in metadata", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      new Response(JSON.stringify({ id: "f", webViewLink: "" }))
    );
    await createDriveFile({
      accessToken: "t",
      folderId: "FOLDER123",
      filename: "x.md",
      content: "hi",
      mimeType: "text/markdown",
    });
    const body = (globalThis.fetch as ReturnType<typeof vi.fn>).mock
      .calls[0][1].body as string;
    expect(body).toContain("FOLDER123");
    expect(body).toContain("x.md");
  });

  it("throws on non-2xx response", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      new Response("forbidden", { status: 403 })
    );
    await expect(
      createDriveFile({
        accessToken: "t",
        folderId: "f",
        filename: "x.md",
        content: "y",
        mimeType: "text/markdown",
      })
    ).rejects.toThrow();
  });
});
