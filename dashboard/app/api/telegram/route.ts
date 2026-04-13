// app/api/telegram/route.ts — Pi CEO Telegram interface: CEO delegation + commands

export const dynamic = "force-dynamic";

import { NextRequest, NextResponse, after } from "next/server";
import Anthropic from "@anthropic-ai/sdk";
import { MODELS } from "@/lib/models";

// ── Types ─────────────────────────────────────────────────────────────────────

interface TelegramUpdate {
  message?: {
    chat: { id: number };
    text?: string;
    from?: { id: number; username?: string; first_name?: string };
  };
}

type Role = "user" | "assistant";
interface Turn { role: Role; content: string }

// ── Conversation history ──────────────────────────────────────────────────────

const HISTORY = new Map<number, Turn[]>();
const MAX_HISTORY_TURNS = 20;

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

// ── Telegram send ─────────────────────────────────────────────────────────────

async function send(chatId: number, text: string): Promise<void> {
  const token = process.env.TELEGRAM_BOT_TOKEN;
  if (!token) return;
  await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, text, parse_mode: "Markdown" }),
  });
}

// ── Linear ────────────────────────────────────────────────────────────────────

const LINEAR_TEAM_ID = "a8a52f07-63cf-4ece-9ad2-3e3bd3c15673"; // RestoreAssist

async function linearGQL(query: string, variables: Record<string, unknown>): Promise<Record<string, unknown>> {
  const apiKey = process.env.LINEAR_API_KEY ?? "";
  if (!apiKey) return { error: "LINEAR_API_KEY not configured" };
  const res = await fetch("https://api.linear.app/graphql", {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: apiKey },
    body: JSON.stringify({ query, variables }),
    signal: AbortSignal.timeout(8000),
  });
  return res.json() as Promise<Record<string, unknown>>;
}

async function createLinearIssue(
  title: string,
  description: string,
  priority: number,
): Promise<string> {
  type GQLResult = { data?: { issueCreate?: { success: boolean; issue?: { identifier: string; url: string } } } };
  const result = await linearGQL(
    `mutation CreateIssue($title: String!, $desc: String!, $priority: Int!, $teamId: String!) {
       issueCreate(input: { title: $title, description: $desc, priority: $priority, teamId: $teamId }) {
         success
         issue { identifier url }
       }
     }`,
    { title, desc: description, priority, teamId: LINEAR_TEAM_ID },
  ) as GQLResult;
  const issue = result.data?.issueCreate?.issue;
  if (issue) return `Created *${issue.identifier}*: ${title}\n${issue.url}`;
  return `Failed to create Linear issue (check LINEAR_API_KEY)`;
}

async function getLinearBacklog(): Promise<string> {
  type GQLResult = { data?: { issues?: { nodes: Array<{ identifier: string; title: string; state: { name: string }; priority: number }> } } };
  const result = await linearGQL(
    `query Backlog($teamId: ID!) {
       issues(filter: {
         team: { id: { eq: $teamId } },
         state: { type: { nin: ["completed", "cancelled"] } }
       }, orderBy: priority, first: 8) {
         nodes { identifier title state { name } priority }
       }
     }`,
    { teamId: LINEAR_TEAM_ID },
  ) as GQLResult;
  const nodes = result.data?.issues?.nodes ?? [];
  if (!nodes.length) return "No open issues.";
  const priorityLabel = (p: number) => ["", "🔴 Urgent", "🟠 High", "🟡 Normal", "⚪ Low"][p] ?? "?";
  return nodes.map((n) => `${priorityLabel(n.priority)} *${n.identifier}* ${n.title} [${n.state.name}]`).join("\n");
}

// ── Pi CEO server ──────────────────────────────────────────────────────────────

