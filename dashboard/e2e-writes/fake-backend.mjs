// Stand-in for the Pi-CEO backend, for the write-action journeys (AAA check 12).
//
// It is stateful (kill/resume change what /api/swarm/status reports, so a page
// reload sees the effect) and it RECORDS every write it receives, so a test can
// assert exactly what a button sent. It proves what the dashboard sends and how
// the page reacts. It does not prove the real backend accepts it: that is what
// the preview journeys (check 3) are for.
//
//   GET  /__calls              recorded write calls (login excluded)
//   POST /__reset              clear calls, restore the initial state
//   POST /__control {failNext, halted}  refuse the next "kill"/"resume" with 403;
//                              start halted or running
import { createServer } from "node:http";

const PORT = Number(process.env.FAKE_BACKEND_PORT ?? 7778);

const initial = () => ({
  swarm_enabled_env: true,
  kill_switch_active: false,
  escalation_lock_active: false,
  panic_count_last_hour: 0,
  approver_allowlist: ["alice", "bob"],
  approver_totp_configured: ["alice", "bob"],
});

let state = initial();
let calls = [];
let failNext = null;

const json = (res, status, body, headers = {}) => {
  res.writeHead(status, { "Content-Type": "application/json", ...headers });
  res.end(JSON.stringify(body));
};

const readBody = (req) =>
  new Promise((resolve) => {
    let raw = "";
    req.on("data", (c) => (raw += c));
    req.on("end", () => {
      try { resolve(raw ? JSON.parse(raw) : {}); } catch { resolve({ __unparseable: raw }); }
    });
  });

const digits = (v) => typeof v === "string" && /^\d{6,8}$/.test(v);

function kill(body) {
  const ok = body.approver1_user && body.approver2_user && body.approver1_user !== body.approver2_user
    && digits(body.approver1_totp) && digits(body.approver2_totp);
  if (!ok) return [400, { error: "two different approvers with TOTP codes required" }];
  if (state.kill_switch_active) return [409, { error: "already halted" }];
  state = { ...state, kill_switch_active: true, panic_count_last_hour: state.panic_count_last_hour + 1 };
  return [200, { ok: true, kill_switch_active: true }];
}

function resume(body) {
  if (!body.approver_user || !digits(body.approver_totp)) {
    return [400, { error: "approver and TOTP code required" }];
  }
  if (!state.kill_switch_active) return [409, { error: "not halted" }];
  state = { ...state, kill_switch_active: false };
  return [200, { ok: true, kill_switch_active: false }];
}

createServer(async (req, res) => {
  const { pathname } = new URL(req.url, "http://x");
  if (pathname === "/__calls") return json(res, 200, calls);
  if (pathname === "/__reset") { state = initial(); calls = []; failNext = null; return json(res, 200, { ok: true }); }
  if (pathname === "/__control") {
    const body = await readBody(req);
    if ("failNext" in body) failNext = body.failNext ?? null;
    if ("halted" in body) state = { ...state, kill_switch_active: Boolean(body.halted) };
    return json(res, 200, { failNext, halted: state.kill_switch_active });
  }
  if (pathname === "/api/login") {
    return json(res, 200, { ok: true }, { "Set-Cookie": "tao_session=fake; Path=/; HttpOnly" });
  }
  if (!/(^|;\s*)tao_session=fake/.test(req.headers.cookie ?? "")) return json(res, 401, { error: "no session" });

  if (pathname === "/api/swarm/status" && req.method === "GET") return json(res, 200, state);
  const op = /^\/api\/swarm\/(kill|resume)$/.exec(pathname)?.[1];
  if (op && req.method === "POST") {
    const body = await readBody(req);
    calls.push({ method: req.method, path: pathname, body });
    if (failNext === op) { failNext = null; return json(res, 403, { error: "approver TOTP rejected" }); }
    const [status, out] = op === "kill" ? kill(body) : resume(body);
    return json(res, status, out);
  }
  return json(res, 404, { error: `fake backend has no ${req.method} ${pathname}` });
}).listen(PORT, "127.0.0.1", () => console.log(`fake backend on ${PORT}`));
