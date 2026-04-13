// app/api/chat/route.ts — Claude chat endpoint with session context awareness

export const dynamic = "force-dynamic";

import { NextRequest, NextResponse } from "next/server";
import { makeClient, chatWithClaude } from "@/lib/claude";
import { MODELS } from "@/lib/models";
import type { ChatMessage } from "@/lib/types";

interface ChatBody {
  messages: ChatMessage[];
  sessionContext?: string;
}

export async function POST(req: NextRequest): Promise<NextResponse> {
  let body: ChatBody;
  try {
    body = await req.json() as ChatBody;
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const { messages, sessionContext = "" } = body;

  if (!Array.isArray(messages) || messages.length === 0) {
    return NextResponse.json({ error: "messages array required" }, { status: 400 });
  }

  // Validate message format
  for (const m of messages) {
    if (!["user", "assistant"].includes(m.role) || typeof m.content !== "string") {
      return NextResponse.json({ error: "Invalid message format" }, { status: 400 });
    }
  }

  try {
    const client = makeClient();
    const model = MODELS.DEFAULT;
    const reply = await chatWithClaude(
      client,
      model,
      messages.map((m) => ({ role: m.role, content: m.content })),
      sessionContext
    );
    return NextResponse.json({ reply, ts: Date.now() / 1000 });
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Claude API error";
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}
