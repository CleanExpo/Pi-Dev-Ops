export const runtime = "edge";

import { composeMeetingMarkdown, type MeetingState } from "@/lib/markdown-composer";
import { slugify } from "@/lib/slug";
import { mintServiceAccountToken, createDriveFile } from "@/lib/drive-client";

export async function POST(req: Request): Promise<Response> {
  const saJson = process.env.DRIVE_SERVICE_ACCOUNT_JSON;
  const folderId = process.env.DRIVE_FOLDER_ID;

  if (!saJson) {
    return Response.json(
      { error: "DRIVE_SERVICE_ACCOUNT_JSON not configured" },
      { status: 500 }
    );
  }
  if (!folderId) {
    return Response.json({ error: "DRIVE_FOLDER_ID not configured" }, { status: 500 });
  }

  let state: MeetingState;
  try {
    state = (await req.json()) as MeetingState;
  } catch {
    return Response.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const markdown = composeMeetingMarkdown(state);
  const dateStr = state.startedAt.slice(0, 10);
  const slug = slugify(state.title || "meeting");
  const filename = `${dateStr}_${slug}.md`;

  try {
    const saKey = JSON.parse(saJson);
    const accessToken = await mintServiceAccountToken(saKey);
    const result = await createDriveFile({
      accessToken,
      folderId,
      filename,
      content: markdown,
      mimeType: "text/markdown",
    });
    return Response.json({ fileId: result.fileId, driveUrl: result.webViewLink });
  } catch (e) {
    console.error("[api/save] Drive save failed:", e);
    return Response.json({ error: String((e as Error).message) }, { status: 502 });
  }
}
