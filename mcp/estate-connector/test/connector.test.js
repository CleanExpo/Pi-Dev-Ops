import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { createRuntime, startServer } from "../server.js";
import { READ_TOOL_NAMES, WRITE_TOOL_NAMES } from "../tools.js";

const TOKEN = "estate-test-token-1";
const HERE = path.dirname(fileURLToPath(import.meta.url));
const REAL_PROJECTS = path.resolve(HERE, "../../../config/harness/projects.json");

function jsonResponse(body, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    async text() {
      return JSON.stringify(body);
    },
  };
}

async function boot(extraEnv = {}) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "estate-mcp-"));
  const projects = path.join(dir, "projects.json");
  fs.writeFileSync(projects, JSON.stringify({
    projects: [
      {
        id: "pi-dev-ops",
        repo: "CleanExpo/Pi-Dev-Ops",
        linear_project_id: "pid",
        linear_project_name: "Pi - Dev -Ops",
        deployments: { backend: "https://pi-dev-ops-production.up.railway.app" },
      },
      {
        id: "unite-group",
        repo: "CleanExpo/unite-group",
        linear_project_id: "uid",
        linear_project_name: "Unite-Group",
        deployments: { frontend: "https://unite-group.vercel.app" },
      },
    ],
  }));
  const calls = [];
  const fetchImpl = async (url, opts) => {
    calls.push({ url: String(url), opts });
    const target = String(url);
    if (target.endsWith("/health")) return jsonResponse({ status: "ok", uptime_s: 3, linear_api_key: true, sessions: { active: 0 } });
    if (target.includes("/api/mission-control/live")) {
      return jsonResponse({
        ts: "2026-10-08T00:00:00Z",
        queue: { urgent: 1, high: 0, next_issue_id: "RA-1", next_issue_title: "Fix the gate" },
        active_sessions: [{ id: "s1", repo: "CleanExpo/Pi-Dev-Ops", phase: "build", elapsed_s: 4, prompt: "hidden" }],
        pulse: { last_at: null },
      });
    }
    if (target.includes("api.github.com")) {
      return jsonResponse({
        full_name: "CleanExpo/Unite-Group",
        default_branch: "main",
        pushed_at: "2026-10-01T00:00:00Z",
        open_issues_count: 2,
        visibility: "private",
        workflow_runs: [],
      });
    }
    if (target.includes("api.linear.app")) {
      return jsonResponse({
        data: {
          issues: {
            nodes: [
              { identifier: "RA-9", title: "Pi queue", priority: 2, url: "https://linear.app/ra", project: { id: "pid", name: "Pi" }, state: { name: "Ready for Pi-Dev" } },
              { identifier: "UNI-3", title: "Unite queue", priority: 1, url: "https://linear.app/uni", project: { id: "uid", name: "Unite" }, state: { name: "Ready for Pi-Dev" } },
            ],
          },
        },
      });
    }
    return jsonResponse({ error: "unexpected" }, 500);
  };
  const runtime = createRuntime({
    env: {
      ESTATE_MCP_TOKEN: TOKEN,
      ESTATE_MCP_STATE_DIR: dir,
      ESTATE_PROJECTS_PATH: projects,
      PICEO_BASE_URL: "http://127.0.0.1:9",
      PICEO_BEARER: "tao-test-bearer",
      GITHUB_TOKEN: "gh-test-token-value",
      LINEAR_API_KEY: "lin-test-secret",
      ...extraEnv,
    },
    fetchImpl,
  });
  const started = await startServer(runtime);
  return { ...started, dir, calls };
}

async function rpc(url, token, body, headers = {}) {
  const reqHeaders = {
    "Content-Type": "application/json",
    Accept: "application/json, text/event-stream",
    "mcp-protocol-version": "2025-11-25",
    ...headers,
  };
  if (token) reqHeaders.Authorization = `Bearer ${token}`;
  const res = await fetch(`${url}/mcp`, { method: "POST", headers: reqHeaders, body: JSON.stringify(body) });
  const text = await res.text();
  let json = null;
  try {
    json = JSON.parse(text);
  } catch {
    json = parseSse(text);
  }
  return { status: res.status, json, text };
}

