// app/api/telegram/route.ts — Telegram bot: commands + multi-turn conversation history

export const dynamic = "force-dynamic";

import { NextRequest, NextResponse } from "next/server";
import { makeClient, chatWithClaude } from "@/lib/claude";

interface TelegramUpdate {
  message?: {
    chat: { id: number };
    text?: string;
    from?: { id: number; username?: string; first_name?: string };
  };
}

type Role = "user" | "assistant";
interface Turn { role: Role; content: string }

// In-memory per-chat history (survives within a single serverless instance lifetime)
// Key: chatId, Value: last N turns
const HISTORY = new Map<number, Turn[]>();
const MAX_HISTORY_TURNS = 20; // 10 user + 10 assistant

function getHistory(chatId: number): Turn[] {
  return HISTORY.get(chatId) ?? [];
}

function pushHistory(chatId: number, role: Role, content: string): void {
  const h = getHistory(chatId);
  h.push({ role, content });
  if (h.length > MAX_HISTORY_TURNS) h.splice(0, h.length - MAX_HISTORY_TURNS);
  HISTORY.set(chatId, h);
}

function clearHistory(chatId: number): void {
  HISTORY.delete(chatId);
}

async function send(chatId: number, text: string): Promise<void> {
  const token = process.env.TELEGRAM_BOT_TOKEN;
  if (!token) return;
  await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, text, parse_mode: "Markdown" }),
  });
}

async function getPiCeoStatus(): Promise<string> {
  const piUrl = (process.env.PI_CEO_URL ?? "http://127.0.0.1:7777").replace(/\/$/, "");
  const piPassword = process.env.PI_CEO_PASSWORD ?? "";
  try {
    const loginRes = await fetch(`${piUrl}/api/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: piPassword }),
      signal: AbortSignal.timeout(5000),
    });
    if (!loginRes.ok) return "Pi CEO server unreachable.";
    const cookie = loginRes.headers.get("set-cookie")?.split(";")[0] ?? "";

    const sessRes = await fetch(`${piUrl}/api/sessions`, {
      headers: { Cookie: cookie },
      signal: AbortSignal.timeout(5000),
    });
    if (!sessRes.ok) return "Could not fetch sessions.";
    const sessions: Array<{ id: string; repo: string; status: string; last_phase: string }> = await sessRes.json();

    if (sessions.length === 0) return "No build sessions. Start one via `/build <repo_url>`.";

    const active = sessions.filter((s) => ["cloning", "building", "evaluating"].includes(s.status));
    const recent = sessions.slice(0, 5);

    let msg = `*Pi CEO Status*\n`;
    msg += `Active: ${active.length} | Total: ${sessions.length}\n\n`;
    for (const s of recent) {
      const phase = s.last_phase ? ` (${s.last_phase})` : "";
      msg += `• \`${s.id}\` ${s.status}${phase}\n  ${s.repo.split("/").slice(-2).join("/")}\n`;
    }
    return msg;
  } catch {
    return "Pi CEO server unreachable.";
  }
}