async function piCeoLogin(): Promise<string | null> {
  const piUrl = (process.env.PI_CEO_URL ?? "http://127.0.0.1:7777").replace(/\/$/, "");
  const piPassword = process.env.PI_CEO_PASSWORD ?? "";
  const res = await fetch(`${piUrl}/api/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password: piPassword }),
    signal: AbortSignal.timeout(5000),
  });
  if (!res.ok) return null;
  return res.headers.get("set-cookie")?.split(";")[0] ?? null;
}

async function getPiCeoStatus(): Promise<string> {
  const piUrl = (process.env.PI_CEO_URL ?? "http://127.0.0.1:7777").replace(/\/$/, "");
  try {
    const cookie = await piCeoLogin();
    if (!cookie) return "Pi CEO server unreachable — check PI_CEO_PASSWORD.";
    const sessRes = await fetch(`${piUrl}/api/sessions`, {
      headers: { Cookie: cookie },
      signal: AbortSignal.timeout(5000),
    });
    if (!sessRes.ok) return "Could not fetch sessions.";
    const sessions: Array<{ id: string; repo: string; status: string; last_phase: string }> = await sessRes.json();
    if (!sessions.length) return "No build sessions. Send a task to create one.";
    const active = sessions.filter((s) => ["cloning", "building", "evaluating"].includes(s.status));
    const recent = sessions.slice(0, 5);
    let msg = `*Pi CEO Status*\nActive: ${active.length} | Total: ${sessions.length}\n\n`;
    for (const s of recent) {
      const phase = s.last_phase ? ` (${s.last_phase})` : "";
      msg += `• \`${s.id}\` ${s.status}${phase}\n  ${s.repo.split("/").slice(-2).join("/")}\n`;
    }
    return msg;
  } catch {
    return "Pi CEO server unreachable.";
  }
}

async function triggerBuild(repoUrl: string, brief: string = "Triggered via Telegram"): Promise<string> {
  const piUrl = (process.env.PI_CEO_URL ?? "http://127.0.0.1:7777").replace(/\/$/, "");
  try {
    const cookie = await piCeoLogin();
    if (!cookie) return "Pi CEO server unreachable — check PI_CEO_PASSWORD.";
    const buildRes = await fetch(`${piUrl}/api/sessions`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Cookie: cookie },
      body: JSON.stringify({ repo_url: repoUrl, brief }),
      signal: AbortSignal.timeout(10_000),
    });
    if (!buildRes.ok) {
      const body = await buildRes.json().catch(() => ({})) as { detail?: string };
      return `Build failed: ${body.detail ?? `HTTP ${buildRes.status}`}`;
    }
    const data = await buildRes.json() as { session_id: string };
    return `Build started: \`${data.session_id}\``;
  } catch (e) {
    return `Build error: ${e instanceof Error ? e.message : String(e)}`;
  }
}

// ── CEO agent ─────────────────────────────────────────────────────────────────

const CEO_SYSTEM = `You are the Pi CEO delegate — an autonomous chief of staff operating from a phone.
The user is the CEO. Every message is a delegation. Your job is not to discuss, it is to EXECUTE.

BEHAVIOUR:
- Task given → call create_linear_issue immediately, then confirm what was created
- "Status" or "what's running" → call get_pi_ceo_status
- "Backlog" or "what's open" → call get_linear_backlog
- "Build <repo>" → call trigger_build with the repo URL and a brief derived from context
- Follow-up questions → answer concisely from conversation history
- Never ask for permission. Never say "I'll help you with that." Just do it and confirm.

PRIORITY MAPPING (for create_linear_issue):
- Urgent / critical / asap / broken → priority 1
- High / important / soon → priority 2
- Normal / standard (default) → priority 3
- Low / nice to have / later → priority 4

PROJECTS context:
- Pi-CEO / Pi Dev Ops → pi-ceo-dev-ops repo, team RestoreAssist
- Pi-SEO → scanner/health dashboard
- RestoreAssist → the main RA app

Telegram limit: 4096 chars. Be concise.`;

const CEO_TOOLS: Anthropic.Tool[] = [
  {
    name: "create_linear_issue",
    description: "Create a new Linear issue for engineering work. Call this whenever the user delegates a task.",
    input_schema: {
      type: "object" as const,
      properties: {
        title: { type: "string", description: "Short issue title (max 80 chars)" },
        description: { type: "string", description: "Full task description with context and acceptance criteria" },
        priority: { type: "number", description: "1=Urgent, 2=High, 3=Normal, 4=Low" },
      },
      required: ["title", "description", "priority"],
    },
  },
  {
    name: "trigger_build",
    description: "Start a Pi CEO build session for a GitHub repository.",
    input_schema: {
      type: "object" as const,
      properties: {
        repo_url: { type: "string", description: "Full GitHub repository URL" },
        brief: { type: "string", description: "What to build or fix — one sentence" },
      },
      required: ["repo_url", "brief"],
    },
  },
  {
    name: "get_pi_ceo_status",
    description: "Get current Pi CEO build sessions and recent activity.",
    input_schema: { type: "object" as const, properties: {}, required: [] },
  },
  {
    name: "get_linear_backlog",
    description: "Get open Linear issues sorted by priority.",
    input_schema: { type: "object" as const, properties: {}, required: [] },
  },
];

