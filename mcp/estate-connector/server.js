import path from "node:path";
import { fileURLToPath } from "node:url";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import { createMcpExpressApp } from "@modelcontextprotocol/sdk/server/express.js";
import { bearerOk, unauthorized } from "./lib/auth.js";
import { createContext } from "./lib/context.js";
import { registerAll } from "./lib/register.js";
import { botsFromRequest, runWithBot } from "./lib/request-context.js";

const VERSION = "1.0.0";

export function buildApp(opts = {}) {
  const env = opts.env || process.env;
  const token = opts.token ?? env.ESTATE_MCP_TOKEN ?? "";
  if (token.length < 16) {
    throw new Error("ESTATE_MCP_TOKEN must be at least 16 characters.");
  }
  const host = opts.host || env.ESTATE_MCP_HOST || "0.0.0.0";
  const ctx = createContext({ ...opts, env });
  const allowed = hostList(env.ESTATE_MCP_ALLOWED_HOSTS);
  const app = createMcpExpressApp(allowed.length ? { host, allowedHosts: allowed } : { host });
  app.get("/healthz", (_req, res) => {
    res.status(200).json({ status: "ok" });
  });
  app.use((req, res, next) => {
    if (req.path === "/healthz") return next();
    if (!bearerOk(req.headers.authorization, token)) return unauthorized(res);
    return next();
  });
  app.post("/mcp", (req, res) => handleMcp(req, res, ctx));
  app.get("/mcp", (_req, res) => methodNotAllowed(res));
  app.delete("/mcp", (_req, res) => methodNotAllowed(res));
  return app;
}

async function handleMcp(req, res, ctx) {
  const named = botsFromRequest(req.get("x-estate-bot"), req.query?.bot);
  if (named.mismatch) {
    res.status(400).json({ error: "bot mismatch" });
    return;
  }
  const server = new McpServer({ name: "estate-connector", version: VERSION });
  registerAll(server, ctx);
  const transport = new StreamableHTTPServerTransport({
    sessionIdGenerator: undefined,
    enableJsonResponse: true,
  });
  res.on("close", () => {
    transport.close();
    server.close();
  });
  try {
    await runWithBot(named.bot, async () => {
      await server.connect(transport);
      await transport.handleRequest(req, res, req.body);
    });
  } catch (err) {
    console.error(`mcp request failed: ${err?.name || "Error"}`);
    if (!res.headersSent) {
      res.status(500).json({
        jsonrpc: "2.0",
        error: { code: -32603, message: "Internal server error" },
        id: null,
      });
    }
  }
}

function methodNotAllowed(res) {
  res.status(405).set("Allow", "POST").json({
    jsonrpc: "2.0",
    error: { code: -32000, message: "Method not allowed." },
    id: null,
  });
}

function hostList(raw) {
  return String(raw || "").split(",").map((item) => item.trim()).filter(Boolean);
}

function main() {
  try {
    const app = buildApp({ env: process.env });
    const port = Number(process.env.PORT || process.env.ESTATE_MCP_PORT || 8787);
    const host = process.env.ESTATE_MCP_HOST || "0.0.0.0";
    app.listen(port, host, () => {
      console.log(`estate-connector listening on port ${port}`);
    });
  } catch (err) {
    console.error(err instanceof Error ? err.message : "startup failed");
    process.exit(1);
  }
}

const thisFile = fileURLToPath(import.meta.url);
if (process.argv[1] && path.resolve(process.argv[1]) === thisFile) main();
