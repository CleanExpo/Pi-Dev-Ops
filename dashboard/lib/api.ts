import type { BuildRequest, BuildResponse, Session } from "./types";

// All calls go client-side to the local FastAPI.
// When this Vercel page is opened in the user's local browser,
// requests to 127.0.0.1:7777 are same-machine — TrustedHostMiddleware passes.
export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:7777";

export const WS_BASE = API_BASE.replace(/^http/, "ws");

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    credentials: "include", // send tao_session cookie
    headers: { "Content-Type": "application/json", ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  login: (password: string) =>
    request<{ ok: boolean }>("/api/login", {
      method: "POST",
      body: JSON.stringify({ password }),
    }),

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