type ToolInput = {
  create_linear_issue: { title: string; description: string; priority: number };
  trigger_build: { repo_url: string; brief: string };
  get_pi_ceo_status: Record<string, never>;
  get_linear_backlog: Record<string, never>;
};

async function executeTool(name: string, input: Record<string, unknown>): Promise<string> {
  if (name === "create_linear_issue") {
    const { title, description, priority } = input as ToolInput["create_linear_issue"];
    return createLinearIssue(title, description, priority);
  }
  if (name === "trigger_build") {
    const { repo_url, brief } = input as ToolInput["trigger_build"];
    return triggerBuild(repo_url, brief);
  }
  if (name === "get_pi_ceo_status") {
    return getPiCeoStatus();
  }
  if (name === "get_linear_backlog") {
    return getLinearBacklog();
  }
  return `Unknown tool: ${name}`;
}

async function ceoAgentCall(history: Turn[]): Promise<string> {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) {
    // Fallback: plain chat without tools
    const client = new Anthropic({ apiKey: "" });
    try {
      const response = await client.messages.create({
        model: MODELS.DEFAULT,
        max_tokens: 1024,
        system: CEO_SYSTEM,
        messages: history,
      });
      const block = response.content[0];
      return block.type === "text" ? block.text : "(no response)";
    } catch {
      return "ANTHROPIC_API_KEY not set — cannot process free-form messages.";
    }
  }

  const client = new Anthropic({ apiKey });
  const messages: Anthropic.MessageParam[] = history.map((t) => ({
    role: t.role,
    content: t.content,
  }));

  // Agentic loop: up to 5 turns to handle tool calls
  for (let turn = 0; turn < 5; turn++) {
    const response = await client.messages.create({
      model: MODELS.DEFAULT,
      max_tokens: 1024,
      system: CEO_SYSTEM,
      tools: CEO_TOOLS,
      messages,
    });

    if (response.stop_reason === "end_turn") {
      return response.content
        .filter((b): b is Anthropic.TextBlock => b.type === "text")
        .map((b) => b.text)
        .join("");
    }

    if (response.stop_reason === "tool_use") {
      messages.push({ role: "assistant", content: response.content });
      const toolResults: Anthropic.ToolResultBlockParam[] = [];
      for (const block of response.content) {
        if (block.type === "tool_use") {
          const result = await executeTool(block.name, block.input as Record<string, unknown>);
          toolResults.push({
            type: "tool_result",
            tool_use_id: block.id,
            content: result,
          });
        }
      }
      messages.push({ role: "user", content: toolResults });
      continue;
    }

    break;
  }

  return "Done.";
}

// ── Background analysis trigger ───────────────────────────────────────────────
// Fires the 8-phase analysis SSE stream in background via next/server after().
// The analyze route sends a Telegram completion notification when done —
// no need to block the bot response waiting for the 5-min analysis.

function triggerAnalysisBackground(repoUrl: string, appOrigin: string, ghToken?: string): void {
  after(async () => {
    try {
      const url = new URL(`${appOrigin}/api/analyze`);
      url.searchParams.set("repo", repoUrl);
      if (ghToken) url.searchParams.set("token", ghToken);
      // Consume the SSE stream — the analyze route sends Telegram notification on done/error
      const res = await fetch(url.toString(), {
        headers: { "x-webhook-trigger": "telegram" },
        signal: AbortSignal.timeout(295_000), // just under Vercel 300s
      });
      // Drain response so the SSE stream completes fully
      if (res.body) {
        const reader = res.body.getReader();
        while (true) {
          const { done } = await reader.read();
          if (done) break;
        }
      }
    } catch { /* analyze route handles its own Telegram error notification */ }
  });
}

// ── Commands ──────────────────────────────────────────────────────────────────

