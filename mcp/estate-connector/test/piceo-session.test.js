// UNI-3359: mc_live must log in to Pi CEO for a session, not send the password as a Bearer token.
// A local http server stands in for Pi CEO. It copies the two rules that matter from
// app/server: /api/login sets a tao_session cookie, and require_auth accepts only a
// session token (cookie or Bearer), never the password itself.
import assert from "node:assert/strict";
import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { after, before, beforeEach, test } from "node:test";
import { missionControl } from "../adapters/mission-control/index.js";
import { createContext } from "../lib/context.js";
import { fetchJson } from "../lib/upstream.js";

const REPO_ROOT = path.resolve(import.meta.dirname, "../../..");
// Made-up test value. It is not, and never was, a real credential.
const PASSWORD = "fixture-password-not-real-3359";

const fake = {
  server: null,
  base: "",
  sessions: new Set(),
  issued: 0,
  logins: 0,
  liveCalls: 0,
  liveAlways401: false,
  loginRedirect: false,
  seenAuthHeaders: [],
  redirectTargetHits: 0,
};

function resetFake() {
  Object.assign(fake, {
    sessions: new Set(), issued: 0, logins: 0, liveCalls: 0,
    liveAlways401: false, loginRedirect: false, seenAuthHeaders: [], redirectTargetHits: 0,
  });
}

function sendJson(res, status, body, headers = {}) {
  res.writeHead(status, { "content-type": "application/json", ...headers });
  res.end(JSON.stringify(body));
}

function readBody(req) {
  return new Promise((resolve) => {
    let raw = "";
    req.on("data", (chunk) => { raw += chunk; });
    req.on("end", () => resolve(raw));
  });
}

function cookieToken(req) {
  const match = /(?:^|;\s*)tao_session=([^;]+)/.exec(req.headers.cookie || "");
  return match ? match[1] : "";
}

async function handleLogin(req, res) {
  fake.logins += 1;
  if (fake.loginRedirect) {
    res.writeHead(307, { location: "/elsewhere" });
    return res.end();
  }
  const body = JSON.parse((await readBody(req)) || "{}");
  if (body.password !== PASSWORD) return sendJson(res, 401, { detail: "Invalid password" });
  fake.issued += 1;
  const token = `sess-${fake.issued}`;
  fake.sessions.add(token);
  return sendJson(res, 200, { ok: true }, {
    "set-cookie": `tao_session=${token}; HttpOnly; Max-Age=3600; Path=/; SameSite=strict`,
  });
}

function handleLive(req, res) {
  fake.liveCalls += 1;
  fake.seenAuthHeaders.push(req.headers.authorization || "");
  const auth = req.headers.authorization || "";
  const bearer = auth.startsWith("Bearer ") ? auth.slice(7) : "";
  const authed = fake.sessions.has(cookieToken(req)) || fake.sessions.has(bearer);
  if (!authed || fake.liveAlways401) return sendJson(res, 401, { detail: "Not authenticated" });
  return sendJson(res, 200, { sessions: [{ id: "s1", status: "building" }], health: "ok" });
}

before(async () => {
  fake.server = http.createServer((req, res) => {
    if (req.method === "POST" && req.url === "/api/login") return handleLogin(req, res);
    if (req.method === "GET" && req.url === "/api/mission-control/live") return handleLive(req, res);
    if (req.url === "/elsewhere") {
      fake.redirectTargetHits += 1;
      return sendJson(res, 200, { ok: true });
    }
    return sendJson(res, 404, { detail: "not found" });
  });
  await new Promise((resolve) => fake.server.listen(0, "127.0.0.1", resolve));
  fake.base = `http://127.0.0.1:${fake.server.address().port}`;
});

after(() => new Promise((resolve) => fake.server.close(resolve)));

beforeEach(resetFake);

function makeCtx(env) {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "estate-uni3359-"));
  return createContext({ repoRoot: REPO_ROOT, dataDir, env });
}

function liveTool() {
  return missionControl.tools().find((tool) => tool.name === "mc_live");
}

async function callLive(ctx) {
  const result = await liveTool().handler({}, ctx);
  return { result, body: JSON.parse(result.content[0].text) };
}

const configured = () => makeCtx({ PICEO_BASE_URL: fake.base, PICEO_BEARER_TOKEN: PASSWORD });

test("the old way fails: the password sent as a Bearer token gets 401", async () => {
  const res = await fetchJson(`${fake.base}/api/mission-control/live`, PASSWORD);
  assert.equal(res.status, 401);
  assert.equal(res.ok, false);
});

