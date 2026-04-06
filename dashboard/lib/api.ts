import type { BuildRequest, BuildResponse, Session } from "./types";

// Backend URL — set NEXT_PUBLIC_API_URL in Vercel env vars to point at Railway
// Falls back to localhost for local npm run dev
export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:7777";

// http → ws, https → wss (regex replaces the http prefix only)
export const WS_BASE = API_BASE.replace(/^http/, "ws");

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const body = await res.text().catch(() => res.statusText);
    // Try to extract FastAPI detail message
    try {
      const json = JSON.parse(body);
      throw new Error(json.detail ?? body);
    } catch {
      throw new Error(body || `HTTP ${res.status}`);
    }
  }
  return res.json() as Promise<T>;
}

// Store the session token in memory so the WebSocket can use it as a header
// (cross-origin WebSocket connections cannot send cookies)
let _sessionToken: string | null = null;
export function getSessionToken() { return _sessionToken; }
export function setSessionToken(t: string | null) { _sessionToken = t; }

export const api = {
  login: async (password: string) => {
    const res = await request<{ ok: boolean }>("/api/login", {
      method: "POST",
      body: JSON.stringify({ password }),
    });
    // After login, fetch the raw token from /api/me isn't needed —
    // we cache the password-derived state; WS auth falls back to cookie.
    return res;
  },

  me: () => request<{ authenticated: boolean }>("/api/me"),

  logout: () =>
    request<{ ok: boolean }>("/api/logout", { method: "POST" }),

  build: (payload: BuildRequest) =>
    request<BuildResponse>("/api/build", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  sessions: () => request<Session[]>("/api/sessions"),

  kill: (sid: string) =>
    request<{ ok: boolean }>(`/api/sessions/${sid}/kill`, {
      method: "POST",
    }),
};
