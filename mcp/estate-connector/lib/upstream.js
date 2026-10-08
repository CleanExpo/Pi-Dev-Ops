import { redact } from "./results.js";

const MAX_BODY = 65536;

/** Read JSON from an http(s) URL. Never returns the bearer token. */
export async function fetchJson(url, token) {
  const headers = { accept: "application/json" };
  if (token) headers.authorization = `Bearer ${token}`;
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 8000);
  try {
    const res = await fetch(url, { headers, signal: ctrl.signal, redirect: "follow" });
    const text = (await res.text()).slice(0, MAX_BODY);
    return { configured: true, ok: res.ok, status: res.status, body: parseBody(text) };
  } catch (err) {
    const reason = err?.name === "AbortError" ? "timeout" : "unreachable";
    return { configured: true, ok: false, status: 0, error: reason };
  } finally {
    clearTimeout(timer);
  }
}

function parseBody(text) {
  try {
    return redact(JSON.parse(text));
  } catch {
    return { raw: text.slice(0, 500) };
  }
}

export function joinUrl(base, path) {
  const root = String(base || "").replace(/\/+$/, "");
  const suffix = String(path || "").startsWith("/") ? path : `/${path}`;
  return `${root}${suffix}`;
}
