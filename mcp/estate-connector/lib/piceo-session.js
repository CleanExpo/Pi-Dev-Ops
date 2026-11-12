import { joinUrl } from "./upstream.js";

const TIMEOUT_MS = 8000;
const REDACTED = "[redacted]";
const MAX_DEPTH = 64; // deeper JSON is replaced by REDACTED rather than walked

// One login per connector context (the server builds one context at start).
// Holds { base, pending } where pending resolves to { cookie } or { failure }.
const sessions = new WeakMap();

/**
 * GET a Pi CEO API path as a logged-in session (UNI-3359), the way mcp/pi-ceo-server.js does.
 * PICEO_BEARER_TOKEN holds the Pi CEO login password. Pi CEO's require_auth rejects that
 * password as a Bearer token, so it is sent only in the body of POST /api/login. Only the
 * tao_session cookie goes to the API. A 401 drops the cookie, logs in again, retries once.
 *
 * What comes back is an allow-list, never the upstream reply as received:
 * - `fields` names the top-level keys the caller may receive. Every other key is dropped
 *   and only their number is reported (`omitted_fields`), never their names or values.
 * - An error reply (not 2xx) returns its status and no body. Error details are where a
 *   server echoes request input back.
 * - A 2xx reply that is not a JSON object returns no body and `unexpected_body`.
 * - Inside the kept fields, every decoded string, key and number has the password and the
 *   session token replaced by "[redacted]" (see allowedBody).
 * Neither secret is logged.
 */
export async function piceoGetJson(ctx, apiPath, fields) {
  if (!Array.isArray(fields)) throw new TypeError("piceoGetJson needs the list of fields to return");
  const base = ctx.env.PICEO_BASE_URL;
  const password = ctx.env.PICEO_BEARER_TOKEN;
  if (!password) {
    return {
      configured: true, ok: false, status: 401, error: "not_authenticated",
      reason: "Set PICEO_BEARER_TOKEN to the Pi CEO login password.",
    };
  }
  const url = joinUrl(base, apiPath);
  let reply = await getAsSession(ctx, base, password, url);
  if (reply.res?.status === 401) reply = await getAsSession(ctx, base, password, url);
  return reply.failure || resultFrom(reply.res, reply.secrets, fields);
}

async function getAsSession(ctx, base, password, url) {
  const pending = currentLogin(ctx, base, password);
  const session = await pending;
  if (!session.cookie) return { failure: session.failure };
  const res = await send(url, { method: "GET", headers: { accept: "application/json", cookie: session.cookie } });
  if (res.error) return { failure: { configured: true, ok: false, status: 0, error: res.error } };
  if (res.status === 401) forget(ctx, pending);
  return { res, secrets: [password, session.cookie.slice("tao_session=".length)] };
}

function resultFrom(res, secrets, fields) {
  const head = { configured: true, ok: res.ok, status: res.status };
  if (!res.ok) return { ...head, error: "upstream_error" };
  const kept = allowedBody(res.text, secrets, fields);
  if (!kept) return { ...head, ok: false, error: "unexpected_body" };
  const result = { ...head, body: kept.body };
  if (kept.omitted > 0) result.omitted_fields = kept.omitted;
  return result;
}

/**
 * The listed top-level fields of a JSON object body, with every secret removed from what
 * the caller will read. Returns null when the body is not a JSON object.
 * JSON.parse decodes every JSON escape (\uXXXX, \", \\) before the scrub, so the scrub sees
 * the value the caller receives, at any depth, in strings, keys and numbers.
 * Limit: a secret that Pi CEO itself re-encodes (percent-encoding, base64) inside a kept field
 * is not recognised. Pi CEO checks the password and issues the session, so it already holds
 * both; this guards against an accidental echo, not against the server that owns the secrets.
 * This module never puts either secret in a URL or a form body, so no ordinary code path
 * would percent-encode one.
 */
export function allowedBody(text, secrets, fields) {
  const live = secrets.filter(Boolean).map(String);
  let parsed;
  try {
    parsed = JSON.parse(String(text));
  } catch {
    return null;
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return null;
  const body = {};
  for (const field of fields) {
    if (Object.hasOwn(parsed, field)) body[field] = withoutSecrets(parsed[field], live, 0);
  }
  return { body, omitted: Object.keys(parsed).filter((key) => !fields.includes(key)).length };
}

function scrubText(text, secrets) {
  let out = String(text);
  for (const secret of secrets) out = out.split(secret).join(REDACTED);
  return out;
}

function withoutSecrets(value, secrets, depth) {
  if (typeof value === "string") return scrubText(value, secrets);
  if (typeof value === "number" || typeof value === "bigint") {
    return secrets.some((secret) => String(value).includes(secret)) ? REDACTED : value;
  }
  if (!value || typeof value !== "object") return value;
  if (depth >= MAX_DEPTH) return REDACTED;
  if (Array.isArray(value)) return value.map((item) => withoutSecrets(item, secrets, depth + 1));
  const out = {};
  for (const [key, item] of Object.entries(value)) {
    out[scrubText(key, secrets)] = withoutSecrets(item, secrets, depth + 1);
  }
  return out;
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
    // Not cut: a cut JSON body fails to parse, and res.text() has already read all of it.
    const text = await res.text();
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
