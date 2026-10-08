import { ToolError } from "./validate.js";
import { fail } from "./results.js";
import { adapters } from "../adapters/registry.js";

export function registerAll(server, ctx) {
  for (const adapter of adapters) {
    for (const tool of adapter.tools(ctx)) registerOne(server, ctx, tool);
  }
}

function registerOne(server, ctx, tool) {
  server.registerTool(tool.name, {
    title: tool.title,
    description: tool.description,
    inputSchema: tool.inputSchema,
    annotations: {
      readOnlyHint: tool.readOnly,
      destructiveHint: false,
      idempotentHint: false,
      openWorldHint: false,
    },
  }, (args) => invoke(tool, args || {}, ctx));
}

async function invoke(tool, args, ctx) {
  try {
    return await tool.handler(args, ctx);
  } catch (err) {
    if (!(err instanceof ToolError)) console.error(`tool ${tool.name} failed: ${err?.name || "Error"}`);
    const message = err instanceof ToolError ? err.message : "tool failed";
    return fail(message);
  }
}