async function triggerBuild(repoUrl: string): Promise<string> {
  const piUrl = (process.env.PI_CEO_URL ?? "http://127.0.0.1:7777").replace(/\/$/, "");
  const piPassword = process.env.PI_CEO_PASSWORD ?? "";
  try {
    const loginRes = await fetch(`${piUrl}/api/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: piPassword }),
      signal: AbortSignal.timeout(5000),
    });
    if (!loginRes.ok) return "Pi CEO server unreachable.";
    const cookie = loginRes.headers.get("set-cookie")?.split(";")[0] ?? "";

    const buildRes = await fetch(`${piUrl}/api/sessions`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Cookie: cookie },
      body: JSON.stringify({ repo_url: repoUrl, brief: "Triggered via Telegram" }),
      signal: AbortSignal.timeout(10_000),
    });
    if (!buildRes.ok) {
      const body = await buildRes.json().catch(() => ({})) as { detail?: string };
      return `Build failed: ${body.detail ?? `HTTP ${buildRes.status}`}`;
    }
    const data = await buildRes.json() as { session_id: string };
    return `Build started. Session: \`${data.session_id}\`\nTrack at /builds in the dashboard.`;
  } catch (e) {
    return `Build error: ${e instanceof Error ? e.message : String(e)}`;
  }
}

const HELP = `*Pi CEO Bot*

Commands:
/start — welcome message
/help — show this help
/status — show active build sessions
/build <repo\\_url> — trigger a new build
/clear — clear conversation history

Any other message is sent to Claude with full conversation context.`;

export async function POST(req: NextRequest): Promise<NextResponse> {
  const webhookSecret = process.env.TELEGRAM_WEBHOOK_SECRET;
  const incomingSecret = req.headers.get("x-telegram-bot-api-secret-token");
  if (!webhookSecret || !incomingSecret || incomingSecret !== webhookSecret) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  let update: TelegramUpdate;
  try {
    update = await req.json() as TelegramUpdate;
  } catch {
    return NextResponse.json({ ok: true });
  }

  const msg = update.message;
  if (!msg?.text) return NextResponse.json({ ok: true });

  const chatId = msg.chat.id;
  const text = msg.text.trim();
  const firstName = msg.from?.first_name ?? "there";

  // ── Commands ────────────────────────────────────────────────────────────────
  if (text === "/start") {
    await send(chatId, `👋 Hey ${firstName}! Pi CEO is online.\n\n${HELP}`);
    return NextResponse.json({ ok: true });
  }

  if (text === "/help") {
    await send(chatId, HELP);
    return NextResponse.json({ ok: true });
  }

  if (text === "/status") {
    const status = await getPiCeoStatus();
    await send(chatId, status);
    return NextResponse.json({ ok: true });
  }

  if (text.startsWith("/build ")) {
    const repoUrl = text.slice(7).trim();
    if (!repoUrl.includes("/")) {
      await send(chatId, "Usage: `/build https://github.com/owner/repo`");
      return NextResponse.json({ ok: true });
    }
    await send(chatId, `Starting build for \`${repoUrl}\`…`);
    const result = await triggerBuild(repoUrl);
    await send(chatId, result);
    return NextResponse.json({ ok: true });
  }

  if (text === "/clear") {
    clearHistory(chatId);
    await send(chatId, "Conversation history cleared.");
    return NextResponse.json({ ok: true });
  }

  // Unknown slash command
  if (text.startsWith("/")) {
    await send(chatId, `Unknown command. Try /help`);
    return NextResponse.json({ ok: true });
  }

  // ── Free-form chat with history ─────────────────────────────────────────────
  pushHistory(chatId, "user", text);

  try {
    const client = makeClient();
    const model = process.env.ANALYSIS_MODEL ?? "claude-sonnet-4-6";
    const reply = await chatWithClaude(
      client,
      model,
      getHistory(chatId),
      "User is messaging via Telegram. Be concise — Telegram has a 4096 char limit. You are the Pi CEO assistant. Help with repo analysis, build sessions, and development tasks."
    );
    pushHistory(chatId, "assistant", reply);
    await send(chatId, reply.slice(0, 4000));
  } catch (err) {
    const errMsg = err instanceof Error ? err.message : "Error";
    await send(chatId, `⚠️ ${errMsg}`);
  }

  return NextResponse.json({ ok: true });
}

// GET /api/telegram/set-webhook — registers this URL as the Telegram webhook
export async function GET(req: NextRequest): Promise<NextResponse> {
  const token = process.env.TELEGRAM_BOT_TOKEN;
  const webhookSecret = process.env.TELEGRAM_WEBHOOK_SECRET;
  if (!token) return NextResponse.json({ error: "TELEGRAM_BOT_TOKEN not set" }, { status: 500 });

  const appUrl = req.nextUrl.origin;
  const webhookUrl = `${appUrl}/api/telegram`;

  const params: Record<string, string> = { url: webhookUrl };
  if (webhookSecret) params.secret_token = webhookSecret;

  const res = await fetch(`https://api.telegram.org/bot${token}/setWebhook`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });

  const data = await res.json();
  return NextResponse.json({ webhook_url: webhookUrl, telegram_response: data });
}
