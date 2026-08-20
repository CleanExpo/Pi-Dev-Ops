/** Timeouts for the Pi-CEO dashboard proxy. Analyze is an LLM call; 25s 502s it. */

export const PROXY_MAX_DURATION_S = 120;
export const PROXY_DEFAULT_MS = 25_000;
export const PROXY_ANALYZE_MS = 100_000;
export const PROXY_LOGIN_MS = 12_000;

export function proxyTimeoutMs(pathStr: string): number {
  const bare = pathStr.split("?")[0];
  if (bare === "/api/goal-ticket/analyze") return PROXY_ANALYZE_MS;
  return PROXY_DEFAULT_MS;
}

export function isAbortTimeout(err: unknown): boolean {
  if (typeof err !== "object" || err === null) return false;
  const name = "name" in err ? String((err as { name: unknown }).name) : "";
  return name === "TimeoutError" || name === "AbortError";
}

export function proxyAbortPayload(err: unknown): {
  error: string;
  hint: string;
  status: number;
} {
  if (isAbortTimeout(err)) {
    return {
      error: "Pi CEO request timed out",
      hint: "Analyze can take up to a minute. Retry. Linear was not written.",
      status: 504,
    };
  }
  return {
    error: "Pi CEO server unreachable",
    hint: "The dashboard could not reach PI_CEO_URL. Linear was not written.",
    status: 502,
  };
}
