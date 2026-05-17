export const runtime = "edge";

const ASSEMBLYAI_TOKEN_URL = "https://api.assemblyai.com/v2/realtime/token";
const ASSEMBLYAI_WS_URL = "wss://api.assemblyai.com/v2/realtime/ws";
const TOKEN_EXPIRY_SECONDS = 3600;

export async function POST(_req: Request): Promise<Response> {
  const apiKey = process.env.ASSEMBLYAI_API_KEY;
  if (!apiKey) {
    return Response.json(
      { error: "ASSEMBLYAI_API_KEY not configured" },
      { status: 500 }
    );
  }

  try {
    const upstream = await fetch(ASSEMBLYAI_TOKEN_URL, {
      method: "POST",
      headers: {
        Authorization: apiKey,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ expires_in: TOKEN_EXPIRY_SECONDS }),
    });

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