function parseSse(text) {
  const data = text.split("\n").filter((line) => line.startsWith("data:")).map((line) => line.slice(5).trim()).filter(Boolean);
  if (!data.length) return { raw: text };
  return JSON.parse(data[data.length - 1]);
}

function callTool(name, args) {
  return { jsonrpc: "2.0", id: 1, method: "tools/call", params: { name, arguments: args } };
}

function payload(json) {
  const text = json?.result?.content?.[0]?.text;
  assert.equal(typeof text, "string");
  return JSON.parse(text);
}

test("rejects missing, wrong, and short tokens", async () => {
  const app = await boot();
  try {
    const missing = await rpc(app.url, "", callTool("pidevops_projects", {}));
    assert.equal(missing.status, 401);
    const wrong = await rpc(app.url, "not-the-estate-token", callTool("pidevops_projects", {}));
    assert.equal(wrong.status, 401);
    const health = await fetch(`${app.url}/healthz`);
    assert.equal(health.status, 200);
    const body = await health.json();
    assert.equal(body.status, "ok");
    assert.equal(body.service, "estate-connector");
  } finally {
    app.server.close();
  }
});

test("a short token is treated as not configured", async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "estate-mcp-"));
  const runtime = createRuntime({
    env: { ESTATE_MCP_TOKEN: "too-short", ESTATE_MCP_STATE_DIR: dir, PICEO_BASE_URL: "http://127.0.0.1:9" },
    fetchImpl: async () => { throw new Error("no network"); },
  });
  const app = await startServer(runtime);
  try {
    const health = await fetch(`${app.url}/healthz`);
    assert.equal(health.status, 503);
    const denied = await rpc(app.url, "too-short", callTool("coord_list_activity", {}));
    assert.equal(denied.status, 401);
  } finally {
    app.server.close();
  }
});

test("lists only the safe tools and a read tool returns the register", async () => {
  const app = await boot();
  try {
    const init = await rpc(app.url, TOKEN, {
      jsonrpc: "2.0",
      id: 1,
      method: "initialize",
      params: { protocolVersion: "2025-11-25", capabilities: {}, clientInfo: { name: "test", version: "0" } },
    });
    assert.equal(init.status, 200);
    assert.equal(init.json.result.serverInfo.name, "estate-connector");

    const listed = await rpc(app.url, TOKEN, { jsonrpc: "2.0", id: 2, method: "tools/list", params: {} });
    assert.equal(listed.status, 200);
    const names = listed.json.result.tools.map((tool) => tool.name).sort();
    assert.deepEqual(names, [...READ_TOOL_NAMES, ...WRITE_TOOL_NAMES].sort());
    const banned = new Set(["delete", "destroy", "merge", "deploy", "wipe", "drop"]);
    for (const tool of listed.json.result.tools) {
      assert.equal(banned.has(tool.name), false);
      assert.equal(tool.annotations.destructiveHint, false);
    }
    for (const name of WRITE_TOOL_NAMES) {
      const tool = listed.json.result.tools.find((item) => item.name === name);
      assert.equal(tool.annotations.readOnlyHint, false);
      assert.match(tool.description, /^WRITE\./);
    }

    const read = await rpc(app.url, TOKEN, callTool("pidevops_projects", {}));
    const body = payload(read.json);
    assert.deepEqual(body.projects.map((project) => project.id), ["pi-dev-ops"]);
    assert.equal(app.calls.length, 0);
  } finally {
    app.server.close();
  }
});

