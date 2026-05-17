export const runtime = "edge";

import { composeMeetingMarkdown, type MeetingState } from "@/lib/markdown-composer";
import { slugify } from "@/lib/slug";
import {
  mintServiceAccountToken,
  mintTokenFromRefreshToken,
  createDriveFile,
} from "@/lib/drive-client";

/** Mint a Drive access token. Prefers OAuth refresh-token flow (file owned by
 * the user — works for personal Drive). Falls back to service-account JWT
 * (only works against Workspace Shared Drives — SA has no storage quota in
 * personal Drive). */
async function mintAccessToken(): Promise<string> {
  const clientId = process.env.GOOGLE_OAUTH_CLIENT_ID;
  const clientSecret = process.env.GOOGLE_OAUTH_CLIENT_SECRET;
  const refreshToken = process.env.GOOGLE_OAUTH_REFRESH_TOKEN;
  if (clientId && clientSecret && refreshToken) {
    return mintTokenFromRefreshToken({ clientId, clientSecret, refreshToken });
  }
  const saJson = process.env.DRIVE_SERVICE_ACCOUNT_JSON;
  if (saJson) {
    return mintServiceAccountToken(JSON.parse(saJson));
  }
  throw new Error(
    "No Drive auth configured. Set GOOGLE_OAUTH_* (preferred) or DRIVE_SERVICE_ACCOUNT_JSON."
  );
}

export async function POST(req: Request): Promise<Response> {
  const folderId = process.env.DRIVE_FOLDER_ID;
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
    const accessToken = await mintAccessToken();
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
