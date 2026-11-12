import { joinUrl, parseBody } from "./upstream.js";

const MAX_BODY = 65536;
const TIMEOUT_MS = 8000;

// One login per connector context (the server builds one context at start).
// Holds { base, pending } where pending resolves to { cookie } or { failure }.
const sessions = new WeakMap();

/**
 * GET a Pi CEO API path as a logged-in session (UNI-3359), the way mcp/pi-ceo-server.js does.
 * PICEO_BEARER_TOKEN holds the Pi CEO login password. Pi CEO's require_auth rejects that
 * password as a Bearer token, so it is sent only in the body of POST /api/login. Only the
 * tao_session cookie goes to the API. A 401 drops the cookie, logs in again, retries once.
 * Neither the password nor the cookie is ever returned or logged.
 */
export async function piceoGetJson(ctx, apiPath) {
  const base = ctx.env.PICEO_BASE_URL;
  const password = ctx.env.PICEO_BEARER_TOKEN;
  if (!password) {
    return {
      configured: true, ok: false, status: 401, error: "not_authenticated",
      reason: "Set PICEO_BEARER_TOKEN to the Pi CEO login password.",
    };
  }
  const url = joinUrl(base, apiPath);
  let result = await getAsSession(ctx, base, password, url);
  if (result.status === 401 && !result.error) {
    result = await getAsSession(ctx, base, password, url);
  }
  return result;
}

async function getAsSession(ctx, base, password, url) {
  const pending = currentLogin(ctx, base, password);
  const session = await pending;
  if (!session.cookie) return session.failure;
  const res = await send(url, { method: "GET", headers: { accept: "application/json", cookie: session.cookie } });
  if (res.error) return { configured: true, ok: false, status: 0, error: res.error };
  if (res.status === 401) forget(ctx, pending);
  return { configured: true, ok: res.ok, status: res.status, body: parseBody(res.text) };
}

function currentLogin(ctx, base, password) {
  const held = sessions.get(ctx);
  if (held && held.base === base) return held.pending;
  const pending = login(base, password);
  sessions.set(ctx, { base, pending });
  // A failed login is not cached, so the next call tries again.
  pending.then((session) => { if (!session.cookie) forget(ctx, pending); });
  return pending;
}

function forget(ctx, pending) {
  if (sessions.get(ctx)?.pending === pending) sessions.delete(ctx);
}

async function login(base, password) {
  const res = await send(joinUrl(base, "/api/login"), {
    method: "POST",
    headers: { accept: "application/json", "content-type": "application/json" },
    body: JSON.stringify({ password }),
  });
  if (res.error) return { failure: { configured: true, ok: false, status: 0, error: res.error } };
  const cookie = res.ok ? sessionCookie(res.headers) : "";
  if (!cookie) return { failure: { configured: true, ok: false, status: res.status, error: "login_failed" } };
  return { cookie };
}

/** Redirects are never followed: the password and the cookie stay with PICEO_BASE_URL. */
async function send(url, init) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(url, { ...init, signal: ctrl.signal, redirect: "manual" });
    const text = (await res.text()).slice(0, MAX_BODY);
    return { ok: res.ok, status: res.status, headers: res.headers, text };
  } catch (err) {
    return { error: err?.name === "AbortError" ? "timeout" : "unreachable" };
  } finally {
    clearTimeout(timer);
  }
}

function sessionCookie(headers) {
  const lines = typeof headers.getSetCookie === "function"
    ? headers.getSetCookie()
    : [headers.get("set-cookie") || ""];
  for (const line of lines) {
    const match = /(?:^|,\s*)tao_session=([^;,\s]+)/.exec(line);
    if (match) return `tao_session=${match[1]}`;
  }
  return "";
}
