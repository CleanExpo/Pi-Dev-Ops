export const runtime = "edge";

// AssemblyAI v3 streaming token endpoint.
// v2 (`/v2/realtime/token`) was deprecated and returns HTTP 410.
// See: https://www.assemblyai.com/docs/streaming/streaming-api
const ASSEMBLYAI_TOKEN_URL = "https://streaming.assemblyai.com/v3/token";
const ASSEMBLYAI_WS_URL = "wss://streaming.assemblyai.com/v3/ws";
const TOKEN_EXPIRY_SECONDS = 60; // v3 caps at 600 for single-use; 60 is fine for a hand-off

export async function POST(_req: Request): Promise<Response> {
  const apiKey = process.env.ASSEMBLYAI_API_KEY;
  if (!apiKey) {
    return Response.json(
      { error: "ASSEMBLYAI_API_KEY not configured" },
      { status: 500 }
    );
  }

  try {
    // v3 token endpoint is a GET with query params, not POST.
    const upstream = await fetch(
      `${ASSEMBLYAI_TOKEN_URL}?expires_in_seconds=${TOKEN_EXPIRY_SECONDS}`,
      {
        method: "GET",
        headers: {
          // v3 uses the raw API key as Authorization (no Bearer prefix).
          Authorization: apiKey,
        },
      }
    );

    if (!upstream.ok) {
      const text = await upstream.text();
      console.error("[api/session] AssemblyAI rejected:", upstream.status, text);
      return Response.json({ error: "Upstream token mint failed" }, { status: 502 });
    }

    const data = (await upstream.json()) as { token: string };
    return Response.json({
      token: data.token,
      ws_url: ASSEMBLYAI_WS_URL,
      expires_at: Date.now() + TOKEN_EXPIRY_SECONDS * 1000,
    });
  } catch (e) {
    console.error("[api/session] transport error:", e);
    return Response.json({ error: "Upstream unreachable" }, { status: 502 });
  }
}
