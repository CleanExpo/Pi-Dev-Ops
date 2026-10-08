import { currentBot } from "./request-context.js";
import { normalizeBot } from "./bots.js";
import { ToolError } from "./validate.js";
import { fail, ok } from "./results.js";

function resolveActor(argBot, bots) {
  const fromRequest = currentBot();
  const fromArg = normalizeBot(argBot);
  if (fromRequest && fromArg && fromRequest !== fromArg) {
    throw new ToolError("Bot name does not match the connector URL or header.");
  }
  const bot = fromRequest || fromArg;
  if (!bot || !bots.has(bot)) {
    throw new ToolError("Name the bot with X-Estate-Bot, ?bot= on the URL, or the bot field.");
  }
  return bot;
}

/**
 * Run a write, then record who, what, and when.
 * Rejected bots are logged as well. The token is never logged.
 */
export async function auditedWrite(ctx, tool, argBot, summary, fn) {
  let bot = "unknown";
  try {
    bot = resolveActor(argBot, ctx.bots);
    const data = await fn(bot);
    await ctx.audit.record({ bot, tool, ok: true, summary });
    return ok(data);
  } catch (err) {
    const message = err instanceof ToolError ? err.message : "write failed";
    if (!(err instanceof ToolError)) console.error(`write ${tool} failed: ${err?.name || "Error"}`);
    await ctx.audit.record({ bot, tool, ok: false, summary: message });
    return fail(message);
  }
}
