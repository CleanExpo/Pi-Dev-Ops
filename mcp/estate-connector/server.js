import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import { bearerMatches, configuredToken } from "./auth.js";
import { configFromEnv } from "./config.js";
import { requestAls } from "./context.js";
import { createStore } from "./store.js";
import { buildMcpServer } from "./tools.js";

const MAX_BODY = 65_536;
const ACTOR_HEADER = /^[A-Za-z][A-Za-z0-9 ._-]{0,63}$/;

export function createRuntime({ env, fetchImpl }) {
  const config = configFromEnv(env);
  return {
    config,
    store: createStore(config.stateDir),
    fetchImpl: fetchImpl || globalThis.fetch,
  };
}

export function createHttpServer(runtime) {
  return http.createServer((req, res) => {
    handle(req, res, runtime).catch((err) => {
      log({ event: "error", message: err && err.name ? err.name : "error" });
      if (!res.headersSent) sendJson(res, 500, { error: "internal" });
    });
  });
}

export function startServer(runtime, host = "127.0.0.1", port = 0) {
  const server = createHttpServer(runtime);
  return new Promise((resolve) => {
    server.listen(port, host, () => {
      const address = server.address();
      resolve({ server, port: address.port, url: `http://127.0.0.1:${address.port}` });
    });
  });
}

async function handle(req, res, runtime) {
  const pathname = new URL(req.url || "/", "http://127.0.0.1").pathname;
  if (pathname === "/healthz" && (req.method === "GET" || req.method === "HEAD")) {
    if (!runtime.config.token) {
      sendJson(res, 503, { status: "misconfigured", missing: "ESTATE_MCP_TOKEN" });
      return;
    }
    sendJson(res, 200, { status: "ok", service: "estate-connector" });
    return;
  }
  if (pathname !== "/mcp") {
    if (!bearerMatches(req.headers.authorization, runtime.config.token)) {
      sendJson(res, 401, { error: "unauthorized" });
      return;
    }
    sendJson(res, 404, { error: "not found" });
    return;
  }
  if (!bearerMatches(req.headers.authorization, runtime.config.token)) {
    sendJson(res, 401, { error: "unauthorized" });
    return;
  }
  // Stateless mode has no session to hang an SSE side-channel on. The official
  // SDK example answers GET and DELETE with 405 and serves every call as POST.
  if (req.method === "GET" || req.method === "DELETE") {
    sendJson(res, 405, { jsonrpc: "2.0", error: { code: -32000, message: "Method not allowed." }, id: null });
    return;
  }
  if (req.method !== "POST") {
    sendJson(res, 405, { error: "method not allowed" });
    return;
  }
  const header = botHeader(req);
  if (header.error) {
    sendJson(res, 400, { error: "bad X-Bot-Name" });
    return;
  }
  let body;
  try {
    body = await readBody(req);
  } catch (err) {
    sendJson(res, err.status || 400, { error: err.status === 413 ? "body too large" : "invalid json" });
    return;
  }
  const mcp = buildMcpServer(runtime);
  const transport = new StreamableHTTPServerTransport({
    sessionIdGenerator: undefined,
    enableJsonResponse: true,
  });
  let closed = false;
  const close = () => {
    if (closed) return;
    closed = true;
    transport.close().catch(() => undefined);
    mcp.close().catch(() => undefined);
  };
  res.on("close", close);
  try {
    await mcp.connect(transport);
    await requestAls.run({ botName: header.name }, () => transport.handleRequest(req, res, body));
  } catch (err) {
    close();
    throw err;
  }
}

function botHeader(req) {
  const raw = req.headers["x-bot-name"];
  if (!raw) return { name: "" };
  const value = String(Array.isArray(raw) ? raw[0] : raw).trim();
  if (!ACTOR_HEADER.test(value)) return { error: true };
  return { name: value };
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let size = 0;
    let settled = false;
    const fail = (status) => {
      if (settled) return;
      settled = true;
      reject(Object.assign(new Error("bad body"), { status }));
    };
    req.on("data", (chunk) => {
      size += chunk.length;
      if (size > MAX_BODY) {
        fail(413);
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });
    req.on("end", () => {
      if (settled) return;
      settled = true;
      if (!size) return resolve(undefined);
      try {
        resolve(JSON.parse(Buffer.concat(chunks).toString("utf8")));
      } catch {
        reject(Object.assign(new Error("invalid json"), { status: 400 }));
      }
    });
    req.on("error", () => fail(400));
  });
}

function sendJson(res, status, body) {
  const payload = JSON.stringify(body);
  res.writeHead(status, {
    "Content-Type": "application/json",
    "Content-Length": Buffer.byteLength(payload),
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
  });
  res.end(payload);
}

function log(event) {
  console.log(JSON.stringify({ ts: new Date().toISOString(), service: "estate-connector", ...event }));
}

function main() {
  const env = process.env;
  if (!configuredToken(env.ESTATE_MCP_TOKEN)) {
    log({ event: "boot", token_configured: false });
  }
  const runtime = createRuntime({ env });
  const server = createHttpServer(runtime);
  server.listen(runtime.config.port, runtime.config.host, () => {
    log({
      event: "listening",
      port: runtime.config.port,
      token_configured: Boolean(runtime.config.token),
      github_configured: Boolean(runtime.config.githubToken),
      linear_configured: Boolean(runtime.config.linearKey),
      piceo_bearer_configured: Boolean(runtime.config.piceoBearer),
      actors_restricted: Boolean(runtime.config.actors),
    });
  });
}

const isMain = process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isMain) main();
