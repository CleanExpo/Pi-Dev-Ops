export const dynamic = "force-dynamic";

import { NextRequest, NextResponse } from "next/server";

const PI_CEO_URL = (process.env.PI_CEO_URL ?? "http://127.0.0.1:7777").replace(/\/$/, "");
const WEBHOOK_SECRET = process.env.TAO_WEBHOOK_SECRET ?? "";

interface BubbleBody {
  message?: string;
  conversation_id?: string;
}

export async function POST(req: NextRequest): Promise<NextResponse> {
  const cookie = req.headers.get("cookie") ?? "";
  if (!cookie.includes("tao_session=")) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  if (!WEBHOOK_SECRET) {
    return NextResponse.json(
      { error: "Margot bridge not configured (TAO_WEBHOOK_SECRET missing)" },
      { status: 503 },
    );
  }

  let body: BubbleBody;
  try {
    body = (await req.json()) as BubbleBody;
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const message = typeof body.message === "string" ? body.message.trim() : "";
  if (!message) {
    return NextResponse.json({ error: "message required" }, { status: 400 });
  }

  const chatId =
    typeof body.conversation_id === "string" && body.conversation_id.trim()
      ? body.conversation_id.trim()
      : "dashboard-unite-group";

  const upstream = await fetch(`${PI_CEO_URL}/api/margot/turn`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Pi-CEO-Secret": WEBHOOK_SECRET,
    },
    body: JSON.stringify({
      chat_id: chatId,
      user_text: message,
      tenant_id: "unite-group",
    }),
    signal: AbortSignal.timeout(260_000),
  }).catch(() => null);

  if (!upstream) {
    return NextResponse.json({ error: "Margot backend unreachable" }, { status: 502 });
  }

  const text = await upstream.text();
  return new NextResponse(text, {
    status: upstream.status,
    headers: { "Content-Type": "application/json" },
  });
}
