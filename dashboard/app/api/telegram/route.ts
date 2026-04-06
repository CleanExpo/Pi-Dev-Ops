// app/api/telegram/route.ts — Telegram bot webhook: routes messages to Claude chat

export const dynamic = "force-dynamic";

import { NextRequest, NextResponse } from "next/server";
import { makeClient, chatWithClaude } from "@/lib/claude";

interface TelegramUpdate {
  message?: {
    chat: { id: number };
    text?: string;
    from?: { username?: string };
  };
}

async function sendTelegramMessage(chatId: number, text: string): Promise<void> {
  const token = process.env.TELEGRAM_BOT_TOKEN;
  if (!token) return;
  await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, text, parse_mode: "Markdown" }),
  });
}

export async function POST(req: NextRequest): Promise<NextResponse> {
  // Verify this is a genuine Telegram request by checking bot token in URL
  const { searchParams } = new URL(req.url);
  const token = process.env.TELEGRAM_BOT_TOKEN;
  if (!token || searchParams.get("token") !== token) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  let update: TelegramUpdate;
  try {
    update = await req.json() as TelegramUpdate;
  } catch {
    return NextResponse.json({ ok: true }); // Telegram retries on error — always 200
  }

  const msg = update.message;
  if (!msg?.text) return NextResponse.json({ ok: true });

  const chatId = msg.chat.id;
  const text = msg.text.trim();

  try {
    const client = makeClient();
    const model = process.env.ANALYSIS_MODEL ?? "claude-opus-4-5-20250514";
    const reply = await chatWithClaude(
      client, model,
      [{ role: "user", content: text }],
      "User is messaging via Telegram. Be concise — Telegram has a 4096 char limit."
    );
    await sendTelegramMessage(chatId, reply.slice(0, 4000));
  } catch (err) {
    const errMsg = err instanceof Error ? err.message : "Error";
    await sendTelegramMessage(chatId, `⚠️ Error: ${errMsg}`);
  }

  return NextResponse.json({ ok: true });
}