test("mc_live logs in, keeps the tao_session cookie, and reads the live page", async () => {
  const ctx = configured();
  const { body } = await callLive(ctx);
  assert.equal(body.ok, true);
  assert.equal(body.status, 200);
  assert.equal(body.body.sessions[0].id, "s1");
  assert.ok("coordination_queue" in body, "the shared queue is still included");
  assert.equal(fake.logins, 1);
  for (const header of fake.seenAuthHeaders) assert.ok(!header.includes(PASSWORD));

  const second = await callLive(ctx);
  assert.equal(second.body.ok, true);
  assert.equal(fake.logins, 1, "the cached session is reused, not a new login per call");
});

test("a 401 on a cached session logs in again and retries once", async () => {
  const ctx = configured();
  assert.equal((await callLive(ctx)).body.ok, true);
  fake.sessions.clear(); // the server forgot the session, as after a restart or expiry
  const { body } = await callLive(ctx);
  assert.equal(body.ok, true);
  assert.equal(body.status, 200);
  assert.equal(fake.logins, 2);
  assert.equal(fake.liveCalls, 3);
});

test("the retry happens once only, then the 401 is reported", async () => {
  const ctx = configured();
  fake.liveAlways401 = true;
  const { body } = await callLive(ctx);
  assert.equal(body.ok, false);
  assert.equal(body.status, 401);
  assert.equal(fake.logins, 2);
  assert.equal(fake.liveCalls, 2);
});

test("a wrong password reports a failed login without calling the live page", async () => {
  const ctx = makeCtx({ PICEO_BASE_URL: fake.base, PICEO_BEARER_TOKEN: "wrong-fixture-value" });
  const { body } = await callLive(ctx);
  assert.equal(body.ok, false);
  assert.equal(body.status, 401);
  assert.equal(body.error, "login_failed");
  assert.equal(fake.liveCalls, 0);
});

test("the login does not follow a redirect, so the password is never re-sent", async () => {
  const ctx = configured();
  fake.loginRedirect = true;
  const { body } = await callLive(ctx);
  assert.equal(body.ok, false);
  assert.equal(body.error, "login_failed");
  assert.equal(fake.redirectTargetHits, 0);
});

test("with no password set, mc_live says so and does not log in", async () => {
  const ctx = makeCtx({ PICEO_BASE_URL: fake.base });
  const { body } = await callLive(ctx);
  assert.equal(body.ok, false);
  assert.equal(body.status, 401);
  assert.match(body.reason, /PICEO_BEARER_TOKEN/);
  assert.equal(fake.logins, 0);
});

// Every log line in this connector goes through console.* (lib/register.js, lib/writes.js,
// server.js). process.stdout is left alone because the test runner reports through it.
async function captureOutput(run) {
  const lines = [];
  const methods = ["log", "info", "warn", "error", "debug", "trace"];
  const saved = methods.map((name) => console[name]);
  methods.forEach((name) => { console[name] = (...args) => lines.push(args.map(String).join(" ")); });
  try {
    await run();
  } finally {
    methods.forEach((name, i) => { console[name] = saved[i]; });
  }
  return lines.join("\n");
}

test("the output capture used below does see a planted line (positive control)", async () => {
  const text = await captureOutput(async () => { console.error(`planted ${PASSWORD}`); });
  assert.ok(text.includes(PASSWORD));
});

test("the password never appears in logs, results, or the audit file", async () => {
  const ctx = configured();
  const results = [];
  const logged = await captureOutput(async () => {
    results.push((await callLive(ctx)).result);
    fake.sessions.clear();
    results.push((await callLive(ctx)).result);
    fake.liveAlways401 = true;
    results.push((await callLive(ctx)).result);
    const bad = makeCtx({ PICEO_BASE_URL: fake.base, PICEO_BEARER_TOKEN: `${PASSWORD}-x` });
    results.push((await callLive(bad)).result);
  });
  assert.ok(fake.logins >= 4, "the flows above really ran");
  assert.ok(!logged.includes(PASSWORD), "password found in console output");
  for (const result of results) assert.ok(!JSON.stringify(result).includes(PASSWORD), "password found in a result");
  for (const name of fs.readdirSync(ctx.dataDir)) {
    const text = fs.readFileSync(path.join(ctx.dataDir, name), "utf8");
    assert.ok(!text.includes(PASSWORD), `password found in ${name}`);
  }
});