const HELP = `*Pi CEO — CEO Interface*

Delegate tasks by typing naturally. Examples:
_"Fix login timeout in RestoreAssist, high priority"_
_"Add dark mode to dashboard, normal priority"_
_"What's running?"_ · _"Show backlog"_

Slash commands:
/analyze <github\\_url> — run full 8-phase analysis (notifies here when done)
/status — active Railway build sessions
/backlog — open Linear issues
/build <repo\\_url> — trigger a Railway build
/clear — clear conversation history
/help — this message`;

// ── Chat ID allowlist (owner-only access) ─────────────────────────────────────
// TELEGRAM_CHAT_ID env var is the owner's numeric chat ID.
// If set, ALL messages from other chat IDs are silently dropped.
// Get your chat ID by sending /start to @userinfobot on Telegram.

function isAuthorized(chatId: number): boolean {
  const allowed = process.env.TELEGRAM_CHAT_ID?.trim();
  if (!allowed) return true; // not configured — open (dev mode)
  return String(chatId) === allowed;
}

// ── POST handler ──────────────────────────────────────────────────────────────

export async function POST(req: NextRequest): Promise<NextResponse> {
  const webhookSecret = process.env.TELEGRAM_WEBHOOK_SECRET;
  const incomingSecret = req.headers.get("x-telegram-bot-api-secret-token");
  if (webhookSecret && incomingSecret && incomingSecret !== webhookSecret) {
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

  // Silently ignore messages from unauthorized chat IDs
  if (!isAuthorized(chatId)) return NextResponse.json({ ok: true });

  const text = msg.text.trim();
  const firstName = msg.from?.first_name ?? "there";

  // ── Slash commands ──────────────────────────────────────────────────────────

  if (text === "/start") {
    await send(chatId, `👋 Hey ${firstName}! Pi CEO is online and ready.\n\n${HELP}`);
    return NextResponse.json({ ok: true });
  }

  if (text === "/help") {
    await send(chatId, HELP);
    return NextResponse.json({ ok: true });
  }

  if (text === "/status") {
    await send(chatId, await getPiCeoStatus());
    return NextResponse.json({ ok: true });
  }

  if (text === "/backlog") {
    await send(chatId, await getLinearBacklog());
    return NextResponse.json({ ok: true });
  }

  if (text.startsWith("/analyze ")) {
    const repoUrl = text.slice(9).trim();
    if (!repoUrl.includes("github.com/")) {
      await send(chatId, "Usage: `/analyze https://github.com/owner/repo`");
      return NextResponse.json({ ok: true });
    }
    const appOrigin = req.nextUrl.origin;
    const ghToken = process.env.GITHUB_TOKEN?.trim();
    triggerAnalysisBackground(repoUrl, appOrigin, ghToken);
    await send(chatId,
      `🔍 *Analysis started*\nRepo: \`${repoUrl}\`\n\nRunning 8 phases — I'll message you here when complete (~5 min).`
    );
    return NextResponse.json({ ok: true });
  }

  if (text.startsWith("/build ")) {
    const repoUrl = text.slice(7).trim();
    if (!repoUrl.includes("/")) {
      await send(chatId, "Usage: `/build https://github.com/owner/repo`");
      return NextResponse.json({ ok: true });
    }
    await send(chatId, `Starting build for \`${repoUrl}\`…`);
    await send(chatId, await triggerBuild(repoUrl));
    return NextResponse.json({ ok: true });
  }

  if (text === "/clear") {
    clearHistory(chatId);
    await send(chatId, "Conversation cleared.");
    return NextResponse.json({ ok: true });
  }

  if (text.startsWith("/")) {
    await send(chatId, `Unknown command. Try /help`);
    return NextResponse.json({ ok: true });
  }

  // ── CEO agent (free-form) ───────────────────────────────────────────────────

  pushHistory(chatId, "user", text);

  try {
    const reply = await ceoAgentCall(getHistory(chatId));
    pushHistory(chatId, "assistant", reply);
    await send(chatId, reply.slice(0, 4000));
  } catch (err) {
    const errMsg = err instanceof Error ? err.message : String(err);
    await send(chatId, `⚠️ ${errMsg.slice(0, 500)}`);
  }

  return NextResponse.json({ ok: true });
}

// ── GET: register webhook ──────────────────────────────────────────────────────

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
