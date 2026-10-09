import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { after, before, test } from "node:test";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";
import { adapters } from "../adapters/registry.js";
import { buildApp } from "../server.js";

const TOKEN = "test-token-0123456789";
const REPO_ROOT = path.resolve(import.meta.dirname, "../../..");
const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "estate-mcp-"));

let server;
let port;

function toolText(result) {
  const block = result.content?.find((item) => item.type === "text");
  assert.ok(block?.text, "tool returned text");
  return JSON.parse(block.text);
}

async function connect(headers = { "X-Estate-Bot": "Queue" }, search = "") {
  const transport = new StreamableHTTPClientTransport(new URL(`http://127.0.0.1:${port}/mcp${search}`), {
    requestInit: { headers: { Authorization: `Bearer ${TOKEN}`, ...headers } },
  });
  const client = new Client({ name: "estate-test", version: "0.0.0" });
  await client.connect(transport);
  return client;
}

before(async () => {
  const app = buildApp({
    token: TOKEN,
    host: "127.0.0.1",
    repoRoot: REPO_ROOT,
    dataDir,
    env: {},
  });
  server = await new Promise((resolve) => {
    const listening = app.listen(0, "127.0.0.1", () => resolve(listening));
  });
  port = server.address().port;
});

after(async () => {
  await new Promise((resolve, reject) => server.close((err) => (err ? reject(err) : resolve())));
  fs.rmSync(dataDir, { recursive: true, force: true });
});

test("rejects missing and wrong bearer tokens", async () => {
  const url = `http://127.0.0.1:${port}/mcp`;
  const missing = await fetch(url, { method: "POST", headers: { "content-type": "application/json" }, body: "{}" });
  const wrong = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json", authorization: "Bearer not-the-token" },
    body: "{}",
  });
  assert.equal(missing.status, 401);
  assert.equal(wrong.status, 401);
  assert.deepEqual(await missing.json(), { error: "unauthorized" });
});

test("health check does not require a token and reveals nothing else", async () => {
  const res = await fetch(`http://127.0.0.1:${port}/healthz`);
  assert.equal(res.status, 200);
  assert.deepEqual(await res.json(), { status: "ok" });
});

test("startup refuses a missing token", () => {
  assert.throws(() => buildApp({ token: "short", env: {}, dataDir, repoRoot: REPO_ROOT }), /ESTATE_MCP_TOKEN/);
});

test("lists read and write tools for the registered systems only", async () => {
  assert.deepEqual(adapters.map((adapter) => adapter.id), [
    "coord", "pidevops", "unite", "mc", "restoreassist", "synthex", "drnrpg",
  ]);
  const client = await connect();
  try {
    const listed = await client.listTools();
    const names = listed.tools.map((tool) => tool.name).sort();
    assert.deepEqual(names, [
      "coord_activity",
      "coord_post_note",
      "drnrpg_health",
      "drnrpg_post_note",
      "mc_claim_work",
      "mc_live",
      "mc_post_note",
      "mc_queue",
      "mc_release_work",
      "mc_update_queue_item",
      "pidevops_deployments",
      "pidevops_health",
      "pidevops_post_status",
      "pidevops_projects",
      "restoreassist_health",
      "restoreassist_post_note",
      "synthex_health",
      "synthex_post_note",
      "unite_post_note",
      "unite_projects",
      "unite_status",
    ]);
    for (const tool of listed.tools) {
      assert.notEqual(tool.annotations?.destructiveHint, true);
      assert.equal(/delete|merge|wipe|_deploy$/.test(tool.name), false);
      const write = tool.annotations?.readOnlyHint === false;
      assert.equal(tool.description.startsWith(write ? "[WRITE]" : "[READ]"), true);
    }
  } finally {
    await client.close();
  }
});

test("pidevops_projects reads the project list", async () => {
  const client = await connect();
  try {
    const result = await client.callTool({ name: "pidevops_projects", arguments: { id: "pi-dev-ops" } });
    const body = toolText(result);
    assert.equal(body.project.repo, "CleanExpo/Pi-Dev-Ops");
    assert.equal(Boolean(result.isError), false);
  } finally {
    await client.close();
  }
});

test("a write without a bot is rejected and audited", async () => {
  const client = await connect({});
  try {
    const result = await client.callTool({ name: "mc_post_note", arguments: { text: "should fail" } });
    assert.equal(result.isError, true);
    const audit = fs.readFileSync(path.join(dataDir, "audit.jsonl"), "utf8");
    const row = audit.trim().split("\n").at(-1);
    const entry = JSON.parse(row);
    assert.equal(entry.tool, "mc_post_note");
    assert.equal(entry.ok, false);
    assert.equal(entry.bot, "unknown");
    assert.ok(entry.ts);
    assert.equal(audit.includes(TOKEN), false);
  } finally {
    await client.close();
  }
});

test("mc_post_note writes the shared feed and an audit line", async () => {
  const client = await connect();
  try {
    const wrote = await client.callTool({
      name: "mc_post_note",
      arguments: { text: "Queue checked Mission Control" },
    });
    const note = toolText(wrote);
    assert.equal(note.system, "mc");
    assert.equal(note.bot, "queue");
    const feed = toolText(await client.callTool({ name: "coord_activity", arguments: { system: "mc" } }));
    assert.equal(feed.notes.some((item) => item.id === note.id), true);
    const audit = fs.readFileSync(path.join(dataDir, "audit.jsonl"), "utf8");
    const entry = audit.trim().split("\n").map((line) => JSON.parse(line)).find((row) => row.ok && row.tool === "mc_post_note");
    assert.equal(entry.bot, "queue");
    assert.ok(entry.ts);
    assert.equal(audit.includes(TOKEN), false);
  } finally {
    await client.close();
  }
});

test("a project note lands on the shared feed", async () => {
  const client = await connect();
  try {
    const wrote = toolText(await client.callTool({
      name: "restoreassist_post_note",
      arguments: { text: "RestoreAssist health checked" },
    }));
    assert.equal(wrote.system, "restoreassist");
    assert.equal(wrote.bot, "queue");
    const feed = toolText(await client.callTool({
      name: "coord_activity",
      arguments: { system: "restoreassist" },
    }));
    assert.equal(feed.notes.some((item) => item.id === wrote.id), true);
  } finally {
    await client.close();
  }
});

test("claim and release use the bot named on the URL", async () => {
  const queue = await connect({ "X-Estate-Bot": "Queue" });
  const scout = await connect({}, "?bot=scout");
  try {
    const created = toolText(await queue.callTool({
      name: "mc_update_queue_item",
      arguments: { id: "job-1", title: "Watch the queue" },
    }));
    assert.equal(created.status, "open");
    const claimed = toolText(await scout.callTool({ name: "mc_claim_work", arguments: { id: "job-1" } }));
    assert.equal(claimed.status, "claimed");
    assert.equal(claimed.owner, "scout");
    const stolen = await queue.callTool({ name: "mc_release_work", arguments: { id: "job-1" } });
    assert.equal(stolen.isError, true);
    const released = toolText(await scout.callTool({ name: "mc_release_work", arguments: { id: "job-1" } }));
    assert.equal(released.status, "open");
    assert.equal(released.owner, null);
  } finally {
    await queue.close();
    await scout.close();
  }
});
