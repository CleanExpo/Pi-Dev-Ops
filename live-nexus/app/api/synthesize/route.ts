export const runtime = "edge";

const ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages";
const ANTHROPIC_MODEL = "claude-haiku-4-5";
const ANTHROPIC_VERSION = "2023-06-01";

const UPDATE_SYNTHESIS_TOOL = {
  name: "update_synthesis",
  description:
    "Update the meeting's running list of topics discussed and action items, based on the latest transcript chunk plus the prior state.",
  input_schema: {
    type: "object",
    properties: {
      topics: {
        type: "array",
        description:
          "Updated list of distinct topics discussed in the meeting so far. Append new topics to the existing list; do not remove prior ones unless they were clearly retracted.",
        items: { type: "string" },
      },
      actions: {
        type: "array",
        description:
          "Updated list of action items / commitments. Each must be a concrete commitment ('I'll send X', 'Toby will check Y'). Skip vague mentions.",
        items: {
          type: "object",
          properties: {
            title: { type: "string" },
            description: { type: "string" },
            priority: { type: "integer", minimum: 0, maximum: 4 },
          },
          required: ["title", "description", "priority"],
        },
      },
    },
    required: ["topics", "actions"],
  },
};

const SYSTEM_PROMPT = `You are a real-time meeting synthesizer. Given the latest 30 seconds of transcript plus the running state of topics and action items, return the UPDATED full lists.

Rules:
- Topics: short noun phrases ("Q2 pricing tiers", not "we talked about Q2 pricing"). Keep prior topics. Add new ones if discussed.
- Actions: only concrete commitments. Skip philosophical musings.
- Priority: 0=None, 1=Urgent, 2=High (has deadline), 3=Normal, 4=Low.
- Always use the update_synthesis tool. Never reply with prose.`;

export async function POST(req: Request): Promise<Response> {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) {
    return Response.json({ error: "ANTHROPIC_API_KEY not configured" }, { status: 500 });
  }

  let body: { transcript: string; current_topics: string[]; current_actions: unknown[] };
  try {
    body = await req.json();
  } catch {
    return Response.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const userMessage = JSON.stringify({
    new_transcript_chunk: body.transcript,
    current_topics: body.current_topics ?? [],
    current_actions: body.current_actions ?? [],
  });

  try {
    const upstream = await fetch(ANTHROPIC_API_URL, {
      method: "POST",
      headers: {
        "x-api-key": apiKey,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
      },
      body: JSON.stringify({
        model: ANTHROPIC_MODEL,
        max_tokens: 1024,
        system: SYSTEM_PROMPT,
        messages: [{ role: "user", content: userMessage }],
        tools: [UPDATE_SYNTHESIS_TOOL],
        tool_choice: { type: "tool", name: "update_synthesis" },
      }),
    });

    if (!upstream.ok) {
      const text = await upstream.text();
      console.error(
        "[api/synthesize] Anthropic non-2xx:",
        upstream.status,
        text.slice(0, 500)
      );
      return Response.json({ error: "Upstream synthesis failed" }, { status: 502 });
    }

    const data = (await upstream.json()) as {
      content?: Array<{ type: string; name?: string; input?: unknown }>;
    };
    const toolUse = data.content?.find(
      (b) => b.type === "tool_use" && b.name === "update_synthesis"
    );
    if (!toolUse?.input) {
      return Response.json({ topics: [], actions: [] });
    }
    const input = toolUse.input as { topics: string[]; actions: unknown[] };
    return Response.json({ topics: input.topics ?? [], actions: input.actions ?? [] });
  } catch (e) {
    console.error("[api/synthesize] transport error:", e);
    return Response.json({ error: "Upstream unreachable" }, { status: 502 });
  }
}