test("a write is validated, shared, and audit-logged", async () => {
  const app = await boot();
  try {
    const before = app.calls.length;
    const posted = await rpc(app.url, TOKEN, callTool("coord_post_note", {
      actor: "Queue",
      system: "mc",
      text: "Gate is red. Bearer sk-secret-should-not-stick",
    }));
    const note = payload(posted.json);
    assert.equal(note.write, true);
    assert.equal(note.activity.actor, "Queue");
    assert.equal(note.activity.summary.includes("sk-secret"), false);
    assert.equal(app.calls.length, before);

    const feed = await rpc(app.url, TOKEN, callTool("coord_list_activity", { limit: 5 }));
    const activity = payload(feed.json);
    assert.equal(activity.activity[0].kind, "note");
    assert.equal(activity.activity[0].actor, "Queue");

    const audit = await rpc(app.url, TOKEN, callTool("coord_list_audit", { limit: 5 }));
    const row = payload(audit.json).audit[0];
    assert.equal(row.actor, "Queue");
    assert.equal(row.tool, "coord_post_note");
    assert.equal(row.ok, true);
    assert.equal(typeof row.ts, "string");
    assert.equal(JSON.stringify(row).includes(TOKEN), false);

    const impersonated = await rpc(app.url, TOKEN, callTool("coord_post_note", {
      actor: "Queue",
      system: "mc",
      text: "pretending",
    }), { "X-Bot-Name": "Scout" });
    const denied = payload(impersonated.json);
    assert.equal(impersonated.json.result.isError, true);
    assert.match(denied.error, /X-Bot-Name/);
  } finally {
    app.server.close();
  }
});

test("claim and release do not let a second bot take the work", async () => {
  const app = await boot();
  try {
    const saved = await rpc(app.url, TOKEN, callTool("mc_update_queue_item", {
      actor: "Queue",
      id: "gate-check",
      title: "Watch the gate",
      system: "pidevops",
    }));
    assert.equal(payload(saved.json).created, true);

    const claimed = await rpc(app.url, TOKEN, callTool("mc_claim_work", { actor: "Queue", id: "gate-check" }));
    assert.equal(payload(claimed.json).item.owner, "Queue");

    const stolen = await rpc(app.url, TOKEN, callTool("mc_claim_work", { actor: "Scout", id: "gate-check" }));
    assert.equal(stolen.json.result.isError, true);
    assert.match(payload(stolen.json).error, /Queue/);

    const rude = await rpc(app.url, TOKEN, callTool("mc_release_work", { actor: "Scout", id: "gate-check" }));
    assert.equal(rude.json.result.isError, true);

    const released = await rpc(app.url, TOKEN, callTool("mc_release_work", { actor: "Queue", id: "gate-check" }));
    assert.equal(payload(released.json).item.owner, null);
    assert.equal(payload(released.json).item.status, "open");

    const queue = await rpc(app.url, TOKEN, callTool("mc_queue", {}));
    const view = payload(queue.json);
    assert.equal(view.coordination[0].id, "gate-check");
    assert.equal(view.linear.issues.some((issue) => issue.identifier === "RA-9"), true);
    assert.equal(JSON.stringify(view).includes("lin-test-secret"), false);
  } finally {
    app.server.close();
  }
});

test("health read uses the Pi-CEO bearer and hides live prompt text", async () => {
  const app = await boot();
  try {
    const health = await rpc(app.url, TOKEN, callTool("pidevops_health", {}));
    const body = payload(health.json);
    assert.equal(body.body.status, "ok");
    assert.equal(body.bearer_configured, true);
    const upstream = app.calls.find((call) => call.url.endsWith("/health"));
    assert.equal(upstream.opts.headers.Authorization, "Bearer tao-test-bearer");
    assert.equal(JSON.stringify(upstream.opts.headers).includes(TOKEN), false);

    const live = await rpc(app.url, TOKEN, callTool("mc_health", {}));
    const mc = payload(live.json);
    assert.equal(mc.live.body.active_sessions[0].phase, "build");
    assert.equal(JSON.stringify(mc).includes("hidden"), false);
  } finally {
    app.server.close();
  }
});

test("the real project register still contains both homes", async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "estate-mcp-"));
  const runtime = createRuntime({
    env: {
      ESTATE_MCP_TOKEN: TOKEN,
      ESTATE_MCP_STATE_DIR: dir,
      ESTATE_PROJECTS_PATH: REAL_PROJECTS,
      PICEO_BASE_URL: "http://127.0.0.1:9",
    },
    fetchImpl: async () => { throw new Error("no network"); },
  });
  const app = await startServer(runtime);
  try {
    const read = await rpc(app.url, TOKEN, callTool("mc_projects", {}));
    const ids = payload(read.json).projects.map((project) => project.id);
    assert.ok(ids.includes("pi-dev-ops"));
    assert.ok(ids.includes("unite-group"));
    assert.equal(app.server.listening, true);
  } finally {
    app.server.close();
  }
});
